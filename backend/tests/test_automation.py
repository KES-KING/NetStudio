"""Deterministic contracts; these tests do not claim physical-device acceptance."""
from datetime import timedelta
import time

import asyncssh
import pytest
import sqlalchemy as sa

from app.collection import ReadResult, metadata, persist
from app.contracts import PollingSettings, Telemetry
from app.database import now
from app.drivers import parse_text
from app.driver_catalog import GROUPS, VERSION
from app.history import rollup
from app.models import Job
from app.queue import claim, enqueue, finish, owned
from app.scheduler import advance
from app.snmp import parse_if_mib
from app.ssh import ConnectionPolicyError
from app.ssh_profiles import attempt_profiles, options_for, target_signature
from app.structured_parsers import junos_interfaces, nxos_interfaces, parse_structured, xml
from app.telemetry import ingest, normalize
from conftest import add_device, inventory, login, prepare
from test_cisco import OUTPUTS, ios_server
from test_ssh import ssh_server


def wait(client, identifier):
    for _ in range(150):
        job = client.get(f"/api/v1/jobs/{identifier}").json()
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(.04)
    pytest.fail("Job did not terminate")


def test_profile_catalog_enforces_per_device_permission(system):
    client, store, _, _ = system
    login(client)
    device = store.get_device(add_device(client, ssh_profile="auto")["id"])
    assert attempt_profiles(device) == ["standard"]
    assert "diffie-hellman-group1-sha1" not in options_for("standard", device)["kex_algs"]
    with pytest.raises(ValueError):
        options_for("legacy_cbc", device)
    allowed = device.model_copy(update={"allow_legacy_ssh": True})
    assert len(attempt_profiles(allowed)) == 4
    assert "diffie-hellman-group1-sha1" in options_for("legacy_cbc", allowed)["kex_algs"]
    assert client.get("/api/v1/ssh-profiles").json()["max_attempts"] == 4


def test_key_discovery_without_credentials_and_single_use_approval(system, ssh_server):
    client, store, _, _ = system
    login(client)
    port, key = ssh_server
    device = add_device(client, ssh_profile="auto", ssh_port=port)
    base = f"/api/v1/devices/{device['id']}"
    response = client.post(base + "/host-key-discoveries")
    assert response.status_code == 202, response.text
    value = response.json()
    assert wait(client, value["job_id"])["status"] == "succeeded"
    candidate = client.get(base + "/host-key-candidates/" + value["candidate_id"]).json()
    assert candidate["fingerprint"] == key.get_fingerprint()
    assert not store.get_device(device["id"]).credential_configured
    assert client.post(base + "/host-key-discoveries").status_code == 429
    assert client.put(base + "/host-key", json={"candidate_id": candidate["id"]}).status_code == 200
    assert client.put(base + "/host-key", json={"candidate_id": candidate["id"]}).status_code == 409


def test_auto_legacy_does_not_retry_wrong_password_or_changed_host_key(system, ios_server):
    client, store, _, _ = system
    login(client)
    port, key, state = ios_server
    device = add_device(client, ssh_profile="auto", allow_legacy_ssh=True, ssh_port=port,
        credentials={"username": "lab", "password": "wrong-password"})
    base = f"/api/v1/devices/{device['id']}"
    discovered = client.post(base + "/host-key-discoveries").json()
    discovery_job = wait(client, discovered["job_id"])
    assert discovery_job["status"] == "succeeded", discovery_job
    assert state["auth_attempts"] == 0
    assert client.put(base + "/host-key", json={"candidate_id": discovered["candidate_id"]}).status_code == 200
    job = wait(client, client.post(base + "/connection-tests").json()["id"])
    assert job["error_code"] == "authentication_failed"
    assert state["auth_attempts"] == 1
    wrong = asyncssh.generate_private_key("ssh-rsa")
    assert client.put(base + "/host-key", json={"public_key": wrong.export_public_key().decode(),
        "fingerprint": wrong.get_fingerprint(), "replace_existing": True}).status_code == 200
    job = wait(client, client.post(base + "/connection-tests").json()["id"])
    assert job["error_code"] == "host_key_changed"
    assert state["auth_attempts"] == 1


