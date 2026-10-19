from pathlib import Path
from importlib import import_module
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import os
import time

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa
import pytest
from fastapi import HTTPException


@pytest.mark.parametrize("database", ["sqlite", "postgresql"])
def test_user_migration_preserves_accounts_sites_and_audit_history(tmp_path, monkeypatch, database):
    root = Path(__file__).resolve().parents[1]
    url = f"sqlite+pysqlite:///{tmp_path / 'migration.db'}"
    if database == "postgresql":
        url = os.getenv("STOCC_TEST_MIGRATION_DATABASE_URL")
        if not url:
            pytest.skip("Requires a dedicated empty loopback PostgreSQL test database")
        target = sa.engine.make_url(url)
        assert target.get_backend_name() == "postgresql" and target.host in {"127.0.0.1", "localhost"}
        assert target.database and target.database.startswith("stocc_users_test_")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    engine = sa.create_engine(url)
    assert not sa.inspect(engine).get_table_names(), "Refusing to modify a non-empty database"
    # The older 0002 job migration uses PostgreSQL ALTER COLUMN. This SQLite
    # contract test isolates the actual 0003 -> 0004 user/audit migration; the
    # complete migration chain is exercised separately against PostgreSQL.
    if database == "sqlite":
        metadata = sa.MetaData()
        devices = sa.Table("devices", metadata, sa.Column("id", sa.String(64), primary_key=True))
        with engine.begin() as conn:
            devices.create(conn)
            with Operations.context(MigrationContext.configure(conn)):
                import_module("migrations.versions.0003_enterprise_console").upgrade()
        command.stamp(config, "0003_enterprise_console")
    else:
        command.upgrade(config, "0003_enterprise_console")
    metadata = sa.MetaData()
    users = sa.Table("app_users", metadata, autoload_with=engine)
    audit = sa.Table("audit_events", metadata, autoload_with=engine)
    from app.database import now
    with engine.begin() as conn:
        for role in ("admin", "operator", "viewer", "unexpected"):
            conn.execute(users.insert().values(id=role, username=role, roles=[role], sites=["preserved-site"],
                password_hash="legacy-unchanged-hash", enabled=True))
        conn.execute(audit.insert().values(id="historical-event", user_id="admin", event="login", outcome="succeeded", occurred_at=now()))
    command.upgrade(config, "head")
    metadata = sa.MetaData()
    assert "topology_boards" in sa.inspect(engine).get_table_names()
    users = sa.Table("app_users", metadata, autoload_with=engine)
    audit = sa.Table("audit_events", metadata, autoload_with=engine)
    with engine.connect() as conn:
        rows = {row["id"]: row for row in conn.execute(sa.select(users)).mappings()}
        assert rows["admin"]["roles"] == ["superadmin"]
        assert rows["operator"]["roles"] == ["engineer"]
        assert rows["viewer"]["roles"] == ["viewer"]
        assert rows["unexpected"]["enabled"] is False
        assert all(row["sites"] == ["preserved-site"] and row["password_hash"] == "legacy-unchanged-hash" for row in rows.values())
        assert all(row["created_at"] is None for row in rows.values())
        historical = conn.execute(sa.select(audit)).mappings().one()
        assert historical["id"] == "historical-event" and historical["details"] == {} and historical["username"] is None
    command.upgrade(config, "head")
    engine.dispose()
    if database == "postgresql":
        verify_postgres_last_admin_lock(url)


def verify_postgres_last_admin_lock(url):
    from app.auth import AuthContext
    from app.database import Store
    from app.security import SessionUser
    from app.users import Users, UserUpdate
    store = Store(url)
    with store.engine.begin() as conn:
        conn.execute(store.users.insert().values(id="second-admin", username="second-admin",
            display_name="Second test admin", password_hash="unused-test-hash", roles=["superadmin"], sites=["*"], enabled=True))
        for identifier in ("admin", "second-admin"):
            conn.execute(store.sessions.insert().values(token_hash=identifier, user_id=identifier, csrf="test-only", expires_at=time.time() + 60))
    actors = [AuthContext(SessionUser(user_id=identifier, username=identifier, display_name=identifier,
        roles={"superadmin"}, site_ids={"*"}), identifier, "test-only") for identifier in ("admin", "second-admin")]
    ready = Barrier(2)
    def demote(actor, target):
        ready.wait(timeout=5)
        try:
            Users(store).update(actor, target, UserUpdate(role="viewer"))
            return 200
        except HTTPException as error:
            return error.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(demote, actors[0], "second-admin"), pool.submit(demote, actors[1], "admin")]
            assert sorted(result.result(timeout=10) for result in results) == [200, 401]
        with store.engine.connect() as conn:
            active = conn.execute(sa.select(store.users.c.roles).where(store.users.c.enabled.is_(True))).scalars()
            assert sum("superadmin" in roles for roles in active) == 1
    finally:
        store.engine.dispose()
