"""S02 API, RBAC, fencing, audit, and redaction contracts."""
from datetime import timedelta
from uuid import UUID

import sqlalchemy as sa
import pytest

from app.collection import ReadResult, persist
from app.database import now
from app.driver_catalog import GROUPS, VERSION
from app.drivers import parse_text
from app.profile_resolution import (
    AcceptanceRecord,
    acceptance_summary,
    save_acceptance_record,
)
from app.ssh import ConnectionPolicyError
from conftest import add_device, login
from test_cisco import OUTPUTS


def test_old_and_canonical_device_payloads_coexist(system):
    client, store, _, _ = system
    login(client)

    legacy = add_device(client, collector="huawei_vrp")
    assert legacy["collector"] == "huawei_vrp"
    assert legacy["configured_profile_id"] == "huawei_vrp_v200"
    assert legacy["profile_resolution_status"] == "manual_resolution_required"

    canonical_response = client.post("/api/v1/devices", json={
        "name": "Canonical switch", "management_address": "127.0.0.1",
        "site": "lab", "configured_profile_id": "cisco_ios",
        "management_mode": "standalone",
    })
    assert canonical_response.status_code == 201, canonical_response.text
    canonical = canonical_response.json()
    assert canonical["collector"] == "cisco_ios"
    assert canonical["configured_profile_id"] == "cisco_ios"
    assert canonical["management_mode"] == "standalone"

    with store.engine.connect() as conn:
        payload = conn.execute(sa.select(store.devices.c.payload).where(
            store.devices.c.id == canonical["id"]
        )).scalar_one()
    assert "configured_profile_id" not in payload
    assert "management_mode" not in payload

    explicit_external = client.post("/api/v1/devices", json={
        "name": "External mismatch", "management_address": "127.0.0.3",
        "site": "lab", "collector": "external",
        "configured_profile_id": "cisco_ios",
        "management_mode": "standalone",
    })
    assert explicit_external.status_code == 409
    assert explicit_external.json()["detail"]["code"] == "driver_profile_collector_conflict"

    catalog_only_response = client.post("/api/v1/devices", json={
        "name": "Catalog only", "management_address": "127.0.0.2",
        "site": "lab", "configured_profile_id": "aruba_aoss",
    })
    assert catalog_only_response.status_code == 409
    assert catalog_only_response.json()["detail"]["code"] == "driver_profile_not_selectable"
    legacy_catalog_only = client.post("/api/v1/devices", json={
        "name": "Legacy bypass", "management_address": "127.0.0.2",
        "site": "lab", "collector": "hp_procurve",
    })
    assert legacy_catalog_only.status_code == 409
    assert legacy_catalog_only.json()["detail"]["code"] == "driver_profile_not_selectable"

    conflict = client.post("/api/v1/devices", json={
        "name": "Conflict", "management_address": "127.0.0.1", "site": "lab",
        "collector": "huawei_vrp", "configured_profile_id": "cisco_ios",
    })
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "driver_profile_collector_conflict"
    auto_conflict = client.post("/api/v1/devices", json={
        "name": "Auto conflict", "management_address": "127.0.0.1",
        "site": "lab", "collector": "auto",
        "configured_profile_id": "cisco_ios",
    })
    assert auto_conflict.status_code == 409
    mode_conflict = client.post("/api/v1/devices", json={
        "name": "Mode conflict", "management_address": "127.0.0.1",
        "site": "lab", "configured_profile_id": "cisco_ios",
        "management_mode": "cloud_managed",
    })
    assert mode_conflict.status_code == 409
    assert mode_conflict.json()["detail"]["code"] == "driver_profile_management_mode_conflict"