def test_candidate_bound_to_user_revision_and_expiry(system):
    client, store, _, _ = system
    login(client)
    device = store.get_device(add_device(client)["id"])
    key = asyncssh.generate_private_key("ssh-ed25519")
    with store.engine.begin() as conn:
        conn.execute(store.host_candidates.insert().values(id="expired", device_id=device.id, user_id="admin",
            connection_revision=1, target_signature=target_signature(device), created_at=now() - timedelta(minutes=20),
            expires_at=now() - timedelta(minutes=10), public_key=key.export_public_key().decode(),
            fingerprint=key.get_fingerprint(), profile="standard", consumed=False))
    assert client.put(f"/api/v1/devices/{device.id}/host-key", json={"candidate_id": "expired"}).status_code == 409


def test_atomic_groups_retain_last_good_time_and_inventory(system):
    client, store, _, _ = system
    login(client)
    original = store.get_device(add_device(client, collector="cisco_ios")["id"])
    parsed = parse_text(original, "cisco_ios", OUTPUTS, {}, set(GROUPS))
    first = persist(store, original, parsed)
    assert first["interfaces"] and len(store.get_device(original.id).physical_ports) == 3
    current = store.get_device(original.id)
    failed = ReadResult(current, metadata={"fast": metadata("fast", "cisco_ios", quality="parse_error",
        reason="collector_parse_failed", complete=False)})
    second = persist(store, current, failed)
    from app.telemetry import projection
    assert projection(current, second)["data_state"] == "error"
    assert second["groups"]["fast"]["observed_at"] == first["groups"]["fast"]["observed_at"]
    assert second["observed_at"] == first["observed_at"]
    assert second["groups"]["fast"]["quality"] == "parse_error"
    assert len(store.get_device(original.id).physical_ports) == 3
    def fence(conn):
        raise ConnectionPolicyError("worker_lease_lost")
    with pytest.raises(ConnectionPolicyError):
        persist(store, current, parsed, fence=fence)
    assert store.latest(original.id) == second


def test_bad_health_does_not_discard_valid_ports(system):
    client, store, _, _ = system
    login(client)
    device = store.get_device(add_device(client, collector="cisco_ios")["id"])
    result = parse_text(device, "cisco_ios", {**OUTPUTS,
        "show processes cpu": "CPU utilization for five seconds: 110%"}, {}, set(GROUPS))
    assert result.metadata["health"].quality == "parse_error"
    assert result.metadata["fast"].quality == "ok"
    assert len(result.device.physical_ports) == 3
    data = persist(store, device, result)
    assert len(data["interfaces"]) == 4


def test_lldp_management_ip_is_preserved_without_mac_or_name_guessing(system):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, collector="cisco_ios")["id"])
    raw = """Local Intf: Gi1/0/1
Chassis id: 0200.0000.0099
Port id: eth0
Management Addresses:
    IP: 192.0.2.99
Total entries displayed: 1
"""
    result = parse_text(device, "cisco_ios", {**OUTPUTS, "show lldp neighbors detail": raw}, {}, set(GROUPS))
    neighbor = result.payloads["network"]["neighbors"][0]
    assert neighbor["label"] == "0200.0000.0099"
    assert neighbor["addresses"] == ["192.0.2.99"]
    assert neighbor["remote_device_id"] is None  # IPs do not invent inventory identity/cables.


