from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.database import now
from app.endpoint_resolution import resolve_endpoints
from conftest import login, observation, prepare
from test_topology import endpoint, send


def fixture():
    at = now()
    devices = {key: SimpleNamespace(id=key, name=key, site="lab",
               interfaces=[SimpleNamespace(id="if1"), SimpleNamespace(id="if5")]) for key in ("switch", "gateway")}
    fdb = endpoint(addresses=[], mac="02:aa:00:00:00:01")
    arp = endpoint(id="arp", interface_id="if5", mac=fdb["mac"], discovery="arp", vrf_known=True)
    data = {key: observation(at=at, endpoints={"status": "ok", "entries": [value]}) for key, value in (("switch", fdb), ("gateway", arp))}
    data["switch"]["neighbors"] = [{"id": "lldp", "interface_id": "if1", "remote_device_id": "gateway", "relation": "l2", "evidence": "fixture LLDP"}]
    return at, devices, data


def test_adjacent_gateway_resolves_ip_preserving_identity_and_raw_payload():
    at, devices, data = fixture()
    original = deepcopy(data)
    value = resolve_endpoints(devices, data, at)["switch"]["entries"][0]
    assert value["addresses"] == ["192.0.2.101"]
    assert value["id"] == "learned-1" and value["interface_id"] == "if1"
    assert value["resolution"]["status"] == "resolved"
    assert value["resolution"]["sources"][0]["device_id"] == "gateway"
    assert data == original


@pytest.mark.parametrize("failure", ["site", "vlan", "vrf", "unknown_vrf", "stale", "nud_stale", "failed_network",
                                    "missing_adjacency", "removed_interface", "link_local", "no_permission", "future", "naive_time",
                                    "legacy_partial_endpoint", "legacy_partial_lldp"])
def test_no_resolution_without_current_authorized_scope(failure):
    at, devices, data = fixture()
    source = data["gateway"]["endpoints"]["entries"][0]
    if failure == "site":
        devices["gateway"].site = "other"
    elif failure == "vlan":
        source["vlan"] = 20
    elif failure == "vrf":
        data["switch"]["endpoints"]["entries"][0].update(vrf="blue", vrf_known=True)
        source["vrf"] = "red"
    elif failure == "unknown_vrf":
        source["vrf_known"] = False
    elif failure in {"stale", "future"}:
        data["gateway"]["observed_at"] = (at + timedelta(minutes=-5 if failure == "stale" else 5)).isoformat()
    elif failure == "nud_stale":
        source["state"] = "stale"
    elif failure == "failed_network":
        data["gateway"]["groups"] = {"network": {"quality": "parse_error", "observed_at": at.isoformat(), "stale_after_seconds": 900}}
    elif failure == "naive_time":
        data["gateway"]["groups"] = {"network": {"quality": "ok", "observed_at": at.replace(tzinfo=None).isoformat(), "stale_after_seconds": 900}}
    elif failure in {"legacy_partial_endpoint", "legacy_partial_lldp"}:
        key = "endpoints" if failure == "legacy_partial_endpoint" else "show lldp neighbors detail"
        target = "gateway" if failure == "legacy_partial_endpoint" else "switch"
        data[target]["groups"] = {"network": {"quality": "partial", "observed_at": at.isoformat(),
            "stale_after_seconds": 900, "diagnostics": {key: "parse_error"}}}
    elif failure == "missing_adjacency":
        data["switch"]["neighbors"] = []
    elif failure == "removed_interface":
        devices["gateway"].interfaces = []
    elif failure == "link_local":
        source["addresses"] = ["fe80::1"]
    elif failure == "no_permission":
        del devices["gateway"]
    value = resolve_endpoints(devices, data, at)["switch"]["entries"][0]
    assert not value["addresses"]
    assert value["resolution"]["status"] == "unresolved"
    assert not value["resolution"]["sources"]


def test_group_time_not_fresh_fast_poll_controls_resolution():
    at, devices, data = fixture()
    old = (at - timedelta(minutes=30)).isoformat()
    data["gateway"]["groups"] = {"network": {"quality": "ok", "observed_at": old, "stale_after_seconds": 900}}
    result = resolve_endpoints(devices, data, at)
    assert result["switch"]["entries"][0]["addresses"] == []
    assert result["gateway"]["entries"][0]["resolution"]["status"] == "stale"
    assert result["gateway"]["entries"][0]["resolution"]["observed_at"] == old


