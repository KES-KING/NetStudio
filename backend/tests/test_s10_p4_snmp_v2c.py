"""S10 P4 SNMPv2c opt-in and protocol-boundary contracts."""
from __future__ import annotations

import asyncio
from bisect import bisect_right
from hashlib import sha256
import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import config, engine
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.proto import rfc1902, rfc1905
from pysnmp.smi.instrum import AbstractMibInstrumController

from app.driver_catalog import catalog
from app.driver_profiles import REGISTRY
from app.snmp import collect_snmp
from app.snmp_mappers import (
    BRIDGE_COLUMNS, IF_COLUMNS, QBRIDGE_COLUMNS, QBRIDGE_FDB_COLUMNS,
    SYSTEM_SCALARS,
)
from app.snmp_transport import PysnmpV2cSession
from app.ssh import ConnectionPolicyError
from app.transport import TransportContext
from app.worker import implemented_transports
from conftest import PASSWORD, add_device, login


FIXTURES = Path(__file__).parent / "fixtures" / "p4"


def fixture():
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    assert manifest["physical_acceptance"] is False
    assert manifest["production_accepted"] is False
    entry = manifest["files"][0]
    raw = (FIXTURES / entry["path"]).read_bytes()
    assert sha256(raw).hexdigest() == entry["sha256"]
    value = json.loads(raw)
    assert value["source_permission"] == "project_generated_test_fixture"
    return value


def swos_device(client, monkeypatch):
    monkeypatch.setenv("NETSTUDIO_ALLOW_SNMP_V2C", "1")
    return add_device(
        client, configured_profile_id="mikrotik_swos",
        management_mode="standalone", vendor="MikroTik",
    )


def risk_payload(community="test-only-v2c-community"):
    return {
        "community": community, "port": 161,
        "read_only_confirmed": True, "acl_confirmed": True,
        "management_isolation_confirmed": True,
        "unencrypted_confirmed": True,
    }


def oid(value):
    return tuple(int(part) for part in value.split("."))


def test_adr_result_and_catalog_are_installation_gated(monkeypatch):
    profile = REGISTRY.profile("mikrotik_swos")
    assert profile.implementation_status == "implemented"
    assert profile.verification_status == "transport_lab_validated"
    assert profile.release_status == "experimental"
    assert profile.runtime_driver_id == "mikrotik_swos"
    snmp = next(item for item in profile.transports if item.kind == "snmp")
    assert snmp.state == "implemented" and snmp.versions == ("v2c",)
    assert {"installation_opt_in", "superadmin_device_opt_in", "unencrypted_transport"} <= set(snmp.security)

    monkeypatch.setenv("NETSTUDIO_ALLOW_SNMP_V2C", "true")
    malformed = catalog(include_v2=True)
    assert malformed["features"]["snmp_v2c_enabled"] is False

    monkeypatch.setenv("NETSTUDIO_ALLOW_SNMP_V2C", "0")
    disabled = catalog(include_v2=True)
    entry = next(item for item in disabled["profiles"] if item["id"] == "mikrotik_swos")
    assert disabled["features"]["snmp_v2c_enabled"] is False
    assert not entry["available"] and not entry["selectable"]
    assert entry["availability_reason"] == "snmp_v2c_installation_disabled"
    assert entry["transports"]["snmp"]["state"] == "unsupported_by_policy"

    monkeypatch.setenv("NETSTUDIO_ALLOW_SNMP_V2C", "1")
    enabled = catalog(include_v2=True)
    entry = next(item for item in enabled["profiles"] if item["id"] == "mikrotik_swos")
    assert enabled["features"]["snmp_v2c_enabled"] is True
    assert entry["available"] and entry["selectable"]
    assert entry["transports"]["snmp"]["state"] == "implemented"