def test_complete_endpoint_table_refreshes_despite_optional_network_failure(system):
    client, store, *_ = system
    login(client)
    original = store.get_device(add_device(client, collector="cisco_ios")["id"])
    parsed = parse_text(original, "cisco_ios", OUTPUTS, {}, set(GROUPS))
    first = persist(store, original, parsed)
    current = store.get_device(original.id)
    changed = {**OUTPUTS, "show arp": OUTPUTS["show arp"].replace("192.0.2.11", "192.0.2.12")}
    partial = parse_text(current, "cisco_ios", changed,
        {"show lldp neighbors detail": "collector_command_unsupported"}, {"fast", "network"})
    second = persist(store, current, partial)
    assert second["groups"]["network"]["quality"] == "partial"
    assert second["groups"]["network"]["observed_at"] == first["groups"]["network"]["observed_at"]
    assert second["endpoints"]["entries"][0]["addresses"] == ["192.0.2.12"]
    assert second["endpoints"]["observed_at"] > first["endpoints"]["observed_at"]
    from app.telemetry import projection
    assert projection(current, second)["endpoints"]["entries"][0]["resolution"]["status"] == "observed"
    current = store.get_device(original.id)
    broken = parse_text(current, "cisco_ios", {**changed, "show arp": "unrecognized table"}, {}, {"fast", "network"})
    third = persist(store, current, broken)
    assert third["endpoints"] == second["endpoints"]  # Partial table never erases last complete table.
    assert projection(current, third)["endpoints"]["entries"][0]["resolution"]["status"] == "stale"


def test_valid_lldp_management_ip_refreshes_when_an_unrelated_command_is_unsupported(system):
    client, store, *_ = system
    login(client)
    original = store.get_device(add_device(client, collector="cisco_ios")["id"])
    first = persist(store, original, parse_text(original, "cisco_ios", OUTPUTS, {}, set(GROUPS)))
    current = store.get_device(original.id)
    raw = "Local Intf: Gi1/0/1\nChassis id: 0200.0000.0099\nPort id: eth0\nManagement Addresses:\n    IP: 192.0.2.99\nTotal entries displayed: 1\n"
    result = parse_text(current, "cisco_ios", {**OUTPUTS, "show lldp neighbors detail": raw},
        {"show interfaces switchport": "collector_command_unsupported"}, {"network", "fast"})
    second = persist(store, current, result)
    assert second["groups"]["network"]["quality"] == "partial"
    assert second["groups"]["network"]["observed_at"] == first["groups"]["network"]["observed_at"]
    assert second["neighbors"][0]["addresses"] == ["192.0.2.99"]
    assert second["neighbors"][0]["observed_at"] > first["groups"]["network"]["observed_at"]
    from app.endpoint_resolution import network_clock
    assert network_clock(second, now(), neighbor=second["neighbors"][0])[1]


def test_status_parse_error_does_not_poison_other_command_capabilities(system):
    client, store, _, _ = system
    login(client)
    device = store.get_device(add_device(client, collector="cisco_ios")["id"])
    unavailable = {}
    result = parse_text(device, "cisco_ios", {**OUTPUTS, "show interfaces status": "bad table"},
                        unavailable, set(GROUPS))
    assert unavailable == {"show interfaces status": "collector_parse_failed"}
    assert result.metadata["fast"].diagnostics == {"show interfaces status": "parse_error"}
    assert result.metadata["fast"].quality == "parse_error"
    assert result.metadata["health"].quality == "ok"


def test_new_driver_rechecks_old_negative_capabilities(system, ios_server):
    from hashlib import sha256
    from test_cisco import wait_job
    client, store, _, _ = system
    login(client)
    port, key, state = ios_server
    device = add_device(client, collector="cisco_ios", ssh_profile="huawei_legacy", legacy_ssh_confirmed=True,
        ssh_port=port, credentials={"username": "lab", "password": "lab-secret"})
    base = f"/api/v1/devices/{device['id']}"
    assert client.put(base + "/host-key", json={
        "public_key": key.export_public_key().decode(), "fingerprint": key.get_fingerprint()}).status_code == 200
    current = store.get_device(device["id"])
    assert VERSION != "2026.10.20.1"
    previous = sha256(f"{current.connection_revision}:cisco_ios:2026.10.20.1:{current.os_version}".encode()).hexdigest()
    with store.engine.begin() as conn:
        for command in ("show interfaces", "show interfaces status", "show version", "show inventory"):
            conn.execute(store.capabilities.insert().values(device_id=current.id, command_id=command,
                revision_key=previous, status="collector_parse_failed", checked_at=now()))
    job = wait_job(client, device)
    assert job["result"]["groups"]["fast"]["quality"] == "ok"
    assert {"show interfaces", "show interfaces status", "show version", "show inventory"} <= set(state["commands"])
    with store.engine.connect() as conn:
        cached = dict(conn.execute(sa.select(store.capabilities.c.command_id, store.capabilities.c.status)
            .where(store.capabilities.c.device_id == current.id)).all())
    assert not {"show interfaces", "show interfaces status", "show version"} & cached.keys()
    assert cached["show inventory"] == "collector_command_unsupported"