def test_compatibility_is_site_scoped_and_profile_mutation_is_strict(system):
    client, _, _, _ = system
    login(client)
    device = add_device(client, collector="fortinet")
    path = f"/api/v1/devices/{device['id']}"
    view = client.get(path + "/compatibility")
    assert view.status_code == 200
    assert view.json()["resolution_status"] == "manual_resolution_required"

    login(client, "viewer")
    assert client.get(path + "/compatibility").status_code == 200
    assert client.put(path + "/driver-profile", json={
        "configured_profile_id": "fortinet_fortiswitchos"
    }).status_code == 404

    login(client, "outsider")
    assert client.get(path + "/compatibility").status_code == 404

    login(client)
    not_selectable = client.put(path + "/driver-profile", json={
        "configured_profile_id": "fortinet_fortiswitchos"
    })
    assert not_selectable.status_code == 409
    assert not_selectable.json()["detail"]["code"] == "driver_profile_not_selectable"
    connection_bypass = client.put(path + "/connection-settings", json={
        "collector": "fortinet",
        "configured_profile_id": "fortinet_fortiswitchos",
        "management_mode": "standalone",
    })
    assert connection_bypass.status_code == 409
    assert connection_bypass.json()["detail"]["code"] == "driver_profile_not_selectable"
    legacy_connection_bypass = client.put(path + "/connection-settings", json={
        "collector": "hp_procurve",
    })
    assert legacy_connection_bypass.status_code == 409
    assert legacy_connection_bypass.json()["detail"]["code"] == "driver_profile_not_selectable"
    for injected in (
        {"identity_evidence": {"vendor": "Fortinet"}},
        {"validation_level": "physical_validated"},
        {"acceptance": {"production_accepted": True}},
    ):
        response = client.put(path + "/driver-profile", json={
            "configured_profile_id": "fortinet_fortiswitchos", **injected,
        })
        assert response.status_code == 422


def test_profile_change_revisions_fences_jobs_revokes_ssh_and_audits(system, monkeypatch):
    client, store, app, _ = system
    login(client)
    device = add_device(client, collector="cisco_ios")
    before = store.get_device(device["id"])
    jobs = store.jobs_repository.jobs
    with store.engine.begin() as conn:
        conn.execute(jobs.insert().values(
            id=UUID("00000000-0000-0000-0000-000000000111"),
            kind="connection_test", device_id=device["id"], status="queued",
            requested_by="admin", created_at=now(), next_run_at=now() + timedelta(days=1),
            priority=10, attempt=0, max_attempts=3,
        ))
    revoked = []
    monkeypatch.setattr(app.state.ssh, "revoke", lambda **value: revoked.append(value))

    response = client.put(f"/api/v1/devices/{device['id']}/driver-profile", json={
        "configured_profile_id": "juniper_junos", "management_mode": "standalone",
    })
    assert response.status_code == 200, response.text
    assert response.json()["configured_profile_id"] == "juniper_junos"
    after = store.get_device(device["id"])
    assert after.connection_revision == before.connection_revision + 1
    assert after.collector == "juniper_junos"
    assert revoked == [{"device_id": device["id"]}]
    with store.engine.connect() as conn:
        job = conn.execute(sa.select(jobs).where(jobs.c.device_id == device["id"])).mappings().one()
        event = conn.execute(sa.select(store.audit).where(
            store.audit.c.event == "driver.profile.changed"
        )).mappings().one()
    assert job["status"] == "cancelled"
    assert job["result_code"] == "device_connection_changed"
    assert event["details"]["after"]["configured_profile_id"] == "juniper_junos"
    with pytest.raises(ConnectionPolicyError, match="device_connection_changed"):
        persist(store, before, ReadResult(before))
    repeated = client.put(f"/api/v1/devices/{device['id']}/driver-profile", json={
        "configured_profile_id": "juniper_junos", "management_mode": "standalone",
    })
    assert repeated.status_code == 200
    assert store.get_device(device["id"]).connection_revision == after.connection_revision
    assert revoked == [{"device_id": device["id"]}]


def test_profile_change_from_external_selects_the_implemented_runtime(system):
    client, store, _, _ = system
    login(client)
    device = add_device(client, collector="external")
    response = client.put(f"/api/v1/devices/{device['id']}/driver-profile", json={
        "configured_profile_id": "huawei_vrp_v200",
        "management_mode": "standalone",
    })
    assert response.status_code == 200, response.text
    updated = store.get_device(device["id"])
    assert updated.collector == "huawei_vrp"
    assert updated.configured_profile_id == "huawei_vrp_v200"
    assert updated.connection_revision == device["connection_revision"] + 1


