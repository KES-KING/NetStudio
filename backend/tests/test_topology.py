from datetime import timedelta
import json

import pytest
import sqlalchemy as sa

from app.collector import linux_endpoints
from app.database import now
from conftest import inventory, login, observation, prepare


def endpoint(**changes):
    return {"id": "learned-1", "interface_id": "if1", "mac": "02:AA:00:00:00:01", "addresses": ["192.0.2.101"],
        "vlan": 10, "discovery": "fdb", "state": "unknown", "evidence": "Test collector: FDB + same VLAN ARP correlation", **changes}


def send(client, device, **changes):
    return client.post(f"/api/v1/devices/{device['id']}/observations", json=observation(**changes))


def layout(device, **changes):
    return {"version": 0, "zones": [{"id": "zone-1", "name": "Merkez", "x": 20, "y": 20, "width": 620, "height": 540}],
        "placements": [{"device_id": device["id"], "zone_id": "zone-1", "x": 320, "y": 270}], "links": [], **changes}


def test_endpoint_contract_and_graph_preserve_evidence_without_physical_inference(system):
    client, store, *_ = system
    login(client)
    device = prepare(client)
    assert send(client, device, endpoints={"status": "ok", "entries": [endpoint()]}).status_code == 201
    graph = client.get("/api/v1/topology").json()
    assert graph["links"] == []  # No physical cable or device link from a learned MAC/IP.
    row = graph["devices"][0]
    assert row["endpoints"]["entries"][0]["mac"] == "02:aa:00:00:00:01"
    assert row["interfaces"][0]["port_ids"] == ["p1"]
    assert row["endpoints"]["entries"][0]["state"] == "unknown"
    assert "credential" not in json.dumps(row)
    for change in ({"mac": "ff:ff:ff:ff:ff:ff"}, {"addresses": ["not-ip"]}, {"vlan": 4095}, {"interface_id": "missing"}):
        assert send(client, device, endpoints={"status": "ok", "entries": [endpoint(**change)]}).status_code == 422
    assert send(client, device, endpoints={"status": "unsupported", "entries": [endpoint()]}).status_code == 422
    assert send(client, device, endpoints={"status": "ok", "entries": [endpoint(), endpoint()]}).status_code == 422


def test_graph_filters_sites_and_does_not_match_by_label_or_ip(system):
    client, _, *_ = system
    login(client)
    local = prepare(client, name="Local")
    peer = prepare(client, name="Peer", management_address="192.0.2.10")
    other = prepare(client, site="other", name="Restricted", management_address="192.0.2.11")
    assert send(client, local, neighbors=[
        {"id": "allowed", "interface_id": "if1", "label": "Peer", "relation": "l2", "evidence": "LLDP test", "remote_device_id": peer["id"], "remote_interface_id": "if2"},
        {"id": "forbidden", "interface_id": "if2", "label": "Restricted", "relation": "physical", "evidence": "Test cable", "remote_device_id": other["id"]},
        {"id": "unresolved", "interface_id": "if3", "label": "Peer", "relation": "l2", "evidence": "Label only, not an inventory identity"},
    ]).status_code == 201
    login(client, "viewer")
    graph = client.get("/api/v1/topology").json()
    assert len(graph["devices"]) == 2
    assert len(graph["links"]) == 1 and graph["links"][0]["target_device_id"] == peer["id"]
    assert "Restricted" not in json.dumps(graph) and other["id"] not in json.dumps(graph)
    assert next(d for d in graph["devices"] if d["id"] == local["id"])["neighbors"][0]["id"] == "unresolved"


def test_graph_distinguishes_absent_unsupported_empty_and_stale_endpoint_data(system):
    client, *_ = system
    login(client)
    device = prepare(client)
    assert client.get("/api/v1/topology").json()["devices"][0]["endpoints"]["status"] == "unknown"
    assert send(client, device, at=now() - timedelta(minutes=10), endpoints={"status": "ok", "entries": [endpoint(state="stale")]}).status_code == 201
    row = client.get("/api/v1/topology").json()["devices"][0]
    assert row["data_state"] == "stale" and row["endpoints"]["entries"][0]["state"] == "stale"
    assert send(client, device, endpoints={"status": "unsupported"}).status_code == 201
    assert client.get("/api/v1/topology").json()["devices"][0]["endpoints"]["status"] == "unsupported"


