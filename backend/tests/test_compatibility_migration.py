"""S02 migration preservation and optional disposable PostgreSQL proof."""
from importlib import import_module
import json
import os
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa

from app.contracts import ManagedDevice
from app.database import Store, now
from app.fixtures import build_fixture


def _digest_rows(conn, table):
    rows = [dict(row) for row in conn.execute(sa.select(table)).mappings()]
    return json.dumps(rows, sort_keys=True, default=str, separators=(",", ":"))


@pytest.mark.parametrize(("collector", "profile_id"), [
    ("huawei_vrp", "huawei_vrp_v200"),
    ("dell_force10", "dell_os9"),
    ("extreme_vsp", "extreme_fabric_engine"),
])
def test_conditional_legacy_backfill_never_guesses_without_os_evidence(
    collector, profile_id
):
    migration = import_module("migrations.versions.0010_driver_acceptance")
    payload = {"id": "legacy", "collector": collector, "os_version": ""}
    binding = migration._binding(payload, now())
    assert binding["configured_profile_id"] == profile_id
    assert binding["resolved_profile_id"] is None
    assert binding["resolution_status"] == "manual_resolution_required"
    assert binding["resolution_conflicts"] == ["identity_evidence_required"]


def test_fortinet_backfill_has_no_automatic_canonical_target():
    migration = import_module("migrations.versions.0010_driver_acceptance")
    binding = migration._binding({
        "id": "legacy", "collector": "fortinet",
        "vendor": "Fortinet", "os_version": "FortiSwitchOS 7.4",
    }, now())
    assert binding["configured_profile_id"] is None
    assert binding["resolved_profile_id"] is None
    assert binding["resolution_status"] == "manual_resolution_required"