def test_unique_lldp_management_address_can_identify_gateway_but_labels_cannot():
    at, devices, data = fixture()
    devices["gateway"].management_address = "192.0.2.254"
    peer = data["switch"]["neighbors"][0]
    peer.pop("remote_device_id")
    peer["label"] = "192.0.2.254"
    assert not resolve_endpoints(devices, data, at)["switch"]["entries"][0]["addresses"]
    peer["addresses"] = ["192.0.2.254"]
    assert resolve_endpoints(devices, data, at)["switch"]["entries"][0]["addresses"] == ["192.0.2.101"]


def test_conflicting_vrf_or_sources_are_not_silently_combined():
    at, devices, data = fixture()
    source = data["gateway"]["endpoints"]["entries"][0]
    data["gateway"]["endpoints"]["entries"].append({**source, "id": "other", "vrf": "red"})
    result = resolve_endpoints(devices, data, at)["switch"]["entries"][0]
    assert result["resolution"]["status"] == "ambiguous" and not result["addresses"]
    data["gateway"]["endpoints"]["entries"][1].update(vrf=None, interface_id="if1", addresses=["192.0.2.102"])
    result = resolve_endpoints(devices, data, at)["switch"]["entries"][0]
    assert result["resolution"]["status"] == "ambiguous" and not result["addresses"]


def test_multiple_ipv4_ipv6_addresses_and_same_interface_scope():
    at, devices, data = fixture()
    source = data["gateway"]["endpoints"]["entries"][0]
    data["switch"]["endpoints"]["entries"].extend([
        {**source, "interface_id": "if1", "vlan": None},
        {**source, "id": "ndp", "interface_id": "if1", "vlan": None, "discovery": "ndp", "addresses": ["2001:db8::101"]}])
    del devices["gateway"]
    result = resolve_endpoints(devices, data, at)["switch"]["entries"][0]
    assert result["addresses"] == ["192.0.2.101", "2001:db8::101"]


def test_topology_and_detail_share_automatic_latest_resolution_with_site_guards(system):
    client, store, *_ = system
    login(client)
    switch = prepare(client, name="Switch")
    gateway = prepare(client, name="Gateway", management_address="192.0.2.254")
    hidden = prepare(client, name="Hidden", site="other", management_address="198.51.100.254")
    # Old external snapshot must not hide a newer worker snapshot.
    send(client, switch, at=now() - timedelta(minutes=3), endpoints={"status": "ok", "entries": []})
    at = now()
    data = observation(at=at, endpoints={"status": "ok", "entries": [endpoint(addresses=[])]},
        neighbors=[{"id": "uplink", "interface_id": "if2", "remote_device_id": gateway["id"],
                    "label": "Gateway", "relation": "l2", "evidence": "explicit fixture link"}])
    # Use the real validated contract before inserting a worker-shaped snapshot.
    from app.contracts import Telemetry
    with store.engine.begin() as conn:
        conn.execute(store.latest_telemetry.insert().values(device_id=switch["id"], observed_at=at,
            payload=Telemetry.model_validate(data).model_dump(mode="json")))
    for device, address in ((gateway, "192.0.2.101"), (hidden, "198.51.100.101")):
        assert send(client, device, endpoints={"status": "ok", "entries": [
            endpoint(id="arp", interface_id="if5", addresses=[address], discovery="arp", vrf_known=True)]}).status_code == 201
    login(client, "viewer")
    graph = client.get("/api/v1/topology").json()
    row = next(d for d in graph["devices"] if d["id"] == switch["id"])
    detail = client.get(f"/api/v1/devices/{switch['id']}/overview").json()
    assert row["endpoints"] == detail["endpoints"]
    resolved = detail["endpoints"]["entries"][0]
    assert resolved["addresses"] == ["192.0.2.101"]
    assert resolved["resolution"]["sources"][0]["device_id"] == gateway["id"]
    assert hidden["id"] not in str(detail) and "198.51.100.101" not in str(detail)
    node = next(n for n in detail["topology"]["nodes"] if n["kind"] == "endpoint")
    assert node["name"] == "192.0.2.101" and "02:aa:00:00:00:01" in node["detail"]
    assert next(l for l in detail["topology"]["links"] if l["target"] == node["id"])["relation"] == "endpoint"