def test_failed_channel_change_keeps_original_sample_provenance(system):
    client, store, _, _ = system
    login(client)
    device = store.get_device(prepare(client)["id"])
    first = ReadResult(device, payloads={"fast": {"interfaces": [
        {"interface_id": "if1", "in_octets": 100, "out_octets": 200, "source": "snmp"}]}},
        metadata={"fast": metadata("fast", "snmp_if_mib", source="snmp")})
    previous = persist(store, device, first)
    failed = ReadResult(device, metadata={"fast": metadata("fast", "cisco_ios",
        quality="parse_error", complete=False, reason="collector_parse_failed")})
    current = persist(store, device, failed)
    assert current["source"] == current["groups"]["fast"]["source"] == "snmp"
    assert current["groups"]["fast"]["attempted_source"] == "ssh"
    assert current["groups"]["fast"]["driver"] == "snmp_if_mib"
    assert current["observed_at"] == previous["observed_at"]


def test_automatic_counters_reset_after_newer_external_source(system):
    client, store, _, _ = system
    login(client)
    device = store.get_device(prepare(client)["id"])
    def reading(octets, at):
        details = metadata("fast", "snmp_if_mib", source="snmp")
        details.observed_at = at
        return ReadResult(device, payloads={"fast": {"interfaces": [{
            "interface_id": "if1", "in_octets": octets, "out_octets": octets,
            "source": "snmp", "counter_bits": 64, "counter_epoch_known": True, "discontinuity": "same-epoch"}]}},
            metadata={"fast": details})
    persist(store, device, reading(100, now() - timedelta(seconds=60)))
    ingest(store, device, Telemetry(observed_at=now() - timedelta(seconds=30), source="manual",
        interfaces=[{"interface_id": "if1", "in_octets": 900, "out_octets": 900,
                     "counter_bits": 64, "counter_epoch_known": True, "discontinuity": "same-epoch"}]))
    current = persist(store, device, reading(300, now()))
    assert current["interfaces"][0]["rx_bps"] is None
    assert current["interfaces"][0]["rate_reason"] == "counter_source_changed"


def test_lease_fencing_and_global_slots_without_inline_worker(system, monkeypatch):
    client, store, app, _ = system
    login(client)
    # Keep this deterministic: future jobs are only claimed by explicit at=.
    at = now() + timedelta(hours=1)
    jobs = []
    for _ in range(10):
        device = store.get_device(add_device(client)["id"])
        job = enqueue(store, device, "connection_test")
        with store.engine.begin() as conn:
            conn.execute(store.jobs_repository.jobs.update().where(store.jobs_repository.jobs.c.id == job.id).values(next_run_at=at))
        jobs.append(job)
    claimed = [claim(store, "one", at) for _ in range(8)]
    assert all(claimed) and claim(store, "two", at) is None
    reclaimed = claim(store, "two", at + timedelta(seconds=31))
    assert reclaimed is not None
    with store.engine.begin() as conn, pytest.raises(ConnectionPolicyError):
        owned(store, reclaimed, "one", conn, at + timedelta(seconds=32))


def test_legacy_in_memory_job_can_be_replaced_without_inventing_authority(system):
    client, store, _, _ = system
    login(client)
    device = store.get_device(add_device(client)["id"])
    legacy = Job(kind="connection_test", device_id=device.id, requested_by="old-api-user",
                 status="running", lease_owner=None, lease_expires_at=None)
    with store.engine.begin() as conn:
        conn.execute(store.jobs_repository.jobs.insert().values(**legacy.model_dump()))
    replacement = enqueue(store, device, "connection_test")
    assert replacement.id != legacy.id
    old = store.jobs_repository.get(legacy.id)
    assert old.status == "cancelled" and old.result_code == "legacy_job_requires_retry"


