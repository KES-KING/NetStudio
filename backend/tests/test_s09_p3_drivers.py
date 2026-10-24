"""S09 advanced, legacy and Linux-NOS compatibility contracts."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from app.driver_catalog import GROUPS, catalog
from app.driver_profiles import REGISTRY
from app.drivers import identify_platform
from app.p3_parsers import COUNTER_COMMANDS, IDENTITY_COMMANDS, INTERFACE_COMMANDS, parse_p3
from app.ssh_profiles import attempt_profiles
from conftest import add_device, login


FIXTURES = Path(__file__).parent / "fixtures" / "p3"
P3 = {
    "h3c_comware5", "h3c_comware9", "huawei_vrp_v600",
    "juniper_junos_evolved", "dell_sonic", "nvidia_cumulus_linux",
    "nvidia_onyx", "sonic_nos", "cisco_business",
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


def test_nine_p3_profiles_are_independent_experimental_runtime_contracts():
    profiles = {profile.id: profile for profile in REGISTRY.profiles if profile.wave == "P3"}
    assert set(profiles) == P3
    assert {profile.runtime_driver_id for profile in profiles.values()} == P3
    for profile in profiles.values():
        assert profile.implementation_status == "implemented"
        assert profile.verification_status == "fixture_verified"
        assert profile.release_status == "experimental"
        assert profile.acceptance.production_accepted is False
        assert profile.profile_revision == 2
        assert next(t for t in profile.transports if t.kind == "ssh").state == "implemented"
        assert {capability.group for capability in profile.capabilities} >= {"fast", "network", "inventory"}

    assert next(t for t in profiles["h3c_comware5"].transports if t.kind == "ssh").decision_gate == "legacy_ssh_device_opt_in_required"
    for identifier in ("dell_sonic", "sonic_nos"):
        snmp = next(t for t in profiles[identifier].transports if t.kind == "snmp")
        assert snmp.state == "planned"
        assert snmp.decision_gate == "distribution_snmpv3_evidence_required"


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda value: value["profile_id"])
def test_exact_tuple_fixture_covers_identity_interfaces_network_and_inventory(system, fixture):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, collector=fixture["runtime_driver_id"])["id"])
    result = parse_p3(device, fixture["runtime_driver_id"], fixture["outputs"], {}, set(GROUPS))
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
    assert network["endpoints"]["entries"][0]["vlan"] == 10
    assert network["endpoints"]["entries"][0]["addresses"] == ["192.0.2.10"]
    assert network["neighbors"][0]["relation"] == "l2"
    assert {"vlan", "fdb", "arp", "lldp"} <= {
        key for key, value in result.metadata["network"].fields.items() if value == "ok"
    }
    assert all(value.reason != "collector_parse_failed" for value in result.metadata.values())


def test_comware_generations_have_distinct_manifests_parsers_and_evidence():
    profiles = [REGISTRY.profile(identifier) for identifier in ("h3c_comware5", "h3c_comware7", "h3c_comware9")]
    assert len({tuple(command.text for command in profile.commands) for profile in profiles}) == 3
    assert {
        next(command.parser for command in profile.commands if command.group == "fast" and command.required)
        for profile in profiles
    } == {"comware5.interfaces", "comware7.interfaces", "comware9.interfaces"}
    assert len({profile.tested_versions for profile in profiles}) == 3


def test_vrp_v600_junos_evolved_and_cisco_business_do_not_alias_classic_families():
    v600 = REGISTRY.profile("huawei_vrp_v600")
    evolved = REGISTRY.profile("juniper_junos_evolved")
    business = REGISTRY.profile("cisco_business")
    assert v600.runtime_driver_id != REGISTRY.profile("huawei_vrp_v200").runtime_driver_id
    assert evolved.runtime_driver_id != REGISTRY.profile("juniper_junos").runtime_driver_id
    assert "| no-more" in next(c.text for c in evolved.commands if c.group == "fast")
    assert {c.text for c in business.commands} != {c.text for c in REGISTRY.profile("cisco_ios").commands}
    assert identify_platform({"display version": "Huawei CloudEngine VRP V600R023C10"}).runtime_driver_id == "huawei_vrp_v600"
    assert identify_platform({"show version": "Junos OS Evolved 23.4R2-EVO"}).runtime_driver_id == "juniper_junos_evolved"
    assert identify_platform({"show version": "System Description : CBS350-24T-4G\nFirmware Version : 3.4.0.17"}).runtime_driver_id == "cisco_business"


def test_sonic_distribution_boundaries_and_unknown_vendor_are_explicit(system):
    client, store, *_ = system
    login(client)
    fixtures = {value["profile_id"]: value for value in load_fixtures()}
    dell = identify_platform({"show version": fixtures["dell_sonic"]["outputs"]["show version"]})
    generic = identify_platform({"show version": fixtures["sonic_nos"]["outputs"]["show version"]})
    assert (dell.profile_id, dell.runtime_driver_id, dell.vendor) == ("dell_sonic", "dell_sonic", "Dell Technologies")
    assert (generic.profile_id, generic.runtime_driver_id, generic.vendor) == ("sonic_nos", "sonic_nos", "Unknown")

    device = store.get_device(add_device(client, collector="sonic_nos")["id"])
    incomplete = dict(fixtures["sonic_nos"]["outputs"])
    incomplete["show version"] = "SONiC Software Version : 202405\nPlatform : x86_64-acme_switch-r0\n"
    result = parse_p3(device, "sonic_nos", incomplete, {}, {"inventory"})
    assert result.observed_profile_id == "sonic_nos"
    assert result.metadata["inventory"].reason == "collector_platform_mismatch"


def test_cumulus_front_panel_breakout_and_kernel_objects_keep_separate_identity(system):
    client, store, *_ = system
    login(client)
    fixture = next(value for value in load_fixtures() if value["profile_id"] == "nvidia_cumulus_linux")
    device = store.get_device(add_device(client, collector="nvidia_cumulus_linux")["id"])
    result = parse_p3(device, "nvidia_cumulus_linux", fixture["outputs"], {}, set(GROUPS))
    by_name = {interface.name: interface for interface in result.device.interfaces}
    assert by_name["swp1s0"].kind == "subinterface"
    assert by_name["bond1"].kind == "port_channel"
    assert {by_name[name].kind for name in ("br_default", "BLUE")} == {"svi"}
    assert len(result.device.physical_ports) == 2
    child = next(port for port in result.device.physical_ports if port.parent_port_id)
    parent = next(port for port in result.device.physical_ports if port.id == child.parent_port_id)
    assert (parent.label, child.label) == ("1", "1/1")
    assert {binding.interface_id for binding in result.device.bindings} == {by_name["swp1s0"].id}
    assert by_name["swp1s0"].id != child.id


def test_linux_ssh_is_not_a_nos_profile_and_onyx_never_uses_nvue():
    linux = REGISTRY.adapter("linux_ssh")
    assert linux.role == "generic_read_only_infrastructure_adapter"
    assert {"dell_sonic", "nvidia_cumulus_linux", "sonic_nos"} <= set(linux.not_equivalent_to)
    assert all(not command.text.startswith("nv ") for command in REGISTRY.profile("nvidia_onyx").commands)
    assert any(command.text.startswith("nv ") for command in REGISTRY.profile("nvidia_cumulus_linux").commands)


def test_comware5_legacy_algorithms_are_device_opt_in_and_not_inherited_by_v600(system):
    client, store, *_ = system
    login(client)
    cw5 = store.get_device(add_device(
        client, collector="h3c_comware5", ssh_profile="auto", allow_legacy_ssh=True,
    )["id"])
    v600 = store.get_device(add_device(client, collector="huawei_vrp_v600", ssh_profile="auto")["id"])
    assert attempt_profiles(cw5) == ["standard", "legacy_sha1", "legacy_cbc", "legacy_ancient"]
    assert attempt_profiles(v600) == ["standard"]
    assert v600.allow_legacy_ssh is False


def test_cross_profile_wrong_match_corpus_fails_closed(system):
    client, store, *_ = system
    login(client)
    fixtures = {value["profile_id"]: value for value in load_fixtures()}
    cases = (
        ("h3c_comware5", "h3c_comware9"),
        ("huawei_vrp_v600", "h3c_comware5"),
        ("juniper_junos_evolved", "nvidia_onyx"),
        ("sonic_nos", "dell_sonic"),
        ("dell_sonic", "sonic_nos"),
        ("cisco_business", "nvidia_onyx"),
    )
    for configured, observed in cases:
        device = store.get_device(add_device(client, collector=configured)["id"])
        observed_identity = IDENTITY_COMMANDS[observed]
        configured_identity = IDENTITY_COMMANDS[configured]
        outputs = {
            configured_identity: fixtures[observed]["outputs"][observed_identity],
        }
        result = parse_p3(device, configured, outputs, {}, {"inventory"})
        assert result.observed_profile_id == observed
        assert result.metadata["inventory"].reason == "collector_platform_mismatch"


@pytest.mark.parametrize("failure", ["collector_permission_denied", "collector_timeout"])
@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda value: value["profile_id"])
def test_required_interface_permission_and_timeout_are_explicit(system, fixture, failure):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, collector=fixture["runtime_driver_id"])["id"])
    identity = IDENTITY_COMMANDS[fixture["runtime_driver_id"]]
    interface = INTERFACE_COMMANDS[fixture["runtime_driver_id"]]
    result = parse_p3(
        device, fixture["runtime_driver_id"], {identity: fixture["outputs"][identity]},
        {interface: failure}, {"fast"},
    )
    assert result.metadata["fast"].reason == "required_command_unavailable"
    assert result.metadata["fast"].diagnostics[interface] == (
        "permission_denied" if failure == "collector_permission_denied" else "timeout"
    )


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda value: value["profile_id"])
def test_malformed_required_interface_output_preserves_existing_inventory(system, fixture):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, collector=fixture["runtime_driver_id"])["id"])
    outputs = dict(fixture["outputs"])
    outputs[INTERFACE_COMMANDS[fixture["runtime_driver_id"]]] = "malformed synthetic output"
    result = parse_p3(device, fixture["runtime_driver_id"], outputs, {}, {"fast"})
    assert result.device == device
    assert result.metadata["fast"].quality == "parse_error"
    assert result.metadata["fast"].reason == "collector_parse_failed"


def test_catalog_and_create_api_expose_all_p3_profiles(system):
    client, *_ = system
    login(client)
    value = catalog(include_v2=True)
    entries = {entry["id"]: entry for entry in value["profiles"] if entry["wave"] == "P3"}
    assert set(entries) == P3
    assert all(entry["selectable"] and entry["release_status"] == "experimental" for entry in entries.values())
    response = client.post("/api/v1/devices", json={
        "name": "Cumulus test", "management_address": "127.0.0.1", "site": "lab",
        "configured_profile_id": "nvidia_cumulus_linux", "management_mode": "standalone",
    })
    assert response.status_code == 201, response.text
    assert response.json()["collector"] == "nvidia_cumulus_linux"
    assert response.json()["configured_profile_id"] == "nvidia_cumulus_linux"
