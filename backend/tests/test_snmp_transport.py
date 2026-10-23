"""Real loopback SNMPv3 authPriv transport; not physical-switch acceptance."""
import asyncio
from bisect import bisect_right
import socket

import pytest
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import config, engine
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.proto import rfc1902, rfc1905
from pysnmp.smi.instrum import AbstractMibInstrumController

from app.driver_catalog import GROUPS
from app.snmp import COLUMNS, SYS_UPTIME, collect_snmp
from app.snmp_mappers import (
    BRIDGE_COLUMNS, ENTITY_COLUMNS, LLDP_COLUMNS, QBRIDGE_COLUMNS,
    SENSOR_COLUMNS, SYSTEM_SCALARS,
)
from app.ssh import ConnectionPolicyError
from conftest import login, prepare


def oid(value):
    return tuple(int(part) for part in value.split("."))


def test_real_snmpv3_sha256_aes128_and_unknown_user(system):
    client, store, app, _ = system
    login(client)
    device_id = prepare(client)["id"]

    async def scenario():
        agent = engine.SnmpEngine()
        transport = udp.UdpTransport().open_server_mode(("127.0.0.1", 0))
        config.add_transport(agent, udp.DOMAIN_NAME, transport)
        await transport._lport  # Wait for the ephemeral test UDP bind.
        port = transport.transport.get_extra_info("sockname")[1]
        config.add_v3_user(agent, "qa-reader", config.USM_AUTH_HMAC192_SHA256, "qa-auth-secret",
                           config.USM_PRIV_CFB128_AES, "qa-privacy-secret")
        config.add_vacm_user(agent, 3, "qa-reader", "authPriv", (1,), contextName=b"qa")
        values = {
            oid(SYSTEM_SCALARS[0]): rfc1902.ObjectIdentifier("1.3.6.1.4.1.9.1.1"),
            oid(SYSTEM_SCALARS[1]): rfc1902.OctetString("Loopback switch"),
            oid(SYSTEM_SCALARS[2]): rfc1902.OctetString("qa-switch"),
            oid(SYS_UPTIME): rfc1902.TimeTicks(12000),
        }
        for index in range(1, 5):
            for name, prefix in COLUMNS.items():
                if name == "name":
                    value = rfc1902.OctetString(f"eth{index}")
                elif name in {"in_octets", "out_octets"}:
                    value = rfc1902.Counter64(2**40 + index)
                elif name == "discontinuity":
                    value = rfc1902.TimeTicks(0)
                elif name == "capacity":
                    value = rfc1902.Gauge32(1000)
                else:
                    value = rfc1902.Integer32(1)
                values[oid(prefix) + (index,)] = value
        values.update({
            oid(BRIDGE_COLUMNS["port_ifindex"]) + (1,): rfc1902.Integer32(1),
            oid(QBRIDGE_COLUMNS["vlan_fid"]) + (10,): rfc1902.Integer32(10),
            oid(QBRIDGE_COLUMNS["pvid"]) + (1,): rfc1902.Integer32(10),
            oid(LLDP_COLUMNS["local_port"]) + (1,): rfc1902.OctetString("eth1"),
            oid(LLDP_COLUMNS["remote_chassis"]) + (0, 1, 1): rfc1902.OctetString("02:00:00:00:00:02"),
            oid(LLDP_COLUMNS["remote_port"]) + (0, 1, 1): rfc1902.OctetString("Ethernet1"),
            oid(LLDP_COLUMNS["remote_name"]) + (0, 1, 1): rfc1902.OctetString("qa-peer"),
        })
        classes = {1: 9, 2: 7, 3: 6, 4: 8}
        for index, entity_class in classes.items():
            values.update({
                oid(ENTITY_COLUMNS["description"]) + (index,): rfc1902.OctetString(f"entity-{index}"),
                oid(ENTITY_COLUMNS["contained_in"]) + (index,): rfc1902.Integer32(0),
                oid(ENTITY_COLUMNS["class"]) + (index,): rfc1902.Integer32(entity_class),
                oid(ENTITY_COLUMNS["parent_position"]) + (index,): rfc1902.Integer32(index),
                oid(ENTITY_COLUMNS["name"]) + (index,): rfc1902.OctetString(f"entity-{index}"),
                oid(ENTITY_COLUMNS["serial"]) + (index,): rfc1902.OctetString(f"serial-{index}"),
            })
        values.update({
            oid(SENSOR_COLUMNS["type"]) + (4,): rfc1902.Integer32(8),
            oid(SENSOR_COLUMNS["scale"]) + (4,): rfc1902.Integer32(9),
            oid(SENSOR_COLUMNS["precision"]) + (4,): rfc1902.Integer32(0),
            oid(SENSOR_COLUMNS["value"]) + (4,): rfc1902.Integer32(42),
            oid(SENSOR_COLUMNS["status"]) + (4,): rfc1902.Integer32(1),
        })
        keys = sorted(values)
        operations = []

        class ReadOnlyMib(AbstractMibInstrumController):
            def read_variables(self, *bindings, **access):
                operations.append("get")
                result = []
                for name, _ in bindings:
                    value = values.get(tuple(name), rfc1905.NoSuchInstance())
                    access["acFun"]("read", (name, value), **access)
                    result.append((name, value))
                return result

            def read_next_variables(self, *bindings, **access):
                operations.append("next")
                result = []
                for name, _ in bindings:
                    index = bisect_right(keys, tuple(name))
                    if index == len(keys):
                        result.append((name, rfc1905.EndOfMibView()))
                    else:
                        pair = (rfc1902.ObjectName(keys[index]), values[keys[index]])
                        access["acFun"]("read", pair, **access)
                        result.append(pair)
                return result

            def write_variables(self, *bindings, **access):
                pytest.fail("A read-only collector must never send SET")

        ctx = context.SnmpContext(agent)
        ctx.register_context_name(b"qa", ReadOnlyMib())
        responders = [cmdrsp.GetCommandResponder(agent, ctx), cmdrsp.BulkCommandResponder(agent, ctx)]
        settings = dict(username="qa-reader", port=port, context="qa", auth_protocol="sha256",
                        privacy_protocol="aes128", auth_password="qa-auth-secret", privacy_password="qa-privacy-secret")

        def save(values):
            with store.engine.begin() as conn:
                app.state.vault.save_protocol(device_id, "snmp", values,
                    {k: v for k, v in values.items() if not k.endswith("password")}, conn)

        try:
            save(settings)
            device = store.get_device(device_id)
            result = await collect_snmp(store, app.state.vault, device, groups=GROUPS)
            assert result.metadata["fast"].source == "snmp"
            assert result.metadata["fast"].complete
            assert len(result.payloads["fast"]["interfaces"]) == 4
            assert result.payloads["fast"]["interfaces"][0]["in_octets"] > 2**32
            assert result.payloads["inventory"]["system_identity"]["sys_name"] == "qa-switch"
            assert len(result.payloads["inventory"]["entities"]) == 4
            assert result.payloads["network"]["interfaces"][0]["pvid"] == 10
            assert result.payloads["network"]["neighbors"][0]["relation"] == "l2"
            assert result.payloads["health"]["health"]["temperature_c"] == 42
            assert all(result.metadata[group].quality == "partial" and not result.metadata[group].complete
                       for group in ("network", "inventory", "health"))
            assert {"get", "next"} == set(operations)
            failures = [
                ({"username": "qa-unknown"}, "snmp_authentication_failed"),
                ({"auth_password": "wrong-auth-secret"}, "snmp_authentication_failed"),
                ({"privacy_password": "wrong-privacy-secret"}, "snmp_authentication_failed"),
                ({"context": "missing"}, "snmp_context_mismatch"),
            ]
            for changes, code in failures:
                save({**settings, **changes})
                with pytest.raises(ConnectionPolicyError) as captured:
                    await collect_snmp(store, app.state.vault, store.get_device(device_id))
                assert str(captured.value) == code
                assert "qa-reader" not in str(captured.value).lower()
                assert "engine" not in str(captured.value).lower()
        finally:
            for responder in responders:
                responder.close(agent)
            agent.close_dispatcher()
            await asyncio.sleep(0)

    asyncio.run(scenario())