def test_0010_backfill_preserves_payload_secrets_host_keys_jobs_and_probe(tmp_path):
    store = Store(f"sqlite+pysqlite:///{tmp_path / 'compatibility.db'}")
    new_names = set(import_module("app.compatibility_schema_v1").define_tables(sa.MetaData()))
    new_tables = {getattr(store, name) for name in new_names}
    store.meta.create_all(
        store.engine,
        tables=[table for table in store.meta.sorted_tables if table not in new_tables],
    )
    fixture = build_fixture().model_copy(update={
        "id": "legacy-fortinet", "support_status": "generic_readonly",
    })
    device = ManagedDevice.model_validate({
        **fixture.model_dump(), "collector": "fortinet", "resolved_collector": None,
    })
    with store.engine.begin() as conn:
        store.save_device(device, conn)
        conn.execute(store.secrets.insert().values(
            device_id=device.id, key_id="existing", nonce=b"nonce-before",
            ciphertext=b"ciphertext-before",
        ))
        conn.execute(store.host_keys.insert().values(
            device_id=device.id, public_key="ssh-ed25519 existing",
            fingerprint="SHA256:existing",
        ))
        conn.execute(store.protocol_secrets.insert().values(
            device_id=device.id, protocol="snmp", metadata={"port": 161},
            key_id="existing", nonce=b"snmp-nonce-before",
            ciphertext=b"snmp-ciphertext-before",
        ))
        observed = now()
        conn.execute(store.telemetry.insert().values(
            id="telemetry-before", device_id=device.id, observed_at=observed,
            received_at=observed, payload={"observed_at": observed.isoformat()},
        ))
        conn.execute(store.collection_groups.insert().values(
            device_id=device.id, group_name="inventory",
            payload={"physical_ports": [port.id for port in device.physical_ports]},
            metadata={"source": "legacy"}, content_hash="e" * 64,
        ))
        conn.execute(store.collection_history.insert().values(
            id="history-before", device_id=device.id, group_name="inventory",
            observed_at=observed,
            payload={"physical_ports": [port.id for port in device.physical_ports]},
        ))
        conn.execute(store.jobs_repository.jobs.insert().values(
            id=uuid4(), kind="inventory_read", device_id=device.id,
            status="failed", requested_by="legacy-user", created_at=now(),
            next_run_at=now(), priority=100, attempt=1, max_attempts=3,
        ))
        conn.execute(store.network_probe_agents.insert().values(
            id="probe-before", name="Probe", site="lab", token_hash="b" * 64,
            enabled=True, interfaces=[], enrolled_at=now(), last_seen_at=now(),
            bootstrap_id="bootstrap-before",
        ))
        protected = {
            name: _digest_rows(conn, table) for name, table in {
                "devices": store.devices, "secrets": store.secrets,
                "host_keys": store.host_keys,
                "protocol_secrets": store.protocol_secrets,
                "telemetry": store.telemetry,
                "collection_groups": store.collection_groups,
                "collection_history": store.collection_history,
                "jobs": store.jobs_repository.jobs,
                "probe": store.network_probe_agents,
            }.items()
        }
        migration = import_module("migrations.versions.0010_driver_acceptance")
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        for name, table in {
            "devices": store.devices, "secrets": store.secrets,
            "host_keys": store.host_keys,
            "protocol_secrets": store.protocol_secrets,
            "telemetry": store.telemetry,
            "collection_groups": store.collection_groups,
            "collection_history": store.collection_history,
            "jobs": store.jobs_repository.jobs,
            "probe": store.network_probe_agents,
        }.items():
            assert _digest_rows(conn, table) == protected[name]
        binding = conn.execute(sa.select(store.driver_bindings)).mappings().one()
        assert binding["device_id"] == device.id
        assert binding["configured_profile_id"] is None
        assert binding["resolution_status"] == "manual_resolution_required"
        assert binding["identity_evidence"] == {
            "vendor": device.vendor, "model": device.model,
            "os_version": device.os_version,
        }
        assert conn.execute(sa.select(sa.func.count()).select_from(
            store.capability_observations_v2
        )).scalar_one() == 0
        assert conn.execute(sa.select(sa.func.count()).select_from(
            store.driver_acceptance
        )).scalar_one() == 0
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        assert not {
            "device_driver_bindings", "device_capability_observations_v2",
            "driver_acceptance_records",
        } & set(sa.inspect(conn).get_table_names())
        for name, table in {
            "devices": store.devices, "secrets": store.secrets,
            "host_keys": store.host_keys,
            "protocol_secrets": store.protocol_secrets,
            "telemetry": store.telemetry,
            "collection_groups": store.collection_groups,
            "collection_history": store.collection_history,
            "jobs": store.jobs_repository.jobs,
            "probe": store.network_probe_agents,
        }.items():
            assert _digest_rows(conn, table) == protected[name]
    store.engine.dispose()