def test_default_off_profile_and_credentials_fail_closed(system, monkeypatch):
    client, *_ = system
    login(client)
    monkeypatch.setenv("NETSTUDIO_ALLOW_SNMP_V2C", "0")
    response = client.post("/api/v1/devices", json={
        "name": "SwOS disabled", "management_address": "127.0.0.1",
        "site": "lab", "configured_profile_id": "mikrotik_swos",
        "management_mode": "standalone",
    })
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "snmp_v2c_installation_disabled"

    monkeypatch.setenv("NETSTUDIO_ALLOW_SNMP_V2C", "1")
    device = swos_device(client, monkeypatch)
    monkeypatch.setenv("NETSTUDIO_ALLOW_SNMP_V2C", "0")
    assert implemented_transports(client.app.state.store.get_device(device["id"])) == set()
    polling = client.get(f"/api/v1/devices/{device['id']}/polling")
    assert polling.status_code == 200
    assert polling.json()["readiness"] == "snmp_v2c_installation_disabled"
    response = client.put(
        f"/api/v1/devices/{device['id']}/snmp-v2c-credentials",
        json=risk_payload(),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "snmp_v2c_installation_disabled"


def test_v2c_requires_superadmin_all_confirmations_and_never_returns_secret(system, monkeypatch):
    client, store, app, _ = system
    login(client)
    device = swos_device(client, monkeypatch)
    path = f"/api/v1/devices/{device['id']}/snmp-v2c-credentials"

    login(client, "operator")
    assert client.put(path, json=risk_payload()).status_code == 403
    login(client)
    incomplete = {**risk_payload(), "acl_confirmed": False}
    assert client.put(path, json=incomplete).status_code == 422

    community = "test-only-v2c-community"
    response = client.put(path, json=risk_payload(community))
    assert response.status_code == 200
    assert response.json() == {
        "snmp_configured": True, "snmp_version": "v2c",
        "snmp_v2c_risk_accepted": True,
    }
    assert community not in response.text

    current = client.get(f"/api/v1/devices/{device['id']}")
    assert current.status_code == 200
    assert current.json()["snmp_version"] == "v2c"
    assert current.json()["snmp_v2c_risk_accepted"] is True
    assert community not in current.text

    with store.engine.connect() as conn:
        row = conn.execute(sa.select(store.protocol_secrets).where(
            store.protocol_secrets.c.device_id == device["id"],
        )).mappings().one()
        events = list(conn.execute(sa.select(store.audit.c.details).where(
            store.audit.c.device_id == device["id"],
            store.audit.c.event == "snmp.v2c.risk_accepted",
        )).scalars())
    assert row["protocol"] == "snmp_v2c"
    assert community.encode() not in row["ciphertext"]
    assert community not in json.dumps(row["metadata"])
    assert events and community not in json.dumps(events)
    assert app.state.vault.get_protocol(device["id"], "snmp_v2c")["community"] == community

    monkeypatch.setenv("NETSTUDIO_ALLOW_SNMP_V2C", "0")
    removed = client.delete(f"/api/v1/devices/{device['id']}/snmp-credentials")
    assert removed.status_code == 200
    assert removed.json()["snmp_v2c_risk_accepted"] is False
    assert store.get_device(device["id"]).snmp_configured is False
    with store.engine.connect() as conn:
        assert conn.execute(sa.select(store.audit.c.id).where(
            store.audit.c.device_id == device["id"],
            store.audit.c.event == "snmp.v2c.risk_withdrawn",
        )).first()


def test_v2c_never_downgrades_v3_profiles_and_swos_rejects_v3(system, monkeypatch):
    client, *_ = system
    login(client)
    monkeypatch.setenv("NETSTUDIO_ALLOW_SNMP_V2C", "1")
    ios = add_device(
        client, configured_profile_id="cisco_ios", management_mode="standalone",
    )
    response = client.put(
        f"/api/v1/devices/{ios['id']}/snmp-v2c-credentials", json=risk_payload(),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "snmp_v2c_profile_not_allowed"

    swos = swos_device(client, monkeypatch)
    response = client.put(f"/api/v1/devices/{swos['id']}/snmp-credentials", json={
        "username": "reader", "port": 161, "context": "",
        "auth_protocol": "sha256", "privacy_protocol": "aes128",
        "auth_password": "test-auth-password", "privacy_password": "test-privacy-password",
    })
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "snmp_v3_not_supported_by_profile"


def test_conflicting_stored_snmp_versions_fail_closed(system, monkeypatch):
    client, store, app, _ = system
    login(client)
    device_id = swos_device(client, monkeypatch)["id"]
    with store.engine.begin() as conn:
        app.state.vault.save_protocol(
            device_id, "snmp_v2c",
            {"version": "v2c", "community": "test-only-v2c-community", "port": 161},
            {"version": "v2c", "risk_accepted": True}, conn,
        )
        app.state.vault.save_protocol(
            device_id, "snmp",
            {
                "username": "reader", "auth_protocol": "sha256",
                "privacy_protocol": "aes128", "auth_password": "test-auth-password",
                "privacy_password": "test-privacy-password", "port": 161,
            },
            {"username": "reader", "auth_protocol": "sha256", "privacy_protocol": "aes128"},
            conn,
        )
    device = store.get_device(device_id)
    assert device.snmp_configured is True
    assert device.snmp_version is None
    login(client, "operator")
    response = client.delete(f"/api/v1/devices/{device_id}/snmp-credentials")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "snmp_v2c_superadmin_required"
    login(client)
    with pytest.raises(ConnectionPolicyError, match="snmp_protocol_conflict"):
        asyncio.run(collect_snmp(store, app.state.vault, device, groups=("inventory",)))


def test_stored_v2c_without_risk_acceptance_never_runs(system, monkeypatch):
    client, store, app, _ = system
    login(client)
    device_id = swos_device(client, monkeypatch)["id"]
    with store.engine.begin() as conn:
        app.state.vault.save_protocol(
            device_id, "snmp_v2c",
            {"version": "v2c", "community": "test-only-v2c-community", "port": 161},
            {"version": "v2c", "port": 161, "risk_accepted": False}, conn,
        )
    device = store.get_device(device_id)
    assert device.snmp_version == "v2c"
    assert device.snmp_v2c_risk_accepted is False
    polling = client.get(f"/api/v1/devices/{device_id}/polling")
    assert polling.status_code == 200
    assert polling.json()["readiness"] == "snmp_v2c_device_approval_required"
    assert polling.json()["ready_transports"] == []
    with pytest.raises(ConnectionPolicyError, match="snmp_v2c_device_approval_required"):
        asyncio.run(collect_snmp(store, app.state.vault, device, groups=("inventory",)))


def test_v2c_session_is_version_two_and_only_exposes_read_operations(system, monkeypatch):
    client, store, _, _ = system
    login(client)
    device = store.get_device(swos_device(client, monkeypatch)["id"])
    credentials = {"community": "test-only-v2c-community", "port": 161}
    session = PysnmpV2cSession(
        TransportContext.create(store, None, device), credentials,
    )
    try:
        assert session.user.message_processing_model == 1
        assert session.user.security_model == 2
        assert not hasattr(session, "set")
    finally:
        session.close()
    assert credentials == {}


def test_real_loopback_v2c_collects_swos_identity_interfaces_and_fdb(system, monkeypatch):
    client, store, app, _ = system
    login(client)
    fixture_value = fixture()
    device_id = swos_device(client, monkeypatch)["id"]

    async def scenario():
        agent = engine.SnmpEngine()
        transport = udp.UdpTransport().open_server_mode(("127.0.0.1", 0))
        config.add_transport(agent, udp.DOMAIN_NAME, transport)
        await transport._lport
        port = transport.transport.get_extra_info("sockname")[1]
        community = "test-only-v2c-community"
        config.add_v1_system(
            agent, "netstudio-test", community, securityName="netstudio-reader",
        )
        config.add_vacm_user(
            agent, 2, "netstudio-reader", "noAuthNoPriv", readSubTree=(1,),
        )

        system_value = fixture_value["system"]
        values = {
            oid(SYSTEM_SCALARS[0]): rfc1902.ObjectIdentifier(system_value["sys_object_id"]),
            oid(SYSTEM_SCALARS[1]): rfc1902.OctetString(system_value["sys_descr"]),
            oid(SYSTEM_SCALARS[2]): rfc1902.OctetString(system_value["sys_name"]),
            oid(SYSTEM_SCALARS[3]): rfc1902.TimeTicks(system_value["sys_uptime_ticks"]),
        }
        for row in fixture_value["interfaces"]:
            index = row["if_index"]
            values.update({
                oid(IF_COLUMNS["name"]) + (index,): rfc1902.OctetString(row["name"]),
                oid(IF_COLUMNS["admin_up"]) + (index,): rfc1902.Integer32(row["admin_up"]),
                oid(IF_COLUMNS["oper_up"]) + (index,): rfc1902.Integer32(row["oper_up"]),
                oid(IF_COLUMNS["capacity"]) + (index,): rfc1902.Gauge32(row["capacity_mbps"]),
                oid(IF_COLUMNS["in_octets"]) + (index,): rfc1902.Counter64(row["in_octets"]),
                oid(IF_COLUMNS["out_octets"]) + (index,): rfc1902.Counter64(row["out_octets"]),
                oid(IF_COLUMNS["errors"]) + (index,): rfc1902.Counter32(row["errors"]),
                oid(IF_COLUMNS["discards"]) + (index,): rfc1902.Counter32(row["discards"]),
                oid(IF_COLUMNS["tx_errors"]) + (index,): rfc1902.Counter32(row["tx_errors"]),
                oid(IF_COLUMNS["tx_discards"]) + (index,): rfc1902.Counter32(row["tx_discards"]),
                oid(IF_COLUMNS["discontinuity"]) + (index,): rfc1902.TimeTicks(row["discontinuity"]),
            })
        bridge = fixture_value["bridge"]
        mac = tuple(int(part, 16) for part in bridge["mac"].split(":"))
        values.update({
            oid(BRIDGE_COLUMNS["port_ifindex"]) + (bridge["bridge_port"],): rfc1902.Integer32(bridge["if_index"]),
            oid(QBRIDGE_COLUMNS["vlan_fid"]) + (0, bridge["vlan"]): rfc1902.Integer32(bridge["fid"]),
            oid(QBRIDGE_COLUMNS["pvid"]) + (bridge["bridge_port"],): rfc1902.Integer32(bridge["vlan"]),
            oid(QBRIDGE_FDB_COLUMNS["fdb_port"]) + (bridge["fid"], *mac): rfc1902.Integer32(bridge["bridge_port"]),
            oid(QBRIDGE_FDB_COLUMNS["fdb_status"]) + (bridge["fid"], *mac): rfc1902.Integer32(bridge["status"]),
        })
        keys, operations = sorted(values), []

        class ReadOnlyMib(AbstractMibInstrumController):
            def read_variables(self, *bindings, **access):
                operations.append("get")
                return [(name, values.get(tuple(name), rfc1905.NoSuchInstance())) for name, _ in bindings]

            def read_next_variables(self, *bindings, **access):
                operations.append("next")
                result = []
                for name, _ in bindings:
                    index = bisect_right(keys, tuple(name))
                    result.append((name, rfc1905.EndOfMibView()) if index == len(keys) else (
                        rfc1902.ObjectName(keys[index]), values[keys[index]],
                    ))
                return result

            def write_variables(self, *bindings, **access):
                pytest.fail("SNMPv2c collector must never send SET")

        snmp_context = context.SnmpContext(agent)
        snmp_context.unregister_context_name(b"")
        snmp_context.register_context_name(b"", ReadOnlyMib())
        responders = [
            cmdrsp.GetCommandResponder(agent, snmp_context),
            cmdrsp.BulkCommandResponder(agent, snmp_context),
        ]
        secret = {"version": "v2c", "community": community, "port": port}
        try:
            with store.engine.begin() as conn:
                app.state.vault.save_protocol(
                    device_id, "snmp_v2c", secret,
                    {"version": "v2c", "port": port, "risk_accepted": True}, conn,
                )
            result = await collect_snmp(
                store, app.state.vault, store.get_device(device_id),
                groups=("fast", "network", "inventory"),
            )
            assert result.observed_profile_id == "mikrotik_swos"
            assert result.device.vendor == fixture_value["expected"]["vendor"]
            assert result.device.model == fixture_value["model"]
            assert result.device.os_version == fixture_value["os_version"]
            assert result.inventory_complete is True
            assert [item.name for item in result.device.interfaces] == ["ether1"]
            assert result.device.physical_ports == []
            assert result.payloads["fast"]["interfaces"][0]["in_octets"] > 2**32
            assert len(result.payloads["network"]["endpoints"]["entries"]) == 1
            assert set(operations) == {"get", "next"}
        finally:
            for responder in responders:
                responder.close(agent)
            agent.close_dispatcher()
            await asyncio.sleep(0)

    asyncio.run(scenario())


def test_protocol_outside_profiles_are_explicit_and_have_no_credential_transport():
    for identifier in ("tplink_easy_smart", "unmanaged_switch"):
        profile = REGISTRY.profile(identifier)
        assert profile.implementation_status == "unsupported_by_protocol"
        assert profile.operator_guidance
        assert all(transport.state == "unsupported_by_protocol" for transport in profile.transports)
        assert profile.runtime_driver_id is None
    unifi = REGISTRY.profile("ubiquiti_unifi_no_snmp")
    assert next(item for item in unifi.transports if item.kind == "snmp").state == "unsupported_by_protocol"
    instant_on = REGISTRY.profile("aruba_instant_on")
    assert instant_on.implementation_status == "blocked"
    assert next(item for item in instant_on.transports if item.kind == "api").state == "unsupported_by_policy"