def test_personal_layout_roundtrip_csrf_conflict_and_audit(system):
    client, store, *_ = system
    login(client)
    device = prepare(client)
    body = layout(device)
    denied = client.put("/api/v1/topology/board", json=body, headers={"x-csrf-token": "wrong"})
    assert denied.status_code == 403
    saved = client.put("/api/v1/topology/board", json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1
    assert client.get("/api/v1/topology/board").json()["zones"][0]["name"] == "Merkez"
    assert client.put("/api/v1/topology/board", json=body).status_code == 409
    body["version"] = 1
    body["zones"][0]["name"] = "Updated"
    assert client.put("/api/v1/topology/board", json=body).json()["version"] == 2
    with store.engine.connect() as conn:
        records = conn.execute(sa.select(store.audit).where(store.audit.c.event == "topology.saved")).mappings().all()
        assert len(records) == 2 and records[-1]["details"]["input"]["zones"][0]["name"] == "Updated"
    login(client, "viewer")
    assert client.get("/api/v1/topology/board").json()["version"] == 0
    assert client.put("/api/v1/topology/board", json=layout(device)).status_code == 200  # Personal annotation, no device management privilege.
    login(client)
    assert client.get("/api/v1/topology/board").json()["version"] == 2


def test_board_validation_and_pruning_revoked_references(system):
    client, store, *_ = system
    login(client)
    first = prepare(client)
    second = prepare(client, site="other", management_address="192.0.2.5")
    link = {"id": "link-1", "source_device_id": first["id"], "source_port_id": "p1", "target_device_id": second["id"], "target_port_id": "p2"}
    body = layout(first, links=[link])
    assert client.put("/api/v1/topology/board", json={**body, "links": [link, {**link, "id": "link-2"}]}).status_code == 422
    assert client.put("/api/v1/topology/board", json={**body, "links": [{**link, "target_port_id": "missing"}]}).status_code == 422
    assert client.put("/api/v1/topology/board", json={**body, "owner_id": "viewer"}).status_code == 422
    assert client.put("/api/v1/topology/board", json=body).status_code == 200
    with store.engine.begin() as conn:
        conn.execute(store.users.update().where(store.users.c.id == "admin").values(sites=["lab"]))
    limited = client.get("/api/v1/topology/board").json()
    assert limited["links"] == [] and limited["omitted_references"] == 1
    assert second["id"] not in json.dumps(limited)
    body["version"] = 1
    assert client.put("/api/v1/topology/board", json=body).status_code == 422
    assert client.get("/api/v1/topology/board").json()["version"] == 1


def test_linux_neighbors_are_not_assigned_to_unknown_physical_ports(system):
    client, store, *_ = system
    login(client)
    device = prepare(client)
    interfaces = store.get_device(device["id"]).interfaces
    rows = [{"dst": "192.0.2.101", "dev": "eth1", "lladdr": "02:00:00:00:00:01", "state": ["REACHABLE"]},
        {"dst": "2001:db8::1", "dev": "Vlan10", "lladdr": "02:00:00:00:00:02", "state": ["STALE"]},
        {"dst": "192.0.2.200", "dev": "eth1", "state": ["FAILED"]},
        {"dst": "192.0.2.201", "dev": "eth1", "lladdr": "01:00:00:00:00:00", "state": ["PERMANENT"]}]
    result = linux_endpoints(interfaces, json.dumps(rows))
    assert result.status == "partial" and len(result.entries) == 2
    assert result.entries[0].discovery == "arp" and result.entries[0].state == "reachable"
    assert result.entries[1].discovery == "ndp" and result.entries[1].interface_id == "if5" and result.entries[1].state == "stale"
    assert linux_endpoints(interfaces, "[]").status == "ok"
    assert linux_endpoints(interfaces, "garbage").status == "error"
    assert linux_endpoints(interfaces, None).status == "error"


def test_removed_interfaces_do_not_keep_current_topology_references(system):
    client, *_ = system
    login(client)
    device = prepare(client)
    assert send(client, device, endpoints={"status": "ok", "entries": [endpoint()]}).status_code == 201
    value = inventory(now())
    value["interfaces"] = [i for i in value["interfaces"] if i["id"] != "if1"]
    value["bindings"] = [b for b in value["bindings"] if b["interface_id"] != "if1"]
    assert client.put(f"/api/v1/devices/{device['id']}/inventory", json=value).status_code == 200
    row = client.get("/api/v1/topology").json()["devices"][0]
    assert row["endpoints"] == {"status": "partial", "entries": []}


@pytest.mark.parametrize("path", ["/api/v1/topology", "/api/v1/topology/board"])
def test_topology_requires_live_session(system, path):
    client, *_ = system
    assert client.get(path).status_code == 401
    login(client)
    assert client.get(path).status_code == 200
    client.post("/api/v1/session/logout")
    assert client.get(path).status_code == 401
