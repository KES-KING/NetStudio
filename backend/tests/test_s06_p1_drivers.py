"""S06 P1 manifests, parser fixtures and fail-closed identity boundaries."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.driver_catalog import GROUPS, catalog
from app.driver_profiles import REGISTRY
from app.drivers import identify_platform
from app.p1_parsers import IDENTITY_COMMANDS, INTERFACE_COMMANDS, parse_p1
from app.profile_resolution import record_collected_resolution
from conftest import add_device, login


FIXTURES = Path(__file__).parent / "fixtures" / "p1"
P1 = {
    "aruba_aoscx": "aruba_aoscx",
    "aruba_aoss": "hp_procurve",
    "arista_eos": "arista_eos",
    "hpe_comware": "hp_comware",
    "h3c_comware7": "h3c_comware7",
    "mikrotik_routeros": "mikrotik_routeros",
}


def load_fixtures():
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    assert manifest["physical_acceptance"] is False
    assert manifest["production_accepted"] is False
    result = []
    for entry in manifest["files"]:
        raw = (FIXTURES / entry["path"]).read_bytes()
        assert sha256(raw).hexdigest() == entry["sha256"]
        value = json.loads(raw)
        assert value["source_permission"] == "project_generated_test_fixture"
        result.append(value)
    return result


def test_six_p1_profiles_are_independent_experimental_runtime_contracts():
    profiles = {profile.id: profile for profile in REGISTRY.profiles if profile.wave == "P1"}
    assert set(profiles) == set(P1)
    assert {profile.runtime_driver_id for profile in profiles.values()} == set(P1.values())
    for profile in profiles.values():
        assert profile.implementation_status == "implemented"
        assert profile.verification_status == "fixture_verified"
        assert profile.release_status == "experimental"
        assert profile.acceptance.production_accepted is False
        assert profile.profile_revision == 2
        assert {transport.kind for transport in profile.transports if transport.state == "implemented"} == {"ssh", "snmp"}
        assert {capability.group for capability in profile.capabilities} >= {"fast", "network", "inventory"}
    for identifier in ("aruba_aoscx", "arista_eos", "mikrotik_routeros"):
        api = next(transport for transport in profiles[identifier].transports if transport.kind == "api")
        assert api.state == "blocked" and api.decision_gate == "ADR-COMPAT-004"


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda value: value["profile_id"])
def test_exact_tuple_fixture_covers_identity_interfaces_64_bit_network_and_inventory(system, fixture):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, collector=fixture["runtime_driver_id"])["id"])
    result = parse_p1(device, fixture["runtime_driver_id"], fixture["outputs"], {}, set(GROUPS))
    expected = fixture["expected"]

    assert result.observed_profile_id == fixture["profile_id"]
    assert result.device.vendor == expected["vendor"]
    assert result.device.model == expected["model"] == fixture["model"]
    assert result.device.os_version == expected["parsed_os_version"] == fixture["os_version"]
    assert result.device.serial == expected["serial"]
    interface = next(value for value in result.device.interfaces if value.name == expected["interface_name"])
    sample = next(value for value in result.payloads["fast"]["interfaces"] if value["interface_id"] == interface.id)
    assert sample["admin_up"] is True and sample["oper_up"] is True
    assert sample["counter_bits"] == 64
    assert sample["in_octets"] > 2**32 and sample["out_octets"] > 2**32

    network = result.payloads["network"]
    endpoint = network["endpoints"]["entries"][0]
    assert endpoint["vlan"] == 10 and endpoint["addresses"] == ["192.0.2.10"]
    assert network["neighbors"][0]["relation"] == "l2"
    assert next(row for row in network["interfaces"] if row["interface_id"] == interface.id)["pvid"] == 10
    assert {"vlan", "fdb", "arp", "lldp"} <= {
        key for key, value in result.metadata["network"].fields.items() if value == "ok"
    }
    assert result.payloads["inventory"]["modules"]
    assert all(value.reason != "collector_parse_failed" for value in result.metadata.values())


def test_aoscx_and_aoss_do_not_share_a_parser_or_command_grammar():
    cx, switch = REGISTRY.profile("aruba_aoscx"), REGISTRY.profile("aruba_aoss")
    assert cx.adapter == "ssh_cli_json" and switch.adapter == "ssh_cli"
    assert any(command.parser.startswith("aoscx.") for command in cx.commands)
    assert any(command.parser.startswith("aoss.") for command in switch.commands)
    assert {command.text for command in cx.commands} != {command.text for command in switch.commands}
    assert all("rest" not in command.parser.lower() for command in cx.commands)


def test_hpe_and_h3c_share_only_comware7_mapping_not_identity_or_acceptance():
    hpe, h3c = REGISTRY.profile("hpe_comware"), REGISTRY.profile("h3c_comware7")
    assert hpe.identity.vendors == ("HPE Aruba Networking",)
    assert h3c.identity.vendors == ("H3C",)
    assert hpe.runtime_driver_id != h3c.runtime_driver_id
    assert hpe.tested_versions != h3c.tested_versions
    assert identify_platform({"display version": "HP Comware Software, Version 7.1.070"}).profile_id == "hpe_comware"
    assert identify_platform({"display version": "H3C Comware Software, Version 5.20"}).profile_id == "h3c_comware5"
    assert identify_platform({"display version": "H3C Comware Software, Version 9.1"}).profile_id == "h3c_comware9"
    assert identify_platform({"display version": "H3C Comware Software, Version 5.20"}).runtime_driver_id is None
    assert identify_platform({"display version": "H3C Comware Software, Version 9.1"}).runtime_driver_id is None


def test_comware_v5_v9_and_cross_brand_identity_fail_closed(system):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, collector="h3c_comware7")["id"])
    fixture = next(value for value in load_fixtures() if value["profile_id"] == "h3c_comware7")
    for version, observed in (("5.20", "h3c_comware5"), ("9.1", "h3c_comware9")):
        outputs = dict(fixture["outputs"])
        outputs["display version"] = f"H3C Comware Software, Version {version}\nDevice model : S5560X-30C-EI\n"
        result = parse_p1(device, "h3c_comware7", outputs, {}, {"inventory"})
        assert result.observed_profile_id == observed
        assert result.metadata["inventory"].reason == "collector_platform_mismatch"
    hpe_device = store.get_device(add_device(client, collector="hp_comware")["id"])
    mismatch = parse_p1(hpe_device, "hp_comware", fixture["outputs"], {}, {"inventory"})
    assert mismatch.observed_profile_id == "h3c_comware7"
    assert mismatch.metadata["inventory"].reason == "collector_platform_mismatch"


@pytest.mark.parametrize("failure", ["collector_permission_denied", "collector_timeout"])
@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda value: value["profile_id"])
def test_required_p1_interface_permission_and_timeout_are_explicit(system, fixture, failure):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, collector=fixture["runtime_driver_id"])["id"])
    command = INTERFACE_COMMANDS[fixture["runtime_driver_id"]]
    result = parse_p1(device, fixture["runtime_driver_id"], {
        IDENTITY_COMMANDS[fixture["runtime_driver_id"]]: fixture["outputs"][IDENTITY_COMMANDS[fixture["runtime_driver_id"]]],
    }, {command: failure}, {"fast"})
    assert result.metadata["fast"].reason == "required_command_unavailable"
    assert result.metadata["fast"].diagnostics[command] == (
        "permission_denied" if failure == "collector_permission_denied" else "timeout"
    )


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda value: value["profile_id"])
def test_malformed_required_interface_output_does_not_replace_inventory(system, fixture):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, collector=fixture["runtime_driver_id"])["id"])
    outputs = dict(fixture["outputs"])
    outputs[INTERFACE_COMMANDS[fixture["runtime_driver_id"]]] = "malformed synthetic output"
    result = parse_p1(device, fixture["runtime_driver_id"], outputs, {}, {"fast"})
    assert result.device == device
    assert result.metadata["fast"].quality == "parse_error"
    assert result.metadata["fast"].reason == "collector_parse_failed"


def test_routeros_parser_never_calls_cisco_text_parser(system, monkeypatch):
    client, store, *_ = system
    login(client)
    fixture = next(value for value in load_fixtures() if value["profile_id"] == "mikrotik_routeros")
    device = store.get_device(add_device(client, collector="mikrotik_routeros")["id"])
    monkeypatch.setattr("app.cisco.parse_interfaces", lambda _: pytest.fail("Cisco parser must not be called"))
    result = parse_p1(device, "mikrotik_routeros", fixture["outputs"], {}, set(GROUPS))
    assert result.observed_profile_id == "mikrotik_routeros"
    assert all(command.text.startswith("/") for command in REGISTRY.profile("mikrotik_routeros").commands)


def test_hp_procurve_alias_resolution_preserves_device_secret_and_host_key(system):
    client, store, *_ = system
    login(client)
    fixture = next(value for value in load_fixtures() if value["profile_id"] == "aruba_aoss")
    created = add_device(client, collector="hp_procurve", name="Alias switch")
    original = store.get_device(created["id"])
    with store.engine.begin() as conn:
        conn.execute(store.secrets.insert().values(
            device_id=original.id, key_id="test-key", nonce=b"nonce-before", ciphertext=b"ciphertext-before",
        ))
        conn.execute(store.host_keys.insert().values(
            device_id=original.id, public_key="ssh-ed25519 test", fingerprint="SHA256:test",
        ))
        parsed = parse_p1(original, "hp_procurve", fixture["outputs"], {}, set(GROUPS))
        record_collected_resolution(store, parsed.device, conn,
            observed_profile_id=parsed.observed_profile_id, identity_evidence=parsed.identity_evidence)
    binding = store.get_driver_binding(original.id)
    assert binding["configured_profile_id"] == "aruba_aoss"
    assert binding["resolved_profile_id"] == "aruba_aoss"
    assert binding["legacy_collector_id"] == "hp_procurve"
    with store.engine.connect() as conn:
        secret = conn.execute(sa.select(store.secrets).where(store.secrets.c.device_id == original.id)).mappings().one()
        host_key = conn.execute(sa.select(store.host_keys).where(store.host_keys.c.device_id == original.id)).mappings().one()
    assert secret["nonce"] == b"nonce-before" and secret["ciphertext"] == b"ciphertext-before"
    assert host_key["fingerprint"] == "SHA256:test"
    assert store.get_device(original.id).name == "Alias switch"


def test_catalog_and_create_api_expose_all_six_p1_profiles_independently(system):
    client, *_ = system
    login(client)
    value = catalog(include_v2=True)
    entries = {entry["id"]: entry for entry in value["profiles"] if entry["wave"] == "P1"}
    assert set(entries) == set(P1)
    assert all(entry["selectable"] and entry["release_status"] == "experimental" for entry in entries.values())
    response = client.post("/api/v1/devices", json={
        "name": "H3C test", "management_address": "127.0.0.1", "site": "lab",
        "configured_profile_id": "h3c_comware7", "management_mode": "standalone",
    })
    assert response.status_code == 201, response.text
    assert response.json()["collector"] == "h3c_comware7"
    assert response.json()["configured_profile_id"] == "h3c_comware7"