def test_running_fast_read_coalesces_one_full_follow_up(system):
    client, store, _, _ = system
    login(client)
    device = store.get_device(add_device(client)["id"])
    first = enqueue(store, device, "inventory_read", groups=["fast"])
    future = now() + timedelta(hours=1)
    with store.engine.begin() as conn:
        conn.execute(store.jobs_repository.jobs.update().where(store.jobs_repository.jobs.c.id == first.id)
            .values(next_run_at=future))
    running = claim(store, "test-owner", future)
    assert running.id == first.id
    full = enqueue(store, device, "inventory_read", groups=GROUPS)
    repeated = enqueue(store, device, "inventory_read", groups=["health", "network"])
    assert full.id == repeated.id != first.id
    assert claim(store, "another-owner", future + timedelta(seconds=1)) is None
    with store.engine.connect() as conn:
        assert set(conn.execute(sa.select(store.job_contexts.c.groups).where(
            store.job_contexts.c.job_id == full.id)).scalar_one()) == set(GROUPS)


def test_scheduler_100_devices_virtual_24h_bounds():
    settings = PollingSettings().model_dump()
    start = now() - timedelta(days=2)
    for device in range(100):
        state = {}
        at = start
        cycles = 0
        while at < start + timedelta(days=1):
            state = advance(settings, state, ["fast"], 4 if device < 90 else 20,
                            cpu=20, legacy=device >= 90, at=at, seed=str(device))
            next_at = __import__("datetime").datetime.fromisoformat(state["next"]["fast"])
            assert (next_at - at).total_seconds() >= (30 if device < 90 else 100)
            assert state["duration_ema"] / (next_at - at).total_seconds() <= .2
            at, cycles = next_at, cycles + 1
        assert cycles <= 2880


def test_cpu_backoff_and_recovery():
    settings = PollingSettings().model_dump()
    state = {}
    for _ in range(2):
        state = advance(settings, state, ["fast"], 1, cpu=90)
        state = advance(settings, state, ["fast"], 1)
    assert state["load_factor"] == 2
    for _ in range(5):
        state = advance(settings, state, ["fast"], 1, cpu=20)
    assert state["load_factor"] == 1
    for _ in range(12):
        state = advance(settings, state, ["fast"], 1, error="connection_failed")
    assert state["backoff_seconds"] == 1800


def test_snmp_identity_discontinuity_and_source_transition(system):
    client, store, _, _ = system
    login(client)
    device = store.get_device(prepare(client)["id"])
    columns = {"name": {71: "eth1"}, "in_octets": {71: 1000}, "out_octets": {71: 2000},
               "discontinuity": {71: 0}, "admin_up": {71: 1}, "oper_up": {71: 1}}
    first, complete = parse_if_mib(device, columns, 1000)
    assert not complete and first["interfaces"][0]["interface_id"] == "if1"
    second, _ = parse_if_mib(device, columns, 2000, first)
    assert second["snmp_epoch"] == first["snmp_epoch"]
    reset, _ = parse_if_mib(device, columns, 100, second)
    assert reset["snmp_epoch"] != first["snmp_epoch"]
    old = Telemetry(observed_at=now() - timedelta(seconds=30), source="ssh", interfaces=first["interfaces"]).model_dump(mode="json")
    old["interfaces"][0]["source"] = "ssh"
    batch = Telemetry(observed_at=now(), source="snmp", interfaces=second["interfaces"])
    assert normalize(batch, old)["interfaces"][0]["rate_reason"] == "counter_source_changed"


def test_rollup_missing_periods_are_not_zero():
    at = now().replace(second=0, microsecond=0)
    result = rollup([(at, {"health": {"cpu_percent": 40}, "stale_after_seconds": 30}),
                     (at + timedelta(seconds=90), {"health": {"cpu_percent": 80}, "stale_after_seconds": 30}),
                     (at + timedelta(seconds=120), {})], at)
    assert result["cpu_percent"] == {"mean": 60, "min": 40, "max": 80, "valid_seconds": 60, "coverage_ratio": .2}