def test_acceptance_reads_are_redacted_and_do_not_promote_catalog_release(
    system, monkeypatch
):
    client, store, _, _ = system
    login(client)
    at = now()
    record = AcceptanceRecord(
        source_revision="f" * 40,
        profile_id="cisco_ios", profile_revision=2,
        vendor="Cisco", model_family="WS-C2960X-*",
        exact_model="WS-C2960X-48FPD-L", hardware_revision="V02",
        os_family="IOS", os_version="15.2(7)E",
        management_mode="standalone", transport="ssh",
        security_profile="ssh2_host_key_pinned",
        capability_id="interfaces", validation_level="physical_validated",
        parser_version=VERSION, test_suite_revision="compat-physical-v1",
        result="pass", evidence_ref="/private/lab/customer-a/report.json",
        evidence_sha256="a" * 64, evidence_sanitized=True,
        observed_at=at - timedelta(minutes=5), recorded_at=at,
        expires_at=at + timedelta(days=30), reviewed_by="private-reviewer",
    )
    with store.engine.begin() as conn:
        save_acceptance_record(store, record, actor="system:release", conn=conn)

    device = store.get_device(add_device(
        client, collector="cisco_ios", vendor="Cisco",
        model="WS-C2960X-48FPD-L",
    )["id"]).model_copy(update={
        "os_version": "15.2(7)E", "driver_version": VERSION,
        "management_mode": "standalone",
    })
    monkeypatch.setenv("NETSTUDIO_BUILD_REVISION", "f" * 40)
    evidence = {
        "vendor": "Cisco", "model": "WS-C2960X-48FPD-L",
        "hardware_revision": "V02", "os_family": "IOS",
        "os_version": "15.2(7)E",
    }
    matched = acceptance_summary(
        store, "cisco_ios", 2, device=device, identity_evidence=evidence
    )
    assert matched == {
        "highest_level": "physical_validated",
        "matching_unexpired_records": 1,
        "production_accepted": False,
    }
    wrong_mode = acceptance_summary(
        store, "cisco_ios", 2,
        device=device.model_copy(update={"management_mode": "unknown"}),
        identity_evidence=evidence,
    )
    assert wrong_mode["matching_unexpired_records"] == 0
    assert acceptance_summary(
        store, "cisco_ios", 2, device=device,
        identity_evidence={**evidence, "hardware_revision": "V03"},
    )["matching_unexpired_records"] == 0

    public_catalog = client.get("/api/v1/driver-catalog").json()
    profile = next(item for item in public_catalog["profiles"] if item["id"] == "cisco_ios")
    assert profile["acceptance"]["matching_unexpired_records"] == 1
    assert profile["acceptance"]["production_accepted"] is False
    monkeypatch.setenv("NETSTUDIO_BUILD_REVISION", "e" * 40)
    stale_profile = next(
        item for item in client.get("/api/v1/driver-catalog").json()["profiles"]
        if item["id"] == "cisco_ios"
    )
    assert stale_profile["acceptance"]["matching_unexpired_records"] == 0
    assert stale_profile["acceptance"]["production_accepted"] is False

    detail = client.get("/api/v1/driver-acceptance").json()["items"][0]
    assert detail["evidence_sha256"] == "a" * 64
    assert "evidence_ref" not in detail
    assert "reviewed_by" not in detail
    assert "/private/" not in str(detail)

    login(client, "viewer")
    assert client.get("/api/v1/driver-acceptance").status_code == 403


def test_successful_collection_resolves_profile_and_writes_capability_evidence(system):
    client, store, _, _ = system
    login(client)
    device = store.get_device(add_device(client, collector="cisco_ios")["id"])
    result = parse_text(device, "cisco_ios", OUTPUTS, {}, set(GROUPS))
    result.device = result.device.model_copy(update={
        "resolved_collector": "cisco_ios", "driver_version": VERSION,
    })
    persist(store, device, result)

    binding = store.get_driver_binding(device.id)
    assert binding["resolution_status"] == "matched"
    assert binding["resolved_profile_id"] == "cisco_ios"
    assert binding["identity_evidence"]["os_family"] == "IOS"
    with store.engine.connect() as conn:
        capabilities = list(conn.execute(sa.select(
            store.capability_observations_v2
        )).mappings())
        event = conn.execute(sa.select(store.audit).where(
            store.audit.c.event == "driver.profile.resolved"
        )).mappings().one()
    assert {row["capability_id"] for row in capabilities} == set(result.metadata)
    assert all(len(row["evidence_digest"]) == 64 for row in capabilities)
    assert event["outcome"] == "matched"
