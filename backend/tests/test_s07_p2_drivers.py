"""S07 Dell, Extreme and standalone FortiSwitch acceptance contracts."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.driver_catalog import GROUPS, catalog
from app.driver_profiles import REGISTRY
from app.drivers import identify_platform
from app.p2_parsers import IDENTITY_COMMANDS, INTERFACE_COMMANDS, parse_p2
from app.profile_resolution import record_collected_resolution, resolve_profile
from app.ssh import ConnectionPolicyError
from conftest import add_device, login


FIXTURES = Path(__file__).parent / "fixtures" / "p2"
P2 = {
    "dell_os10": "dell_os10",
    "dell_os9": "dell_force10",
    "dell_os6": "dell_os6",
    "extreme_exos": "extreme_exos",
    "extreme_fabric_engine": "extreme_vsp",
    "extreme_slxos": "extreme_slxos",
    "fortinet_fortiswitchos": "fortinet_fortiswitchos",
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


def test_seven_s07_profiles_are_independent_experimental_runtime_contracts():
    profiles = {profile.id: profile for profile in REGISTRY.profiles if profile.id in P2}
    assert set(profiles) == set(P2)
    assert {profile.runtime_driver_id for profile in profiles.values()} == set(P2.values())
    for profile in profiles.values():
        assert profile.implementation_status == "implemented"
        assert profile.verification_status == "fixture_verified"
        assert profile.release_status == "experimental"
        assert profile.acceptance.production_accepted is False
        assert profile.profile_revision == 2
        assert {transport.kind for transport in profile.transports if transport.state == "implemented"} == {"ssh", "snmp"}
        assert {capability.group for capability in profile.capabilities} >= {"fast", "network", "inventory"}

    fortiswitch_api = next(
        transport for transport in profiles["fortinet_fortiswitchos"].transports
        if transport.kind == "api"
    )
    assert fortiswitch_api.state == "planned"
    assert fortiswitch_api.decision_gate == "vendor_api_adapter_not_implemented"
    fabric_snmp = next(
        transport for transport in profiles["extreme_fabric_engine"].transports
        if transport.kind == "snmp"
    )
    assert fabric_snmp.decision_gate == "fabric_engine_ssh_secure_mode_block_snmp"


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda value: value["profile_id"])
def test_exact_tuple_fixture_covers_identity_interfaces_network_and_inventory(system, fixture):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, collector=fixture["runtime_driver_id"])["id"])
    result = parse_p2(device, fixture["runtime_driver_id"], fixture["outputs"], {}, set(GROUPS))
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
    assert len(result.device.physical_ports) == 1
    assert result.device.physical_ports[0].verified_layout is False
    assert all(value.reason != "collector_parse_failed" for value in result.metadata.values())


def test_dell_command_and_interface_grammars_are_not_interchangeable():
    profiles = [REGISTRY.profile(identifier) for identifier in ("dell_os10", "dell_os9", "dell_os6")]
    assert len({tuple(command.text for command in profile.commands) for profile in profiles}) == 3
    assert {
        next(command.parser for command in profile.commands if command.required and command.group == "fast")
        for profile in profiles
    } == {"dell_os10.interfaces", "dell_os9.interfaces", "dell_os6.interfaces"}


def test_extreme_command_families_and_os_alias_metadata_remain_separate():
    exos = REGISTRY.profile("extreme_exos")
    fabric = REGISTRY.profile("extreme_fabric_engine")
    slx = REGISTRY.profile("extreme_slxos")
    assert exos.identity.os_families == ("ExtremeXOS", "Switch Engine")
    assert fabric.identity.os_families == ("Fabric Engine", "VOSS")
    assert len({tuple(command.text for command in profile.commands) for profile in (exos, fabric, slx)}) == 3
    assert identify_platform({"show version": "ExtremeXOS version 33.3.1.4"}).profile_id == "extreme_exos"
    assert identify_platform({"show sys-info": "Extreme Networks Fabric Engine VOSS"}).profile_id == "extreme_fabric_engine"
    assert identify_platform({"show version": "Extreme SLX-OS Version: 20.6.3b"}).profile_id == "extreme_slxos"


def test_dell_same_model_text_requires_os_banner_and_sonic_never_falls_back():
    model = "System Type : S4048-ON\n"
    assert identify_platform({"show version": "Dell EMC SmartFabric OS10\n" + model}).profile_id == "dell_os10"
    assert identify_platform({"show version": "Dell EMC Networking OS9\n" + model}).profile_id == "dell_os9"
    assert identify_platform({"show version": "Dell EMC Enterprise SONiC\n" + model}).profile_id == "dell_sonic"
    assert identify_platform({"show version": "Dell EMC Enterprise SONiC\n" + model}).runtime_driver_id is None


def test_fortiswitch_standalone_fortilink_and_fortios_are_not_aliases():
    standalone = identify_platform({"get system status": "Version: FortiSwitch-124F v7.6.2\nManagement mode: standalone"})
    assert standalone.profile_id == "fortinet_fortiswitchos"
    assert standalone.runtime_driver_id == "fortinet_fortiswitchos"
    managed = identify_platform({"get system status": "Version: FortiSwitch-124F v7.6.2\nFortiLink mode: managed"})
    assert managed.profile_id == "fortinet_fortiswitch_fortilink"
    assert managed.runtime_driver_id is None
    with pytest.raises(ConnectionPolicyError, match="collector_platform_unsupported"):
        identify_platform({"get system status": "Version: FortiGate-100F v7.6.2\nFortiOS"})
    assert resolve_profile("fortinet").status == "manual_resolution_required"


def test_cross_family_identity_mismatch_fails_closed(system):
    client, store, *_ = system
    login(client)
    fixtures = {value["profile_id"]: value for value in load_fixtures()}
    device = store.get_device(add_device(client, collector="dell_os10")["id"])
    mismatch = parse_p2(device, "dell_os10", fixtures["dell_os9"]["outputs"], {}, {"inventory"})
    assert mismatch.observed_profile_id == "dell_os9"
    assert mismatch.metadata["inventory"].reason == "collector_platform_mismatch"

    standalone = store.get_device(add_device(client, collector="fortinet_fortiswitchos")["id"])
    outputs = dict(fixtures["fortinet_fortiswitchos"]["outputs"])
    outputs["get system status"] += "FortiLink mode: managed\n"
    managed = parse_p2(standalone, "fortinet_fortiswitchos", outputs, {}, {"inventory"})
    assert managed.observed_profile_id == "fortinet_fortiswitch_fortilink"
    assert managed.metadata["inventory"].reason == "collector_platform_mismatch"


@pytest.mark.parametrize("failure", ["collector_permission_denied", "collector_timeout"])
@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda value: value["profile_id"])
def test_required_interface_permission_and_timeout_are_explicit(system, fixture, failure):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, collector=fixture["runtime_driver_id"])["id"])
    command = INTERFACE_COMMANDS[fixture["runtime_driver_id"]]
    identity_command = IDENTITY_COMMANDS[fixture["runtime_driver_id"]]
    result = parse_p2(
        device, fixture["runtime_driver_id"],
        {identity_command: fixture["outputs"][identity_command]},
        {command: failure}, {"fast"},
    )
    assert result.metadata["fast"].reason == "required_command_unavailable"
    assert result.metadata["fast"].diagnostics[command] == (
        "permission_denied" if failure == "collector_permission_denied" else "timeout"
    )


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda value: value["profile_id"])
def test_malformed_required_interface_output_preserves_existing_inventory(system, fixture):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, collector=fixture["runtime_driver_id"])["id"])
    outputs = dict(fixture["outputs"])
    outputs[INTERFACE_COMMANDS[fixture["runtime_driver_id"]]] = "malformed synthetic output"
    result = parse_p2(device, fixture["runtime_driver_id"], outputs, {}, {"fast"})
    assert result.device == device
    assert result.metadata["fast"].quality == "parse_error"
    assert result.metadata["fast"].reason == "collector_parse_failed"


def test_fabric_secure_mode_surfaces_snmp_constraint_without_inventing_health(system):
    client, store, *_ = system
    login(client)
    fixture = next(value for value in load_fixtures() if value["profile_id"] == "extreme_fabric_engine")
    device = store.get_device(add_device(client, collector="extreme_vsp")["id"])
    result = parse_p2(device, "extreme_vsp", fixture["outputs"], {}, set(GROUPS))
    assert result.payloads["inventory"]["transport_constraints"] == {
        "snmp": fixture["expected"]["snmp_constraint"]
    }
    health = result.payloads["health"]["health"]
    assert health["fan"] is None and health["power_supply"] is None
    assert not result.payloads["health"]["interfaces"]


@pytest.mark.parametrize(
    ("collector", "profile_id"),
    [("dell_force10", "dell_os9"), ("extreme_vsp", "extreme_fabric_engine")],
)
def test_conditional_legacy_alias_resolution_preserves_secret_and_host_key(system, collector, profile_id):
    client, store, *_ = system
    login(client)
    fixture = next(value for value in load_fixtures() if value["profile_id"] == profile_id)
    original = store.get_device(add_device(client, collector=collector, name="Alias switch")["id"])
    with store.engine.begin() as conn:
        conn.execute(store.secrets.insert().values(
            device_id=original.id, key_id="test-key", nonce=b"nonce-before",
            ciphertext=b"ciphertext-before",
        ))
        conn.execute(store.host_keys.insert().values(
            device_id=original.id, public_key="ssh-ed25519 test",
            fingerprint="SHA256:test",
        ))
        parsed = parse_p2(original, collector, fixture["outputs"], {}, set(GROUPS))
        record_collected_resolution(
            store, parsed.device, conn, observed_profile_id=parsed.observed_profile_id,
            identity_evidence=parsed.identity_evidence,
        )
    binding = store.get_driver_binding(original.id)
    assert binding["configured_profile_id"] == profile_id
    assert binding["resolved_profile_id"] == profile_id
    assert binding["legacy_collector_id"] == collector
    with store.engine.connect() as conn:
        secret = conn.execute(sa.select(store.secrets).where(store.secrets.c.device_id == original.id)).mappings().one()
        host_key = conn.execute(sa.select(store.host_keys).where(store.host_keys.c.device_id == original.id)).mappings().one()
    assert secret["nonce"] == b"nonce-before" and secret["ciphertext"] == b"ciphertext-before"
    assert host_key["fingerprint"] == "SHA256:test"
    assert store.get_device(original.id).name == "Alias switch"


def test_catalog_and_create_api_expose_s07_profiles_and_s08_owns_fortilink(system):
    client, *_ = system
    login(client)
    value = catalog(include_v2=True)
    entries = {entry["id"]: entry for entry in value["profiles"] if entry["id"] in P2}
    assert set(entries) == set(P2)
    assert all(entry["selectable"] and entry["release_status"] == "experimental" for entry in entries.values())
    fortilink = next(entry for entry in value["profiles"] if entry["id"] == "fortinet_fortiswitch_fortilink")
    assert fortilink["selectable"] is True
    assert fortilink["runtime_selection_id"] == "fortinet_fortilink_api"
    response = client.post("/api/v1/devices", json={
        "name": "OS6 test", "management_address": "127.0.0.1", "site": "lab",
        "configured_profile_id": "dell_os6", "management_mode": "standalone",
    })
    assert response.status_code == 201, response.text
    assert response.json()["collector"] == "dell_os6"
    assert response.json()["configured_profile_id"] == "dell_os6"