def test_0001_to_head_on_disposable_postgres(monkeypatch):
    url = os.getenv("NETSTUDIO_TEST_COMPATIBILITY_DATABASE_URL")
    if not url:
        pytest.skip("Requires a dedicated empty loopback netstudio_compatibility_test_* database")
    target = sa.engine.make_url(url)
    assert target.get_backend_name() == "postgresql"
    assert target.host in {"127.0.0.1", "localhost"}
    assert target.database.startswith("netstudio_compatibility_test_")
    engine = sa.create_engine(url)
    assert not sa.inspect(engine).get_table_names(), "Refusing to modify a non-empty database"
    engine.dispose()

    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("backend/alembic.ini")
    command.upgrade(config, "0001_initial")
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO devices (id,name,management_address,site,vendor,platform,model,serial,read_only,support_status) "
            "VALUES ('from-0001','Old','192.0.2.1','lab','Cisco','cisco_ios','WS-C2960X','','true','generic_readonly')"
        ))
        conn.execute(sa.text(
            "INSERT INTO jobs (id,kind,device_id,status,requested_by,created_at) "
            "VALUES (:id,'inventory_read','from-0001','failed','old',CURRENT_TIMESTAMP)"
        ), {"id": uuid4()})
    command.upgrade(config, "0006_collection_automation")
    store = Store(url)
    fixture = build_fixture().model_copy(update={
        "id": "from-0001", "name": "Old", "management_address": "192.0.2.1",
        "site": "lab", "vendor": "Cisco", "platform": "cisco_ios",
        "model": "WS-C2960X", "support_status": "generic_readonly",
    })
    device = ManagedDevice.model_validate({
        **fixture.model_dump(), "collector": "cisco_ios",
        "resolved_collector": None,
    })
    with store.engine.begin() as conn:
        store.save_device(device, conn)
        conn.execute(store.secrets.insert().values(
            device_id=device.id, key_id="old-key", nonce=b"old-nonce",
            ciphertext=b"old-ciphertext",
        ))
        conn.execute(store.host_keys.insert().values(
            device_id=device.id, public_key="ssh-ed25519 old",
            fingerprint="SHA256:old",
        ))
        conn.execute(store.protocol_secrets.insert().values(
            device_id=device.id, protocol="snmp", metadata={"port": 161},
            key_id="old-key", nonce=b"snmp-nonce", ciphertext=b"snmp-ciphertext",
        ))
        conn.execute(store.collection_groups.insert().values(
            device_id=device.id, group_name="inventory", payload={"model": "WS-C2960X"},
            metadata={"source": "legacy"}, content_hash="c" * 64,
        ))
        observed = now()
        conn.execute(store.telemetry.insert().values(
            id="telemetry-from-0006", device_id=device.id,
            observed_at=observed, received_at=observed,
            payload={"observed_at": observed.isoformat()},
        ))
        conn.execute(store.collection_history.insert().values(
            id="history-from-0006", device_id=device.id,
            group_name="inventory", observed_at=observed,
            payload={"model": "WS-C2960X"},
        ))
    command.upgrade(config, "0009_probe_auto_enroll")
    with store.engine.begin() as conn:
        conn.execute(store.network_probe_agents.insert().values(
            id="probe-from-0009", name="Probe", site="lab", token_hash="d" * 64,
            enabled=True, interfaces=[], enrolled_at=now(), last_seen_at=now(),
            bootstrap_id="bootstrap-from-0009",
        ))
        protected = {
            name: _digest_rows(conn, table) for name, table in {
                "devices": store.devices, "secrets": store.secrets,
                "host_keys": store.host_keys,
                "protocol_secrets": store.protocol_secrets,
                "collection_groups": store.collection_groups,
                "collection_history": store.collection_history,
                "telemetry": store.telemetry,
                "jobs": store.jobs_repository.jobs,
                "probe": store.network_probe_agents,
            }.items()
        }
    command.upgrade(config, "head")
    with engine.connect() as conn:
        assert conn.execute(sa.text(
            "SELECT count(*) FROM devices WHERE id='from-0001'"
        )).scalar_one() == 1
        assert conn.execute(sa.text(
            "SELECT count(*) FROM jobs WHERE device_id='from-0001'"
        )).scalar_one() == 1
        binding = conn.execute(sa.text(
            "SELECT configured_profile_id, resolution_status "
            "FROM device_driver_bindings WHERE device_id='from-0001'"
        )).mappings().one()
        assert binding == {
            "configured_profile_id": "cisco_ios",
            "resolution_status": "unresolved",
        }
        assert conn.execute(sa.text(
            "SELECT version_num FROM alembic_version"
        )).scalar_one() == "0011_controller_api"
        for name, table in {
            "devices": store.devices, "secrets": store.secrets,
            "host_keys": store.host_keys,
            "protocol_secrets": store.protocol_secrets,
            "collection_groups": store.collection_groups,
            "collection_history": store.collection_history,
            "telemetry": store.telemetry,
            "jobs": store.jobs_repository.jobs,
            "probe": store.network_probe_agents,
        }.items():
            assert _digest_rows(conn, table) == protected[name]
        # This is the previous-image read contract: its payload model ignores
        # additive tables and still validates without profile fields.
        payload = conn.execute(sa.select(store.devices.c.payload).where(
            store.devices.c.id == "from-0001"
        )).scalar_one()
        assert ManagedDevice.model_validate(payload).collector == "cisco_ios"
    migrated = Store(url).get_device("from-0001")
    assert migrated.configured_profile_id == "cisco_ios"
    engine.dispose()
