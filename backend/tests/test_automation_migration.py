"""Additive migration and actual PostgreSQL queue locking, in disposable databases."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module
import os
from threading import Barrier
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa

from app.contracts import ManagedDevice
from app.database import Store, now
from app.fixtures import build_fixture
from app.queue import claim, enqueue, owned
from app.ssh import ConnectionPolicyError


def test_0006_preserves_existing_inventory_keys_and_ciphertext(tmp_path):
    store = Store(f"sqlite+pysqlite:///{tmp_path / 'migration.db'}")
    new_names = set(import_module("app.automation_schema_v1").define_tables(sa.MetaData()))
    new_tables = {getattr(store, name) for name in new_names}
    store.meta.create_all(store.engine, tables=[t for t in store.meta.sorted_tables if t not in new_tables])
    device = ManagedDevice.model_validate(build_fixture().model_dump())
    with store.engine.begin() as conn:
        store.save_device(device, conn)
        conn.execute(store.secrets.insert().values(device_id=device.id, key_id="existing", nonce=b"old-nonce",
                                                   ciphertext=b"untouched-ciphertext"))
        conn.execute(store.host_keys.insert().values(device_id=device.id, public_key="existing-public", fingerprint="SHA256:existing"))
        before = conn.execute(sa.select(store.devices)).mappings().one()
        with Operations.context(MigrationContext.configure(conn)):
            import_module("migrations.versions.0006_collection_automation").upgrade()
        after = conn.execute(sa.select(store.devices)).mappings().one()
        assert dict(before) == dict(after)
        assert conn.execute(sa.select(store.secrets.c.ciphertext)).scalar_one() == b"untouched-ciphertext"
        assert conn.execute(sa.select(store.host_keys.c.fingerprint)).scalar_one() == "SHA256:existing"
        assert conn.execute(sa.select(sa.func.count()).select_from(store.metric_samples)).scalar_one() == 0
    store.engine.dispose()


def test_postgres_two_worker_claims_and_expiry():
    url = os.getenv("NETSTUDIO_TEST_AUTOMATION_DATABASE_URL")
    if not url:
        pytest.skip("Requires a dedicated empty loopback netstudio_automation_test_* database")
    target = sa.engine.make_url(url)
    assert target.get_backend_name() == "postgresql" and target.host in {"127.0.0.1", "localhost"}
    assert target.database.startswith("netstudio_automation_test_")
    store = Store(url)
    assert not sa.inspect(store.engine).get_table_names(), "Refusing to modify a non-empty database"
    store.meta.create_all(store.engine)
    at = now()
    for _ in range(16):
        device = ManagedDevice.model_validate({**build_fixture().model_dump(), "id": str(uuid4())})
        store.save_device(device)
        enqueue(store, device, "connection_test")
    barrier = Barrier(2)
    def run(owner):
        barrier.wait()
        return [claim(store, owner, at + timedelta(seconds=1)) for _ in range(8)]
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(run, "worker-1")
        second = pool.submit(run, "worker-2")
        jobs = [j for j in first.result() + second.result() if j]
    assert len(jobs) == 8 and len({j.id for j in jobs}) == 8
    assert len({j.device_id for j in jobs}) == 8
    reclaimed = claim(store, "worker-3", at + timedelta(seconds=32))
    assert reclaimed and reclaimed.attempt == 2
    old = next(j for j in jobs if j.id == reclaimed.id)
    with store.engine.begin() as conn, pytest.raises(ConnectionPolicyError):
        owned(store, old, old.lease_owner, conn, at + timedelta(seconds=33))
    store.engine.dispose()
