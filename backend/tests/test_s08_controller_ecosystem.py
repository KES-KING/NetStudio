"""S08 controller/cloud API and standalone EdgeSwitch acceptance contracts."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from ipaddress import ip_address
import json
from pathlib import Path
import ssl

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.controller_transport import (
    ControllerHTTPClient, MAX_RESPONSE_BYTES, parse_controller_record,
)
from app.collection import ReadResult, merge_read_results, metadata
from app.driver_catalog import GROUPS, catalog
from app.driver_profiles import REGISTRY
from app.p2_parsers import parse_p2
from app.ssh import ConnectionPolicyError
from app.transport import TransportContext
from conftest import add_device, login


FIXTURES = Path(__file__).parent / "fixtures" / "s08"
CONTROLLER_PROFILES = {
    "cisco_meraki_ms": "meraki_dashboard",
    "fortinet_fortiswitch_fortilink": "fortinet_fortilink_api",
    "ubiquiti_unifi_switch": "unifi_api",
    "ubiquiti_unifi_no_snmp": "unifi_no_snmp_api",
    "tplink_omada_managed": "tplink_omada_api",
    "tplink_omada_pro": "tplink_omada_pro_api",
}


def load_fixture_manifest():
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    assert manifest["physical_acceptance"] is False
    assert manifest["production_accepted"] is False
    loaded = {}
    for entry in manifest["files"]:
        raw = (FIXTURES / entry["path"]).read_bytes()
        assert sha256(raw).hexdigest() == entry["sha256"]
        fixture = json.loads(raw)
        assert fixture["source_permission"] == "project_generated_test_fixture"
        assert fixture["physical_acceptance"] is False
        assert fixture["production_accepted"] is False
        loaded[entry["path"]] = fixture
    return loaded


def test_controller_profiles_are_api_only_experimental_and_instant_on_stays_blocked():
    for profile_id, runtime in CONTROLLER_PROFILES.items():
        profile = REGISTRY.profile(profile_id)
        assert profile.implementation_status == "implemented"
        assert profile.runtime_driver_id == runtime
        assert profile.adapter == "controller_https"
        assert profile.verification_status == "fixture_verified"
        assert profile.release_status == "experimental"
        assert profile.acceptance.production_accepted is False
        assert next(item for item in profile.transports if item.kind == "api").state == "implemented"
        assert not any(item.kind == "ssh" and item.state == "implemented" for item in profile.transports)

    instant_on = REGISTRY.profile("aruba_instant_on")
    assert instant_on.implementation_status == "blocked"
    api = next(item for item in instant_on.transports if item.kind == "api")
    assert api.state == "unsupported_by_policy"
    assert api.decision_gate == "vendor_public_api_unavailable"
    meraki_fast = next(item for item in REGISTRY.profile("cisco_meraki_ms").capabilities
                       if item.group == "fast")
    assert {"rx_bps", "tx_bps"} <= set(meraki_fast.fields)
    assert "in_octets" not in meraki_fast.fields
    unifi_fast = next(item for item in REGISTRY.profile("ubiquiti_unifi_switch").capabilities
                      if item.group == "fast")
    assert set(unifi_fast.fields) == {"oper_up", "capacity_bps"}


@pytest.mark.parametrize("fixture", load_fixture_manifest()["controller_profiles.json"]["profiles"], ids=lambda item: item["profile_id"])
def test_controller_fixtures_produce_api_provenance_without_physical_claim(system, fixture):
    client, store, *_ = system
    login(client)
    mode = "cloud_managed" if fixture["profile_id"] == "cisco_meraki_ms" else "controller_managed"
    device = store.get_device(add_device(
        client, configured_profile_id=fixture["profile_id"], management_mode=mode,
    )["id"])
    result = parse_controller_record(device, fixture["record"], set(GROUPS))
    assert result.observed_profile_id == fixture["profile_id"]
    assert result.device.model == fixture["record"]["model"]
    assert result.device.inventory_source == "api"
    assert result.metadata["fast"].source == "api"
    assert result.metadata["inventory"].field_sources["model"] == "api"
    sample = result.payloads["fast"]["interfaces"][0]
    assert sample["source"] == "api"
    if fixture["profile_id"] == "cisco_meraki_ms":
        assert sample["rx_bps"] == 1_250_000
        assert sample["tx_bps"] == 750_000
        assert sample["in_octets"] is None
    elif fixture["profile_id"].startswith("ubiquiti_unifi"):
        assert sample["capacity_bps"] == 1_000_000_000
        assert sample["in_octets"] is None
        assert result.payloads["health"]["health"]["cpu_percent"] is not None
    else:
        assert sample["in_octets"] > 2**32


def test_edgeswitch_is_distinct_ssh_snmp_profile_with_its_own_fixture(system):
    fixture = load_fixture_manifest()["ubiquiti_edgeswitch_es48_1_10_4.json"]
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, configured_profile_id="ubiquiti_edgeswitch", management_mode="standalone")["id"])
    result = parse_p2(device, "ubiquiti_edgeswitch", fixture["outputs"], {}, set(GROUPS))
    assert result.observed_profile_id == "ubiquiti_edgeswitch"
    assert result.device.vendor == fixture["expected"]["vendor"]
    assert result.device.model == fixture["expected"]["model"]
    assert result.payloads["network"]["endpoints"]["entries"][0]["addresses"] == ["192.0.2.10"]
    profile = REGISTRY.profile("ubiquiti_edgeswitch")
    assert {item.kind for item in profile.transports if item.state == "implemented"} == {"ssh", "snmp"}


def _controller(client, *, name="UniFi Lab", site="lab", external_site="site-lab"):
    response = client.post("/api/v1/controllers", json={
        "name": name, "vendor": "unifi", "site": site,
        "endpoint_kind": "local", "address": "127.0.0.1", "port": 8443,
        "external_scope_id": "controller-lab", "external_site_id": external_site,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_controller_registration_secret_and_binding_are_site_scoped_and_redacted(system):
    client, store, *_ = system
    login(client)
    controller = _controller(client)
    assert controller["credential_configured"] is False
    assert "ca_pem" not in controller and "token" not in json.dumps(controller)

    invalid = client.post("/api/v1/controllers", json={
        "name": "URL denied", "vendor": "unifi", "site": "lab",
        "endpoint_kind": "local", "address": "https://controller.invalid", "port": 443,
        "external_scope_id": "scope", "external_site_id": "site",
    })
    assert invalid.status_code == 422
    cidr_denied = client.post("/api/v1/controllers", json={
        "name": "Outside operator ceiling", "vendor": "unifi", "site": "lab",
        "endpoint_kind": "local", "address": "192.0.2.10", "port": 443,
        "external_scope_id": "scope", "external_site_id": "site",
    })
    assert cidr_denied.status_code == 422
    wrong_scope = client.put(f"/api/v1/controllers/{controller['id']}/credentials", json={
        "auth_kind": "api_key", "token": "fixture-secret-token-never-returned",
        "scopes": ["device:write"],
    })
    assert wrong_scope.status_code == 422
    assert "fixture-secret-token" not in wrong_scope.text
    missing_scope = client.put(f"/api/v1/controllers/{controller['id']}/credentials", json={
        "auth_kind": "api_key", "token": "fixture-secret-token-never-returned",
        "scopes": ["device:read"],
    })
    assert missing_scope.status_code == 422
    assert missing_scope.json()["detail"]["code"] == "controller_scope_insufficient"

    saved = client.put(f"/api/v1/controllers/{controller['id']}/credentials", json={
        "auth_kind": "api_key", "token": "fixture-secret-token-never-returned",
        "scopes": ["site:read", "device:read"],
    })
    assert saved.status_code == 200
    device = add_device(client, configured_profile_id="ubiquiti_unifi_switch", management_mode="controller_managed")
    bound = client.put(f"/api/v1/devices/{device['id']}/controller-binding", json={
        "controller_id": controller["id"], "external_device_id": "unifi-switch-1",
    })
    assert bound.status_code == 200, bound.text
    assert bound.json()["external_site_id"] == "site-lab"
    assert client.get(f"/api/v1/devices/{device['id']}").json()["api_configured"] is True

    second = add_device(client, configured_profile_id="ubiquiti_unifi_switch", management_mode="controller_managed")
    duplicate = client.put(f"/api/v1/devices/{second['id']}/controller-binding", json={
        "controller_id": controller["id"], "external_device_id": "unifi-switch-1",
    })
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "controller_external_device_already_bound"
    audits = json.dumps(store.engine.connect().execute(store.audit.select()).mappings().all(), default=str)
    assert "fixture-secret-token-never-returned" not in audits

    expired = client.put(f"/api/v1/controllers/{controller['id']}/credentials", json={
        "auth_kind": "api_key", "token": "expired-secret-never-returned",
        "scopes": ["site:read", "device:read"],
        "expires_at": "2020-01-01T00:00:00Z",
    })
    assert expired.status_code == 422
    assert "expired-secret-never-returned" not in expired.text
    revoked = client.delete(f"/api/v1/controllers/{controller['id']}/credentials")
    assert revoked.status_code == 200
    assert client.get(f"/api/v1/devices/{device['id']}").json()["api_configured"] is False


def test_controller_binding_rejects_cross_site_and_wrong_vendor(system):
    client, *_ = system
    login(client)
    other = _controller(client, name="Other", site="other", external_site="site-other")
    device = add_device(client, configured_profile_id="ubiquiti_unifi_switch", management_mode="controller_managed")
    mismatch = client.put(f"/api/v1/devices/{device['id']}/controller-binding", json={
        "controller_id": other["id"], "external_device_id": "unifi-switch-1",
    })
    assert mismatch.status_code == 409
    meraki = client.post("/api/v1/controllers", json={
        "name": "Meraki", "vendor": "meraki", "site": "lab",
        "endpoint_kind": "cloud", "cloud_region": "global",
        "external_scope_id": "org-lab", "external_site_id": "N_lab",
    }).json()
    wrong_vendor = client.put(f"/api/v1/devices/{device['id']}/controller-binding", json={
        "controller_id": meraki["id"], "external_device_id": "Q2XX-TEST-0001",
    })
    assert wrong_vendor.status_code == 409


def test_omada_requires_oauth_access_token_contract(system):
    client, *_ = system
    login(client)
    response = client.post("/api/v1/controllers", json={
        "name": "Omada Lab", "vendor": "omada", "site": "lab",
        "endpoint_kind": "local", "address": "127.0.0.1", "port": 8043,
        "external_scope_id": "controller-test", "external_site_id": "site-test",
    })
    assert response.status_code == 201
    controller_id = response.json()["id"]
    bearer = client.put(f"/api/v1/controllers/{controller_id}/credentials", json={
        "auth_kind": "bearer", "token": "test-only-omada-access-token",
        "scopes": ["site:read", "device:read"],
    })
    assert bearer.status_code == 422
    saved = client.put(f"/api/v1/controllers/{controller_id}/credentials", json={
        "auth_kind": "access_token", "token": "test-only-omada-access-token",
        "scopes": ["site:read", "device:read"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
    })
    assert saved.status_code == 200


def test_external_device_identity_cannot_duplicate_across_controller_replacement(system):
    client, *_ = system
    login(client)
    first_controller = _controller(client, name="UniFi Before", external_site="site-before")
    second_controller = _controller(client, name="UniFi After", external_site="site-after")
    first_device = add_device(
        client, configured_profile_id="ubiquiti_unifi_switch",
        management_mode="controller_managed",
    )
    second_device = add_device(
        client, configured_profile_id="ubiquiti_unifi_switch",
        management_mode="controller_managed",
    )
    first = client.put(f"/api/v1/devices/{first_device['id']}/controller-binding", json={
        "controller_id": first_controller["id"], "external_device_id": "stable-device-id",
    })
    assert first.status_code == 200
    duplicate = client.put(f"/api/v1/devices/{second_device['id']}/controller-binding", json={
        "controller_id": second_controller["id"], "external_device_id": "stable-device-id",
    })
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "controller_external_device_already_bound"


def test_http_client_denies_redirect_loop_oversize_and_bounds_retry(system):
    _, store, _, key_file = system
    device = store.list_devices()[0] if store.list_devices() else None
    if device is None:
        # A minimal device is only needed for the transport deadline/fence.
        client_fixture = system[0]
        login(client_fixture)
        device = store.get_device(add_device(client_fixture)["id"])
    context = TransportContext.create(store, object(), device, timeout_seconds=10)

    async def no_sleep(_):
        return None

    def run(handler, path="/api/v1/items"):
        transport = httpx.MockTransport(handler)
        reader = ControllerHTTPClient(transport=transport, sleeper=no_sleep)
        async def execute():
            async with httpx.AsyncClient(transport=transport, follow_redirects=False) as http:
                return await reader.pages(context, http, "https://api.meraki.com", path, {})
        return asyncio.run(execute())

    with pytest.raises(ConnectionPolicyError, match="controller_redirect_denied"):
        run(lambda request: httpx.Response(302, headers={"location": "https://evil.invalid"}))
    with pytest.raises(ConnectionPolicyError, match="controller_pagination_loop"):
        run(lambda request: httpx.Response(200, json={"data": [], "next": str(request.url)}))
    with pytest.raises(ConnectionPolicyError, match="controller_response_limit"):
        run(lambda request: httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1)))
    def timeout(request):
        raise httpx.ReadTimeout("fixture token must never appear", request=request)
    with pytest.raises(ConnectionPolicyError, match="controller_timeout") as timeout_error:
        run(timeout)
    assert "fixture token" not in str(timeout_error.value)
    calls = 0
    def limited(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"retry-after": "0"})
    with pytest.raises(ConnectionPolicyError, match="controller_rate_limited"):
        run(limited)
    assert calls == 2


def _certificate(common_name: str):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    certificate = (
        x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return (
        certificate.public_bytes(serialization.Encoding.PEM).decode(),
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                          serialization.NoEncryption()).decode(),
    )


def test_isolated_https_controller_accepts_right_ca_and_rejects_wrong_ca(system, tmp_path):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(
        client, configured_profile_id="ubiquiti_unifi_switch", management_mode="controller_managed",
    )["id"])
    good_cert, good_key = _certificate("controller-fixture")
    wrong_cert, _ = _certificate("wrong-ca")
    cert_path, key_path = tmp_path / "controller.crt", tmp_path / "controller.key"
    cert_path.write_text(good_cert); key_path.write_text(good_key)
    payload = json.dumps({"data": [{
        "id": "unifi-switch-1", "siteId": "site-lab", "model": "USW-Pro-24-PoE",
        "firmwareVersion": "7.1.26", "ports": [{"name": "Port 1", "enabled": True,
        "status": "up", "speedMbps": 1000}],
    }]}).encode()

    async def exercise(ca_pem):
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(cert_path, key_path)
        async def handler(reader, writer):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                         + str(len(payload)).encode() + b"\r\nConnection: close\r\n\r\n" + payload)
            await writer.drain(); writer.close(); await writer.wait_closed()
        server = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=server_context)
        port = server.sockets[0].getsockname()[1]
        controller = {"vendor": "unifi", "address": "127.0.0.1", "port": port,
            "cloud_region": None, "ca_pem": ca_pem, "external_scope_id": "controller-lab",
            "external_site_id": "site-lab"}
        binding = {"external_device_id": "unifi-switch-1", "external_site_id": "site-lab"}
        context = TransportContext.create(store, object(), device, timeout_seconds=10)
        try:
            return await ControllerHTTPClient().collect(context, controller, binding,
                {"token": "fixture-secret-never-logged"},
                {"auth_kind": "api_key", "scopes": ["site:read", "device:read"], "expires_at": None})
        finally:
            server.close(); await server.wait_closed()

    record = asyncio.run(exercise(good_cert))
    assert record["id"] == "unifi-switch-1"
    with pytest.raises(ConnectionPolicyError, match="controller_tls_or_connection_failed"):
        asyncio.run(exercise(wrong_cert))


def test_unifi_transport_fetches_documented_details_and_statistics(system):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(
        client, configured_profile_id="ubiquiti_unifi_switch",
        management_mode="controller_managed",
    )["id"])
    requested = []

    def handler(request):
        requested.append(request.url.path)
        assert request.headers["x-api-key"] == "test-only-unifi-api-key"
        if request.url.path.endswith("/statistics/latest"):
            return httpx.Response(200, json={
                "cpuUtilizationPct": 17.5, "memoryUtilizationPct": 42.0,
                "uptimeSec": 7200, "interfaces": {"radios": []},
            })
        if request.url.path.endswith("/devices/unifi-switch-1"):
            return httpx.Response(200, json={
                "id": "unifi-switch-1", "model": "USW-Pro-24-PoE",
                "firmwareVersion": "7.1.26",
                "interfaces": {"ports": [{"idx": 1, "state": "UP",
                    "connector": "RJ45", "maxSpeedMbps": 1000,
                    "speedMbps": 1000}], "radios": []},
            })
        return httpx.Response(200, json={"data": [{
            "id": "unifi-switch-1", "siteId": "site-lab",
            "model": "USW-Pro-24-PoE", "firmwareVersion": "7.1.26",
        }]})

    context = TransportContext.create(store, object(), device, timeout_seconds=10)
    record = asyncio.run(ControllerHTTPClient(transport=httpx.MockTransport(handler)).collect(
        context,
        {"vendor": "unifi", "address": "127.0.0.1", "port": 8443,
         "cloud_region": None, "ca_pem": None, "external_scope_id": "controller-lab",
         "external_site_id": "site-lab"},
        {"external_device_id": "unifi-switch-1", "external_site_id": "site-lab"},
        {"token": "test-only-unifi-api-key"},
        {"auth_kind": "api_key", "scopes": ["site:read", "device:read"],
         "expires_at": None},
    ))
    assert requested == [
        "/proxy/network/integration/v1/sites/site-lab/devices",
        "/proxy/network/integration/v1/sites/site-lab/devices/unifi-switch-1",
        "/proxy/network/integration/v1/sites/site-lab/devices/unifi-switch-1/statistics/latest",
    ]
    parsed = parse_controller_record(device, record, {"fast", "health", "inventory"})
    assert parsed.device.physical_ports[0].connector == "rj45"
    assert parsed.payloads["fast"]["interfaces"][0]["capacity_bps"] == 1_000_000_000
    assert parsed.payloads["health"]["health"]["cpu_percent"] == 17.5


def test_meraki_transport_accepts_registered_read_scopes_and_rate_semantics(system):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(
        client, configured_profile_id="cisco_meraki_ms",
        management_mode="cloud_managed",
    )["id"])
    requested = []

    def handler(request):
        requested.append((request.url.path, str(request.url.query)))
        assert request.headers["authorization"] == "Bearer test-only-meraki-token"
        if request.url.path.endswith("/switch/ports/statuses"):
            assert request.url.params["timespan"] == "300"
            return httpx.Response(200, json=[{
                "portId": "1", "status": "Connected", "speed": "1 Gbps",
                "trafficInKbps": {"recv": 1250, "sent": 750},
            }])
        if request.url.path.endswith("/switch/ports"):
            return httpx.Response(200, json=[{
                "portId": "1", "enabled": True, "vlan": 10, "type": "access",
            }])
        assert request.url.params.get_list("networkIds[]") == ["N_lab"]
        return httpx.Response(200, json=[{
            "serial": "Q2XX-TEST-0001", "networkId": "N_lab",
            "model": "MS225-24P", "firmware": "MS 18.211.2",
        }])

    context = TransportContext.create(store, object(), device, timeout_seconds=10)
    record = asyncio.run(ControllerHTTPClient(transport=httpx.MockTransport(handler)).collect(
        context,
        {"vendor": "meraki", "address": None, "port": None,
         "cloud_region": "global", "ca_pem": None, "external_scope_id": "org-lab",
         "external_site_id": "N_lab"},
        {"external_device_id": "Q2XX-TEST-0001", "external_site_id": "N_lab"},
        {"token": "test-only-meraki-token"},
        {"auth_kind": "bearer", "scopes": [
            "dashboard:general:config:read", "switch:config:read",
            "switch:telemetry:read",
        ], "expires_at": None},
    ))
    assert [path for path, _ in requested] == [
        "/api/v1/organizations/org-lab/devices",
        "/api/v1/devices/Q2XX-TEST-0001/switch/ports",
        "/api/v1/devices/Q2XX-TEST-0001/switch/ports/statuses",
    ]
    parsed = parse_controller_record(device, record, {"fast", "network", "inventory"})
    sample = parsed.payloads["fast"]["interfaces"][0]
    assert sample["rx_bps"] == 1_250_000
    assert sample["tx_bps"] == 750_000
    assert sample["in_octets"] is None


def test_omada_transport_uses_access_token_header(system):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(
        client, configured_profile_id="tplink_omada_managed",
        management_mode="controller_managed",
    )["id"])

    def handler(request):
        assert request.headers["authorization"] == "AccessToken=test-only-omada-token"
        return httpx.Response(200, json={"result": [{
            "deviceId": "omada-switch-1", "siteId": "site-lab",
            "model": "SG3428XMP", "softwareVersion": "1.0.1",
            "port_table": [{"port": "1/0/1", "adminStatus": "enabled",
                "linkStatus": "up", "speed": 1000}],
        }]})

    context = TransportContext.create(store, object(), device, timeout_seconds=10)
    record = asyncio.run(ControllerHTTPClient(transport=httpx.MockTransport(handler)).collect(
        context,
        {"vendor": "omada", "address": "127.0.0.1", "port": 8043,
         "cloud_region": None, "ca_pem": None, "external_scope_id": "controller-lab",
         "external_site_id": "site-lab"},
        {"external_device_id": "omada-switch-1", "external_site_id": "site-lab"},
        {"token": "test-only-omada-token"},
        {"auth_kind": "access_token", "scopes": ["site:read", "device:read"],
         "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)},
    ))
    assert record["deviceId"] == "omada-switch-1"


def test_catalog_exposes_s08_without_claiming_physical_acceptance():
    entries = {item["id"]: item for item in catalog(include_v2=True)["profiles"]}
    for profile_id in CONTROLLER_PROFILES:
        assert entries[profile_id]["selectable"] is True
        assert entries[profile_id]["transports"]["api"]["state"] == "implemented"
        assert entries[profile_id]["acceptance"]["production_accepted"] is False


def test_api_and_snmp_conflict_keeps_winning_source_and_redacted_provenance(system):
    fixtures = json.loads((FIXTURES / "controller_profiles.json").read_text())["profiles"]
    fixture = next(item for item in fixtures if item["profile_id"] == "cisco_meraki_ms")
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(
        client, configured_profile_id="cisco_meraki_ms", management_mode="cloud_managed",
    )["id"])
    api_read = parse_controller_record(device, fixture["record"], {"fast"})
    interface_id = api_read.payloads["fast"]["interfaces"][0]["interface_id"]
    snmp_read = ReadResult(device, payloads={"fast": {"interfaces": [{
        "interface_id": interface_id, "oper_up": False,
    }]}}, metadata={"fast": metadata(
        "fast", "snmp_v3", source="snmp", fields={"oper_up": "ok"},
    )})
    merged = merge_read_results(api_read, snmp_read)
    assert merged.metadata["fast"].quality == "partial"
    assert merged.metadata["fast"].field_sources["oper_up"] == "snmp"
    assert merged.metadata["fast"].diagnostics["conflict:oper_up"] == "api,snmp"
    assert next(row for row in merged.payloads["fast"]["interfaces"] if row["interface_id"] == interface_id)["oper_up"] is False
