import struct
from datetime import timedelta

from fastapi import HTTPException
import pytest
import sqlalchemy as sa

from app.database import now
from app.network_probe import target_networks
from app.network_probe_agent import build_arp_request, parse_arp_reply
from conftest import login, observation, prepare


MAC = "02:00:00:00:00:11"


def arp_reply(sender_mac=MAC, sender_ip="198.51.100.101", target_mac="02:00:00:00:fe:10",
              target_ip="198.51.100.254", ethernet_source=None):
    sender = bytes.fromhex(sender_mac.replace(":", ""))
    target = bytes.fromhex(target_mac.replace(":", ""))
    ethernet_source = bytes.fromhex((ethernet_source or sender_mac).replace(":", ""))
    return (target + ethernet_source + struct.pack("!H", 0x0806)
        + struct.pack("!HHBBH", 1, 0x0800, 6, 4, 2) + sender
        + bytes(map(int, sender_ip.split("."))) + target + bytes(map(int, target_ip.split("."))))


def test_arp_frames_reject_spoofed_or_out_of_scope_replies():
    request = build_arp_request("02:00:00:00:fe:10", "198.51.100.254", "198.51.100.101")
    assert len(request) == 42 and request[:6] == b"\xff" * 6 and request[20:22] == b"\x00\x01"
    expected = parse_arp_reply(arp_reply(), "02:00:00:00:fe:10", "198.51.100.254", {"198.51.100.101"})
    assert expected == (MAC, "198.51.100.101")
    assert parse_arp_reply(arp_reply(ethernet_source="02:00:00:00:00:12"),
        "02:00:00:00:fe:10", "198.51.100.254", {"198.51.100.101"}) is None


def test_target_ranges_enforce_prefix_overlap_and_total_budget():
    proposal = {"network": "10.0.0.0/19"}
    with pytest.raises(HTTPException) as too_wide:
        target_networks(["10.0.0.0/21"], proposal)
    assert too_wide.value.detail["code"] == "invalid_probe_target_cidr"
    with pytest.raises(HTTPException) as overlap:
        target_networks(["10.0.0.0/22", "10.0.0.0/23"], proposal)
    assert overlap.value.detail["code"] == "overlapping_probe_targets"
    with pytest.raises(HTTPException) as too_many:
        target_networks(["10.0.0.0/22", "10.0.4.0/22", "10.0.8.0/22", "10.0.12.0/22", "10.0.16.0/22"], proposal)
    assert too_many.value.detail["code"] == "probe_target_budget_exceeded"
    assert parse_arp_reply(arp_reply(sender_ip="198.51.100.102"),
        "02:00:00:00:fe:10", "198.51.100.254", {"198.51.100.101"}) is None


def setup_probe(system):
    client, store, _, _ = system
    login(client)
    device = prepare(client)
    at = now()
    payload = observation(at, interfaces=[
        {"interface_id": "if1", "admin_up": True, "oper_up": True},
        {"interface_id": "if5", "admin_up": True, "oper_up": True,
         "addresses": ["198.51.100.1/24"], "l3_vlan": 10, "vrf_known": True}],
        endpoints={"status": "ok", "observed_at": at.isoformat(), "stale_after_seconds": 1800, "entries": [
            {"id": "fdb", "interface_id": "if1", "mac": MAC, "addresses": [], "vlan": 10,
             "vrf_known": False, "discovery": "fdb", "evidence": "test FDB"},
            {"id": "arp", "interface_id": "if5", "mac": MAC, "addresses": ["198.51.100.99"], "vlan": 10,
             "vrf_known": True, "discovery": "arp", "evidence": "test switch ARP"}]})
    response = client.post(f"/api/v1/devices/{device['id']}/observations", json=payload)
    assert response.status_code == 201, response.text
    enrollment = client.post("/api/v1/network-probes/enrollments", json={"name": "Probe 10", "site": "lab"})
    assert enrollment.status_code == 201, enrollment.text
    token = enrollment.json()["enrollment_token"]
    enrolled = client.post("/api/v1/network-probe-agent/enroll", headers={"authorization": f"Bearer {token}"})
    assert enrolled.status_code == 201, enrolled.text
    assert client.post("/api/v1/network-probe-agent/enroll",
        headers={"authorization": f"Bearer {token}"}).status_code == 401
    agent_token, agent_id = enrolled.json()["agent_token"], enrolled.json()["agent_id"]
    heartbeat = client.post("/api/v1/network-probe-agent/heartbeat", headers={"authorization": f"Bearer {agent_token}"},
        json={"interfaces": [{"name": "probe.10", "mac": "02:00:00:00:fe:10", "addresses": ["198.51.100.254/24"]}]})
    assert heartbeat.status_code == 200, heartbeat.text
    state = client.get("/api/v1/network-probes").json()
    proposal = next(item for item in state["proposals"] if item["vlan"] == 10)
    scope = client.post("/api/v1/network-probes/scopes", json={"proposal_id": proposal["id"], "agent_id": agent_id,
        "interface_name": "probe.10", "source_ip": "198.51.100.254", "target_cidrs": ["198.51.100.0/24"],
        "interval_seconds": 900, "vrf": None, "active_broadcast_acknowledged": True})
    assert scope.status_code == 201, scope.text
    return client, store, device, agent_token, agent_id, scope.json()


