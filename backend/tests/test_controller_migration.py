"""S08 additive controller schema preservation contract."""
from importlib import import_module
import json

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa

from app.contracts import ManagedDevice
from app.database import Store, now
from app.fixtures import build_fixture


def _digest(conn, table):
    rows = [dict(row) for row in conn.execute(sa.select(table)).mappings()]
    return json.dumps(rows, sort_keys=True, default=str, separators=(",", ":"))


def test_0011_upgrade_and_downgrade_preserve_existing_data(tmp_path):
    store = Store(f"sqlite+pysqlite:///{tmp_path / 'controller-migration.db'}")
    names = set(import_module("app.controller_schema_v1").define_tables(sa.MetaData()))
    new_tables = {getattr(store, name) for name in names}
    store.meta.create_all(store.engine, tables=[
        table for table in store.meta.sorted_tables if table not in new_tables
    ])
    fixture = build_fixture().model_copy(update={
        "id": "before-s08", "support_status": "generic_readonly",
    })
    device = ManagedDevice.model_validate(fixture.model_dump())
    with store.engine.begin() as conn:
        store.save_device(device, conn)
        conn.execute(store.secrets.insert().values(
            device_id=device.id, key_id="existing", nonce=b"ssh-nonce",
            ciphertext=b"ssh-ciphertext",
        ))
        conn.execute(store.protocol_secrets.insert().values(
            device_id=device.id, protocol="snmp", metadata={"port": 161},
            key_id="existing", nonce=b"snmp-nonce", ciphertext=b"snmp-ciphertext",
        ))
        conn.execute(store.driver_bindings.insert().values(
            device_id=device.id, configured_profile_id="cisco_ios",
            legacy_collector_id="cisco_ios", resolved_profile_id=None,
            profile_revision=2, management_mode="standalone",
            resolution_status="unresolved", resolution_confidence=0,
            resolution_conflicts=[], identity_evidence={}, resolved_at=None,
            updated_at=now(), updated_by="test", binding_revision=1,
        ))
        protected = {name: _digest(conn, table) for name, table in {
            "devices": store.devices, "ssh": store.secrets,
            "snmp": store.protocol_secrets, "bindings": store.driver_bindings,
        }.items()}
        with Operations.context(MigrationContext.configure(conn)):
            import_module("migrations.versions.0011_controller_api").upgrade()
        for name, table in {
            "devices": store.devices, "ssh": store.secrets,
            "snmp": store.protocol_secrets, "bindings": store.driver_bindings,
        }.items():
            assert _digest(conn, table) == protected[name]
        assert conn.execute(sa.select(sa.func.count()).select_from(store.api_controllers)).scalar_one() == 0
        assert conn.execute(sa.select(sa.func.count()).select_from(store.api_controller_secrets)).scalar_one() == 0
        assert conn.execute(sa.select(sa.func.count()).select_from(store.device_controller_bindings)).scalar_one() == 0
        with Operations.context(MigrationContext.configure(conn)):
            import_module("migrations.versions.0011_controller_api").downgrade()
        remaining = set(sa.inspect(conn).get_table_names())
        assert names.isdisjoint(remaining)
        for name, table in {
            "devices": store.devices, "ssh": store.secrets,
            "snmp": store.protocol_secrets, "bindings": store.driver_bindings,
        }.items():
            assert _digest(conn, table) == protected[name]
    store.engine.dispose()
