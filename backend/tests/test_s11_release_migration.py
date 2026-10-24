"""S11 migration is additive and preserves existing runtime records."""
from importlib import import_module
import json

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa

from app.database import Store, now


def digest(conn, table):
    rows = [dict(row) for row in conn.execute(sa.select(table)).mappings()]
    return json.dumps(rows, sort_keys=True, default=str, separators=(",", ":"))


def test_0012_upgrade_and_disposable_downgrade_preserve_existing_data(tmp_path):
    store = Store(f"sqlite+pysqlite:///{tmp_path / 's11-migration.db'}")
    names = set(import_module("app.release_schema_v1").define_tables(sa.MetaData()))
    new_tables = {getattr(store, name) for name in names}
    store.meta.create_all(store.engine, tables=[
        table for table in store.meta.sorted_tables if table not in new_tables
    ])
    with store.engine.begin() as conn:
        conn.execute(store.devices.insert().values(
            id="existing", name="Existing", management_address="192.0.2.1",
            site="lab", vendor="Cisco", platform="", model="WS-C2960X",
            serial="", read_only=True, support_status="generic_readonly",
            payload={"id": "existing", "name": "Existing",
                     "management_address": "192.0.2.1", "site": "lab"},
        ))
        conn.execute(store.driver_acceptance.insert().values(
            id="existing-acceptance", source_revision="a" * 40,
            profile_id="cisco_ios", profile_revision=2, vendor="Cisco",
            model_family="WS-C2960X-*", exact_model="WS-C2960X-48FPD-L",
            hardware_revision="V02", os_family="IOS", os_version="15.2(7)E",
            management_mode="standalone", transport="ssh",
            security_profile="ssh2", capability_id="inventory",
            parser_version="test", test_suite_revision="test",
            validation_level="physical_validated", result="pass",
            evidence_ref="CONTROLLED", evidence_sha256="a" * 64,
            evidence_sanitized=True, observed_at=now(), recorded_at=now(),
            expires_at=now() + __import__("datetime").timedelta(days=1),
            reviewed_by="test",
        ))
        protected = {
            "devices": digest(conn, store.devices),
            "acceptance": digest(conn, store.driver_acceptance),
        }
        migration = import_module("migrations.versions.0012_release_acceptance")
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        assert names <= set(sa.inspect(conn).get_table_names())
        assert digest(conn, store.devices) == protected["devices"]
        assert digest(conn, store.driver_acceptance) == protected["acceptance"]
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        assert names.isdisjoint(set(sa.inspect(conn).get_table_names()))
        assert digest(conn, store.devices) == protected["devices"]
        assert digest(conn, store.driver_acceptance) == protected["acceptance"]
    store.engine.dispose()