def claim_and_complete(client, agent_token, scope, matches, reply_count, unknown_count=0):
    queued = client.post(f"/api/v1/network-probes/scopes/{scope['id']}/runs")
    assert queued.status_code == 202, queued.text
    task = client.post("/api/v1/network-probe-agent/tasks/claim",
        headers={"authorization": f"Bearer {agent_token}"}).json()
    at = now()
    result = client.post(f"/api/v1/network-probe-agent/tasks/{task['id']}/result",
        headers={"authorization": f"Bearer {agent_token}"}, json={"lease_token": task["lease_token"],
        "status": "succeeded", "started_at": (at - timedelta(seconds=1)).isoformat(), "completed_at": at.isoformat(),
        "target_count": task["target_count"], "reply_count": reply_count, "unknown_count": unknown_count,
        "duration_ms": 1000, "matches": matches, "error_code": None})
    assert result.status_code == 200, result.text
    return task


def test_active_probe_api_resolution_precedence_and_switch_fallback(system):
    client, store, device, token, agent_id, scope = setup_probe(system)
    claim_and_complete(client, token, scope, [
        {"mac": MAC, "address": "198.51.100.101"},
        {"mac": "02:00:00:00:00:22", "address": "198.51.100.102"}], reply_count=2, unknown_count=1)
    with store.engine.connect() as conn:
        observations = conn.execute(sa.select(store.network_probe_observations)).mappings().all()
    assert [(row["mac"], row["address"]) for row in observations] == [(MAC, "198.51.100.101")]
    endpoints = client.get(f"/api/v1/devices/{device['id']}/overview").json()["endpoints"]["entries"]
    fdb = next(item for item in endpoints if item["id"] == "fdb")
    assert fdb["addresses"] == ["198.51.100.101"]
    assert fdb["resolution"]["reason"] == "active_arp_match"
    assert fdb["resolution"]["sources"][0]["discovery"] == "active_arp"

    with store.engine.begin() as conn:
        conn.execute(store.network_probe_scopes.update().where(store.network_probe_scopes.c.id == scope["id"])
            .values(last_manual_at=None))
    claim_and_complete(client, token, scope, [], reply_count=0)
    endpoints = client.get(f"/api/v1/devices/{device['id']}/overview").json()["endpoints"]["entries"]
    fdb = next(item for item in endpoints if item["id"] == "fdb")
    assert fdb["addresses"] == [] and fdb["resolution"]["reason"] == "active_arp_no_reply"

    with store.engine.begin() as conn:
        conn.execute(store.network_probe_agents.update().where(store.network_probe_agents.c.id == agent_id)
            .values(last_seen_at=now() - timedelta(minutes=2)))
    endpoints = client.get(f"/api/v1/devices/{device['id']}/overview").json()["endpoints"]["entries"]
    fdb = next(item for item in endpoints if item["id"] == "fdb")
    assert fdb["addresses"] == ["198.51.100.99"]
    assert fdb["resolution"]["reason"] == "scoped_mac_match"


def test_failed_probe_result_is_retried_once(system):
    client, store, _, token, _, scope = setup_probe(system)
    assert client.post(f"/api/v1/network-probes/scopes/{scope['id']}/runs").status_code == 202
    headers = {"authorization": f"Bearer {token}"}
    first = client.post("/api/v1/network-probe-agent/tasks/claim", headers=headers).json()

    def fail_task(task):
        at = now()
        return client.post(f"/api/v1/network-probe-agent/tasks/{task['id']}/result", headers=headers, json={
            "lease_token": task["lease_token"], "status": "failed",
            "started_at": (at - timedelta(seconds=1)).isoformat(), "completed_at": at.isoformat(),
            "target_count": task["target_count"], "reply_count": 0, "unknown_count": 0,
            "duration_ms": 10, "matches": [], "error_code": "probe_socket_unavailable"})

    retried = fail_task(first)
    assert retried.status_code == 200 and retried.json()["status"] == "retrying"
    second = client.post("/api/v1/network-probe-agent/tasks/claim", headers=headers).json()
    assert second["id"] == first["id"] and second["lease_token"] != first["lease_token"]
    failed = fail_task(second)
    assert failed.status_code == 200 and failed.json()["status"] == "failed"
    with store.engine.connect() as conn:
        task = conn.execute(sa.select(store.network_probe_tasks).where(
            store.network_probe_tasks.c.id == first["id"])).mappings().one()
        runs = conn.execute(sa.select(store.network_probe_runs).where(
            store.network_probe_runs.c.task_id == first["id"])).mappings().all()
    assert task["status"] == "failed" and task["attempt"] == 2
    assert len(runs) == 2 and all(run["status"] == "failed" for run in runs)


def test_revoking_agent_cancels_an_active_lease(system):
    client, store, _, token, agent_id, scope = setup_probe(system)
    assert client.post(f"/api/v1/network-probes/scopes/{scope['id']}/runs").status_code == 202
    task = client.post("/api/v1/network-probe-agent/tasks/claim",
        headers={"authorization": f"Bearer {token}"}).json()
    assert client.delete(f"/api/v1/network-probes/agents/{agent_id}").status_code == 200
    with store.engine.connect() as conn:
        persisted = conn.execute(sa.select(store.network_probe_tasks).where(
            store.network_probe_tasks.c.id == task["id"])).mappings().one()
        disabled = conn.execute(sa.select(store.network_probe_scopes).where(
            store.network_probe_scopes.c.id == scope["id"])).mappings().one()
    assert persisted["status"] == "cancelled" and persisted["lease_token_hash"] is None
    assert disabled["enabled"] is False and disabled["status"] == "disabled"
    assert client.post("/api/v1/network-probe-agent/tasks/claim",
        headers={"authorization": f"Bearer {token}"}).status_code == 401


def test_probe_management_is_superadmin_only_and_ranges_are_bounded(system):
    client, _, _, _ = system
    login(client, "viewer")
    assert client.get("/api/v1/network-probes").status_code == 403
    login(client)
    assert "network_probe.manage" in client.get("/api/v1/session/me").json()["permissions"]