def test_structured_parser_rejects_entities_and_preserves_logical_identity():
    raw = "<rpc-reply><interface-information><physical-interface><name>ge-0/0/0</name><admin-status>up</admin-status><oper-status>up</oper-status><speed>1000mbps</speed><logical-interface><name>ge-0/0/0.0</name></logical-interface></physical-interface></interface-information></rpc-reply>"
    entries = junos_interfaces(xml(raw))
    assert entries[0]["physical"] and not entries[1]["physical"]
    assert entries[0]["sample"]["capacity_bps"] == 1_000_000_000
    with pytest.raises(Exception):
        xml('<!DOCTYPE x [<!ENTITY x SYSTEM "file:///etc/passwd">]><x>&x;</x>')
    rows = nxos_interfaces({"TABLE_interface": {"ROW_interface": {"interface": "Ethernet1/1", "state": "up", "eth_inbytes": "4"}}})
    assert rows[0]["sample"]["in_octets"] == 4


def test_structured_health_failure_isolated_from_inventory(system):
    client, store, _, _ = system
    login(client)
    device = store.get_device(add_device(client, collector="juniper_junos")["id"])
    outputs = {
        "show interfaces extensive | display xml": (
            "<rpc-reply><interface-information><physical-interface><name>ge-0/0/0</name>"
            "<admin-status>up</admin-status><oper-status>up</oper-status><speed>1000mbps</speed>"
            "</physical-interface></interface-information></rpc-reply>"),
        "show chassis routing-engine | display xml": (
            "<rpc-reply><route-engine><cpu-idle>invalid</cpu-idle></route-engine></rpc-reply>"),
    }
    result = parse_structured(device, "juniper_junos", outputs, {}, {"fast", "health"})
    assert result.metadata["fast"].quality == "ok"
    assert result.metadata["health"].quality == "parse_error"
    assert result.inventory_complete and len(result.device.physical_ports) == 1
    assert persist(store, device, result)["interfaces"]


def test_snmp_secrets_encrypted_and_permissions(system):
    client, store, _, _ = system
    login(client)
    device = add_device(client)
    path = f"/api/v1/devices/{device['id']}/snmp-credentials"
    value = {"username": "testuser", "auth_password": "not-a-real-auth", "privacy_password": "not-a-real-privacy"}
    assert client.put(path, json=value).status_code == 200
    assert store.get_device(device["id"]).snmp_configured
    with store.engine.connect() as conn:
        row = conn.execute(sa.select(store.protocol_secrets)).mappings().one()
        assert value["auth_password"].encode() not in row["ciphertext"]
        assert "auth_password" not in row["metadata"]
    login(client, "viewer")
    assert client.put(path, json=value).status_code == 404


def test_system_job_survives_browser_logout(system, ssh_server):
    client, store, _, _ = system
    login(client)
    port, key = ssh_server
    device = add_device(client, collector="linux_ssh", ssh_port=port,
                        credentials={"username": "lab", "password": "lab-secret"})
    base = f"/api/v1/devices/{device['id']}"
    assert client.put(base + "/host-key", json={"public_key": key.export_public_key().decode(),
        "fingerprint": key.get_fingerprint()}).status_code == 200
    device = store.get_device(device["id"])
    job = enqueue(store, device, "inventory_read", policy_version=1)
    assert client.post("/api/v1/session/logout").status_code == 200
    for _ in range(150):
        current = store.jobs_repository.get(job.id)
        if current.status not in {"queued", "running"}:
            break
        time.sleep(.04)
    # This lab intentionally does not implement the optional neighbour command.
    # A successful fast group must survive logout, with the missing group visible.
    assert current.status == "partial", current
    data = store.latest(device.id)
    assert data["interfaces"]
    assert data["groups"]["fast"]["quality"] == "ok"
    assert data["groups"]["network"]["diagnostics"]["endpoints"] == "parse_error"
