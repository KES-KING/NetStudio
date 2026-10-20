"""Real loopback SNMPv3 authPriv transport; not physical-switch acceptance."""
import asyncio
from bisect import bisect_right

import pytest
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import config, engine
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.proto import rfc1902, rfc1905
from pysnmp.smi.instrum import AbstractMibInstrumController

from app.snmp import COLUMNS, SYS_UPTIME, collect_snmp
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
        config.add_vacm_user(agent, 3, "qa-reader", "authPriv", (1, 3, 6, 1, 2, 1), contextName=b"qa")
        values = {oid(SYS_UPTIME): rfc1902.TimeTicks(12000)}
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
            result = await collect_snmp(store, app.state.vault, device)
            assert result.metadata["fast"].source == "snmp"
            assert result.metadata["fast"].complete
            assert len(result.payloads["fast"]["interfaces"]) == 4
            assert result.payloads["fast"]["interfaces"][0]["in_octets"] > 2**32
            assert {"get", "next"} == set(operations)
            save({**settings, "username": "qa-unknown"})
            with pytest.raises(ConnectionPolicyError, match="snmp_authentication_failed"):
                await collect_snmp(store, app.state.vault, store.get_device(device_id))
        finally:
            for responder in responders:
                responder.close(agent)
            agent.close_dispatcher()
            await asyncio.sleep(0)

    asyncio.run(scenario())
