"""S05 canonical P0 manifests, parser coverage and re-resolution gates."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import sqlalchemy as sa

from app.collection import ReadResult, merge_read_results, metadata, persist
from app.database import now
from app.driver_catalog import GROUPS
from app.driver_profiles import IOS, IOSXE, REGISTRY
from app.drivers import parse_text
from app.profile_resolution import record_collected_resolution
from app.structured_parsers import parse_structured
from conftest import add_device, login, prepare
from test_cisco import OUTPUTS as IOS_OUTPUTS
from test_huawei import OUTPUTS as VRP_OUTPUTS


FIXTURES = Path(__file__).parent / "fixtures" / "p0"


def load_iosxe_fixtures():
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    result = []
    for entry in manifest["files"]:
        raw = (FIXTURES / entry["path"]).read_bytes()
        assert sha256(raw).hexdigest() == entry["sha256"]
        result.append(json.loads(raw))
    return result


def test_ios_and_iosxe_have_independent_manifests_and_two_bounded_fixtures(system):
    assert IOS is not IOSXE
    assert IOS != IOSXE
    assert all(command.parser.startswith("ios.") or command.parser.startswith("ntc.") for command in IOS)
    assert all(command.parser.startswith("iosxe.") or command.parser.startswith("ntc.") for command in IOSXE)
    fixtures = load_iosxe_fixtures()
    assert {(value["model"], value["os_version"]) for value in fixtures} == {
        ("C9200L-24P-4G", "17.12.3"), ("C9300-24T", "17.9.5"),
    }
    client, store, *_ = system
    login(client)
    for fixture in fixtures:
        device = store.get_device(add_device(client, collector="cisco_iosxe")["id"])
        result = parse_text(device, "cisco_iosxe", fixture["outputs"], {}, {"fast", "inventory"})
        expected = fixture["expected"]
        assert result.observed_profile_id == "cisco_iosxe"
        assert result.metadata["fast"].quality == "ok"
        assert result.device.model == expected["model"] == fixture["model"]
        assert result.device.os_version == expected["parsed_os_version"]
        assert result.device.serial == expected["serial"]
        interface = next(value for value in result.device.interfaces if value.name == expected["interface_name"])
        sample = next(value for value in result.payloads["fast"]["interfaces"] if value["interface_id"] == interface.id)
        assert sample["admin_up"] is expected["admin_up"]
        assert sample["oper_up"] is expected["oper_up"]


def test_nxos_all_manifest_commands_are_mapped_without_silent_network_gap(system):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, collector="cisco_nxos")["id"])
    outputs = {
        "show version | json": json.dumps({
            "chassis_id": "N9K-C93180YC-FX", "nxos_ver_str": "10.3(4a)",
            "proc_board_id": "TEST-SERIAL-NXOS", "software": "NX-OS",
        }),
        "show interface | json": json.dumps({"TABLE_interface": {"ROW_interface": {
            "interface": "Ethernet1/1", "admin_state": "up", "state": "up",
            "eth_speed": "10 Gbps", "eth_duplex": "full", "eth_inbytes": "1000",
            "eth_outbytes": "2000", "eth_inerr": "0", "eth_outerr": "0",
            "eth_indiscard": "0", "eth_outdiscard": "0",
            "eth_load_interval1_rx": "30", "eth_load_interval1_tx": "30",
            "eth_inrate1_bits": "800", "eth_outrate1_bits": "1600"
        }}}),
        "show system resources | json": json.dumps({
            "cpu_state_idle": "90", "memory_usage_total": "1000", "memory_usage_used": "250",
        }),
        "show lldp neighbors detail | json": json.dumps({"TABLE_nbor_detail": {"ROW_nbor_detail": {
            "l_port_id": "Ethernet1/1", "chassis_id": "02:00:00:00:00:02",
            "port_id": "Ethernet1", "sys_name": "peer.example.test",
        }}}),
        "show mac address-table | json": json.dumps({"TABLE_mac_address": {"ROW_mac_address": {
            "disp_mac_addr": "0200.0000.0010", "disp_vlan": "10",
            "disp_port": "Ethernet1/1", "disp_type": "dynamic",
        }}}),
        "show inventory | json": json.dumps({"TABLE_inv": {"ROW_inv": {
            "name": "Chassis", "desc": "Nexus chassis", "productid": "N9K-C93180YC-FX",
            "serialnum": "TEST-SERIAL-NXOS",
        }}}),
    }
    result = parse_structured(device, "cisco_nxos", outputs, {}, set(GROUPS))
    assert all("collector_parse_failed" not in meta.diagnostics for meta in result.metadata.values())
    assert result.payloads["network"]["endpoints"]["entries"][0]["vlan"] == 10
    assert result.payloads["network"]["neighbors"][0]["relation"] == "l2"
    assert result.payloads["inventory"]["modules"][0]["part_number"] == "N9K-C93180YC-FX"
    assert result.metadata["network"].fields["fdb"] == "ok"
    assert result.metadata["network"].fields["lldp"] == "ok"


def test_junos_fdb_arp_environment_and_lldp_are_typed(system):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, collector="juniper_junos")["id"])
    outputs = {
        "show version | display xml": "<rpc-reply><software-information><host-name>switch.example.test</host-name><product-model>EX4300-48T</product-model><junos-version>21.4R3-S5.4</junos-version></software-information></rpc-reply>",
        "show interfaces extensive | display xml": "<rpc-reply><interface-information><physical-interface><name>ge-0/0/0</name><admin-status>up</admin-status><oper-status>up</oper-status><speed>1Gbps</speed><snmp-index>7</snmp-index><traffic-statistics><input-bytes>1000</input-bytes><output-bytes>2000</output-bytes></traffic-statistics><logical-interface><name>ge-0/0/0.0</name><address-family><address-family-name>inet</address-family-name><interface-address><ifa-local>192.0.2.2</ifa-local><ifa-destination>192.0.2.0/24</ifa-destination></interface-address></address-family></logical-interface></physical-interface></interface-information></rpc-reply>",
        "show chassis routing-engine | display xml": "<rpc-reply><route-engine><slot>0</slot><cpu-idle>88</cpu-idle><memory-buffer-utilization>31</memory-buffer-utilization></route-engine></rpc-reply>",
        "show chassis environment | display xml": "<rpc-reply><environment-information><environment-item><name>FPC 0 Temp</name><class>Temp</class><status>OK</status><temperature>42 degrees C</temperature></environment-item><environment-item><name>Fan 0</name><class>Fans</class><status>OK</status></environment-item><environment-item><name>PEM 0</name><class>Power</class><status>OK</status></environment-item></environment-information></rpc-reply>",
        "show lldp neighbors | display xml": "<rpc-reply><lldp-neighbors-information><lldp-neighbor-information><lldp-local-interface>ge-0/0/0</lldp-local-interface><lldp-remote-system-name>peer.example.test</lldp-remote-system-name><lldp-remote-chassis-id>02:00:00:00:00:02</lldp-remote-chassis-id><lldp-remote-port-id>Ethernet1</lldp-remote-port-id></lldp-neighbor-information></lldp-neighbors-information></rpc-reply>",
        "show ethernet-switching table | display xml": "<rpc-reply><l2ng-l2ald-rtb-macdb><l2ng-l2ald-mac-entry-vlan><l2ng-l2-mac-address>02:00:00:00:00:10</l2ng-l2-mac-address><l2ng-l2-mac-logical-interface>ge-0/0/0.0</l2ng-l2-mac-logical-interface><l2ng-l2-vlan-id>10</l2ng-l2-vlan-id></l2ng-l2ald-mac-entry-vlan></l2ng-l2ald-rtb-macdb></rpc-reply>",
        "show arp no-resolve | display xml": "<rpc-reply><arp-table-information><arp-table-entry><mac-address>02:00:00:00:00:10</mac-address><ip-address>192.0.2.10</ip-address><interface-name>ge-0/0/0.0</interface-name></arp-table-entry></arp-table-information></rpc-reply>",
        "show chassis hardware | display xml": "<rpc-reply><chassis-inventory><chassis><serial-number>TEST-SERIAL-JUNOS</serial-number><chassis-module><name>FPC 0</name><description>EX4300-48T</description><serial-number>TEST-MODULE-1</serial-number><part-number>TEST-PART-1</part-number></chassis-module></chassis></chassis-inventory></rpc-reply>",
    }
    result = parse_structured(device, "juniper_junos", outputs, {}, set(GROUPS))
    endpoint = result.payloads["network"]["endpoints"]["entries"][0]
    assert endpoint["addresses"] == ["192.0.2.10"] and endpoint["vlan"] == 10
    assert result.payloads["health"]["health"]["temperature_c"] == 42
    assert result.payloads["health"]["health"]["fan"] == "Fan 0: OK"
    assert result.payloads["health"]["health"]["power_supply"] == "PEM 0: OK"
    assert result.metadata["network"].fields["fdb"] == "ok"
    assert result.metadata["network"].fields["arp"] == "ok"


def test_huawei_legacy_runtime_resolves_only_to_v200_without_rewriting_record(system):
    client, store, *_ = system
    login(client)
    created = prepare(client, collector="huawei_vrp")
    original = store.get_device(created["id"])
    with store.engine.begin() as conn:
        conn.execute(store.secrets.insert().values(
            device_id=original.id, key_id="test-key", nonce=b"test-nonce",
            ciphertext=b"test-ciphertext",
        ))
    result = parse_text(original, "huawei_vrp", VRP_OUTPUTS, {}, set(GROUPS))
    assert result.observed_profile_id == "huawei_vrp_v200"
    with store.engine.begin() as conn:
        record_collected_resolution(
            store, result.device, conn,
            observed_profile_id=result.observed_profile_id,
            identity_evidence=result.identity_evidence,
        )
    current = store.get_device(original.id)
    binding = store.get_driver_binding(original.id)
    resolution_projection = {
        "configured_profile_id", "resolved_profile_id", "profile_revision",
        "management_mode", "profile_resolution_status", "credential_configured",
    }
    assert current.model_dump(exclude=resolution_projection) == original.model_dump(
        exclude=resolution_projection
    )
    assert binding["legacy_collector_id"] == "huawei_vrp"
    assert binding["resolved_profile_id"] == "huawei_vrp_v200"
    assert binding["resolution_status"] == "matched"
    with store.engine.connect() as conn:
        secret = conn.execute(sa.select(store.secrets).where(
            store.secrets.c.device_id == original.id
        )).mappings().one()
    assert secret["nonce"] == b"test-nonce"
    assert secret["ciphertext"] == b"test-ciphertext"


def test_os_family_conflict_and_reboot_invalidate_only_derived_caches(system):
    client, store, *_ = system
    login(client)
    created = add_device(client, collector="cisco_ios")
    original = store.get_device(created["id"])
    persist(store, original, parse_text(original, "cisco_ios", IOS_OUTPUTS, {}, set(GROUPS)))
    current = store.get_device(original.id)
    with store.engine.begin() as conn:
        conn.execute(store.capabilities.insert().values(
            device_id=current.id, command_id="show optional", revision_key="old",
            status="collector_command_unsupported", checked_at=now(),
        ))
    fixture = load_iosxe_fixtures()[0]
    mismatch = parse_text(current, "cisco_ios", fixture["outputs"], {}, {"inventory"})
    assert mismatch.observed_profile_id == "cisco_iosxe"
    persist(store, current, mismatch)
    binding = store.get_driver_binding(current.id)
    assert binding["resolution_status"] == "conflict"
    assert binding["resolution_conflicts"] == ["configured_profile_mismatch"]
    with store.engine.connect() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(store.capabilities)).scalar_one() == 0
        assert conn.execute(sa.select(sa.func.count()).select_from(store.capability_observations_v2)).scalar_one() == 0
        assert conn.execute(sa.select(sa.func.count()).select_from(store.collection_groups)).scalar_one() > 0

    # A reboot removes the resolved identity/capability cache, but not the
    # inventory or prior group projections needed for last-good behavior.
    current = store.get_device(current.id)
    persist(store, current, ReadResult(current, reboot_detected=True))
    binding = store.get_driver_binding(current.id)
    assert binding["resolution_status"] == "unresolved"
    assert binding["resolved_profile_id"] is None
    assert store.latest(current.id) is not None


def test_os_version_change_and_model_contradiction_force_fresh_resolution(system):
    client, store, *_ = system
    login(client)
    created = add_device(client, collector="cisco_ios")
    original = store.get_device(created["id"])
    persist(store, original, parse_text(original, "cisco_ios", IOS_OUTPUTS, {}, set(GROUPS)))
    current = store.get_device(original.id)

    def remember_negative():
        with store.engine.begin() as conn:
            conn.execute(store.capabilities.insert().values(
                device_id=current.id, command_id="show optional", revision_key="old",
                status="collector_command_unsupported", checked_at=now(),
            ))

    def negative_count():
        with store.engine.connect() as conn:
            return conn.execute(sa.select(sa.func.count()).select_from(store.capabilities).where(
                store.capabilities.c.device_id == current.id
            )).scalar_one()

    remember_negative()
    with store.engine.begin() as conn:
        record_collected_resolution(
            store, current, conn, observed_profile_id="cisco_ios",
            identity_evidence={
                "vendor": "Cisco", "model": current.model, "os_family": "IOS",
                "os_version": "15.2(7)E9", "management_mode": current.management_mode,
            },
        )
    assert store.get_driver_binding(current.id)["resolution_status"] == "matched"
    assert negative_count() == 0

    remember_negative()
    with store.engine.begin() as conn:
        record_collected_resolution(
            store, current, conn, observed_profile_id="cisco_ios",
            identity_evidence={
                "vendor": "Cisco", "model": "C9300-24T", "os_family": "IOS",
                "os_version": "15.2(7)E9", "management_mode": current.management_mode,
            },
        )
    binding = store.get_driver_binding(current.id)
    assert binding["resolution_status"] == "conflict"
    assert binding["resolution_conflicts"] == ["model_mismatch"]
    assert negative_count() == 0


def test_profile_source_fields_match_actual_transport_boundaries():
    for identifier in (
        "cisco_ios", "cisco_iosxe", "cisco_nxos", "huawei_vrp_v200",
        "juniper_junos",
    ):
        profile = REGISTRY.profile(identifier)
        by_group = {capability.group: capability for capability in profile.capabilities}
        assert "fdb" in by_group["network"].source_fields["snmp"]
        assert "lldp" in by_group["network"].source_fields["snmp"]
        assert "arp" not in by_group["network"].source_fields["snmp"]
        assert "system_identity" in by_group["inventory"].source_fields["snmp"]
        assert set(by_group["network"].fields) == {
            field for fields in by_group["network"].source_fields.values()
            for field in fields
        }


def test_ssh_snmp_profile_identity_conflict_is_fail_closed(system):
    client, store, *_ = system
    login(client)
    device = store.get_device(add_device(client, collector="cisco_ios")["id"])
    ssh = ReadResult(device, metadata={
        "inventory": metadata("inventory", "cisco_ios", source="ssh"),
    })
    ssh.observed_profile_id = "cisco_ios"
    ssh.identity_evidence = {
        "vendor": "Cisco", "model": "WS-C2960X-48FPD-L",
        "os_family": "IOS", "os_version": "15.2(7)E",
        "management_mode": device.management_mode,
    }
    snmp = ReadResult(device, metadata={
        "inventory": metadata("inventory", "snmp_system_entity", source="snmp"),
    })
    snmp.observed_profile_id = "cisco_nxos"
    snmp.identity_evidence = {
        "vendor": "Cisco", "os_family": "NX-OS",
        "sys_object_id": "1.3.6.1.4.1.9.1.1",
        "management_mode": device.management_mode,
    }
    merged = merge_read_results(ssh, snmp)
    assert merged.observed_profile_id == "cisco_ios"
    assert merged.identity_conflicts == ["transport_identity_mismatch"]
    persist(store, device, merged)
    binding = store.get_driver_binding(device.id)
    assert binding["resolution_status"] == "conflict"
    assert binding["resolution_conflicts"] == ["transport_identity_mismatch"]