def test_real_udp_large_table_limit(system):
    client, store, app, _ = system
    login(client)
    device_id = prepare(client)["id"]

    async def scenario():
        agent = engine.SnmpEngine()
        transport = udp.UdpTransport().open_server_mode(("127.0.0.1", 0))
        config.add_transport(agent, udp.DOMAIN_NAME, transport)
        await transport._lport
        port = transport.transport.get_extra_info("sockname")[1]
        config.add_v3_user(agent, "qa-reader", config.USM_AUTH_HMAC192_SHA256, "qa-auth-secret",
                           config.USM_PRIV_CFB128_AES, "qa-privacy-secret")
        config.add_vacm_user(agent, 3, "qa-reader", "authPriv", (1,), contextName=b"")
        values = {
            oid(SYSTEM_SCALARS[0]): rfc1902.ObjectIdentifier("1.3.6.1.4.1.9.1.1"),
            oid(SYSTEM_SCALARS[1]): rfc1902.OctetString("Large table agent"),
            oid(SYSTEM_SCALARS[2]): rfc1902.OctetString("large-agent"),
            oid(SYS_UPTIME): rfc1902.TimeTicks(100),
            **{oid(COLUMNS["name"]) + (index,): rfc1902.OctetString(f"eth{index}")
               for index in range(1, 4098)},
        }
        keys = sorted(values)

        class LargeMib(AbstractMibInstrumController):
            def read_variables(self, *bindings, **access):
                return [(name, values.get(tuple(name), rfc1905.NoSuchInstance())) for name, _ in bindings]

            def read_next_variables(self, *bindings, **access):
                result = []
                for name, _ in bindings:
                    index = bisect_right(keys, tuple(name))
                    if index == len(keys):
                        result.append((name, rfc1905.EndOfMibView()))
                    else:
                        pair = (rfc1902.ObjectName(keys[index]), values[keys[index]])
                        access["acFun"]("read", pair, **access)
                        result.append(pair)
                return result

        ctx = context.SnmpContext(agent)
        ctx.unregister_context_name(b"")
        ctx.register_context_name(b"", LargeMib())
        responders = [cmdrsp.GetCommandResponder(agent, ctx), cmdrsp.BulkCommandResponder(agent, ctx)]
        settings = dict(username="qa-reader", port=port, context="", auth_protocol="sha256",
                        privacy_protocol="aes128", auth_password="qa-auth-secret", privacy_password="qa-privacy-secret")
        try:
            with store.engine.begin() as conn:
                app.state.vault.save_protocol(device_id, "snmp", settings,
                    {key: value for key, value in settings.items() if not key.endswith("password")}, conn)
            with pytest.raises(ConnectionPolicyError, match="snmp_output_limit"):
                await collect_snmp(store, app.state.vault, store.get_device(device_id))
        finally:
            for responder in responders:
                responder.close(agent)
            agent.close_dispatcher()
            await asyncio.sleep(0)

    asyncio.run(scenario())


def test_real_udp_timeout_and_cancellation_are_typed(system):
    client, store, app, _ = system
    login(client)
    device_id = prepare(client)["id"]
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    settings = dict(username="qa-reader", port=port, context="", auth_protocol="sha256",
                    privacy_protocol="aes128", auth_password="qa-auth-secret", privacy_password="qa-privacy-secret")

    def save():
        with store.engine.begin() as conn:
            app.state.vault.save_protocol(device_id, "snmp", settings,
                {key: value for key, value in settings.items() if not key.endswith("password")}, conn)

    async def scenario():
        save()
        with pytest.raises(ConnectionPolicyError, match="snmp_timeout"):
            await collect_snmp(store, app.state.vault, store.get_device(device_id))
        save()
        task = asyncio.create_task(collect_snmp(store, app.state.vault, store.get_device(device_id)))
        await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
