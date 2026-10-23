"""S04 bounded reader, standard mapper, merge and channel-state contracts."""
from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
import sqlalchemy as sa

from app import scheduler
from app.collection import ReadResult, metadata, persist
from app.contracts import Telemetry
from app.database import now
from app.driver_profiles import REGISTRY
from app.snmp_mappers.bridge import parse_bridge_mib
from app.snmp_mappers.entity import parse_entity_mib
from app.snmp_mappers.interfaces import parse_if_mib
from app.snmp_mappers.lldp import parse_lldp_mib
from app.snmp_mappers.system import (
    SYS_DESCR, SYS_NAME, SYS_OBJECT_ID, SYS_UPTIME, parse_system_mib,
)
from app.snmp_transport import BoundedSNMPReader, SNMPLimits, numeric_oid
from app.ssh import ConnectionPolicyError
from app.telemetry import normalize
from app.transport import TransportContext
from conftest import login, prepare


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    async def request(self, operation, oids, *, max_repetitions):
        self.calls += 1
        return self.response(operation, oids, max_repetitions, self.calls)

    def close(self):
        pass


def test_implemented_profiles_publish_generic_snmp_without_physical_promotion():
    for identifier in ("cisco_ios", "cisco_iosxe", "cisco_nxos", "huawei_vrp_v200", "juniper_junos"):
        profile = REGISTRY.profile(identifier)
        assert all("snmp" in capability.sources for capability in profile.capabilities)
        assert profile.verification_status != "physical_validated"
        assert not profile.acceptance.production_accepted


def test_common_transport_context_enforces_deadline_fence_timeout_and_cancel():
    checks = 0

    def fence():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise ConnectionPolicyError("worker_lease_lost")

    async def scenario():
        context = TransportContext.create(None, None, None, fence, timeout_seconds=1)
        with pytest.raises(ConnectionPolicyError, match="worker_lease_lost"):
            await context.wait(asyncio.sleep(0))

        context = TransportContext.create(None, None, None, timeout_seconds=.01)
        with pytest.raises(ConnectionPolicyError, match="transport_timeout"):
            await context.wait(asyncio.sleep(1))

        context = TransportContext.create(None, None, None, timeout_seconds=1)
        task = asyncio.create_task(context.wait(asyncio.sleep(10)))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_bounded_reader_rejects_bad_oid_non_increasing_rows_and_requests():
    root = numeric_oid("1.3.6.1.2.1.2")

    async def scenario():
        context = TransportContext.create(None, None, None, timeout_seconds=5)
        repeated = FakeSession(lambda operation, oids, maximum, calls: [(oids[0], calls)])
        reader = BoundedSNMPReader(context, repeated, [root])
        with pytest.raises(ConnectionPolicyError, match="snmp_non_increasing_oid"):
            await reader.walk(root)
        with pytest.raises(ConnectionPolicyError, match="snmp_malformed_oid"):
            numeric_oid("1.3.vendor.1")
        with pytest.raises(ConnectionPolicyError, match="snmp_oid_not_allowed"):
            await reader.get("1.3.6.1.4.1.9")
        next_reader = BoundedSNMPReader(
            context, FakeSession(lambda operation, oids, maximum, calls: [(root + (1,), 1)]), [root]
        )
        assert await next_reader.get_next(root) == [(root + (1,), 1)]

        def rows(operation, oids, maximum, calls):
            start = (calls - 1) * 40 + 1
            return [(root + (index,), index) for index in range(start, start + 40)]
        reader = BoundedSNMPReader(
            context, FakeSession(rows), [root],
            SNMPLimits(requests=128, rows=4096, varbinds=10000, bytes=2_000_000),
        )
        with pytest.raises(ConnectionPolicyError, match="snmp_output_limit"):
            await reader.walk(root)

        def single(operation, oids, maximum, calls):
            return [(root + (calls,), calls)]
        reader = BoundedSNMPReader(
            context, FakeSession(single), [root],
            SNMPLimits(requests=128, rows=1000, varbinds=1000, bytes=2_000_000,
                       bulk_repetitions=1),
        )
        with pytest.raises(ConnectionPolicyError, match="snmp_request_limit"):
            await reader.walk(root)

    asyncio.run(scenario())


def test_standard_mappers_preserve_identity_and_unknown_evidence(system):
    client, store, _, _ = system
    login(client)
    device = store.get_device(prepare(client)["id"])
    identity = parse_system_mib([
        (numeric_oid(SYS_OBJECT_ID), "1.3.6.1.4.1.9.1.1"),
        (numeric_oid(SYS_DESCR), "Cisco IOS\x1b[31m test"),
        (numeric_oid(SYS_NAME), "switch-1"),
        (numeric_oid(SYS_UPTIME), 12345),
    ])
    assert identity.sys_object_id == "1.3.6.1.4.1.9.1.1"
    assert "\x1b" not in identity.sys_descr and identity.sys_uptime_ticks == 12345

    columns = {
        "name": {7: "eth1"}, "in_octets": {7: 2**40}, "out_octets": {7: 2**40 + 1},
        "discontinuity": {7: 0}, "admin_up": {7: 1}, "oper_up": {7: 1},
    }
    first, _ = parse_if_mib(device, columns, 200)
    reboot, _ = parse_if_mib(device, columns, 100, first)
    assert reboot["snmp_epoch"] != first["snmp_epoch"]
    with pytest.raises(ConnectionPolicyError, match="snmp_ambiguous_interface"):
        parse_if_mib(device, {**columns, "name": {7: "eth1", 8: "eth1"}}, 300)
    duplicate_index = device.model_copy(update={"interfaces": [
        interface.model_copy(update={"if_index": 7}) if interface.id in {"if1", "if2"} else interface
        for interface in device.interfaces
    ]})
    with pytest.raises(ConnectionPolicyError, match="snmp_ambiguous_ifindex"):
        parse_if_mib(duplicate_index, columns, 300)

    bridge, complete = parse_bridge_mib({7: "if1"}, {1: 7}, {10: 10}, {1: 10})
    assert complete and bridge["interfaces"] == [{"interface_id": "if1", "pvid": 10, "source": "snmp"}]
    with pytest.raises(ConnectionPolicyError, match="snmp_bridge_port_conflict"):
        parse_bridge_mib({7: "if1", 8: "if2"}, [(1, 7), (1, 8)], {}, {})

    neighbors, complete = parse_lldp_mib(
        device, {(1,): "eth1"}, {(0, 1, 1): "aa:bb:cc:dd:ee:ff"},
        {(0, 1, 1): "Ethernet1"}, {(0, 1, 1): "upstream"},
    )
    assert complete and neighbors[0]["relation"] == "l2"
    assert neighbors[0]["remote_device_id"] is None and neighbors[0]["remote_interface_id"] is None

    entity, complete = parse_entity_mib(
        {"class": {1: 99, 2: 10}, "name": {1: "Mystery", 2: "Port"},
         "description": {}, "serial": {}, "contained_in": {}, "parent_position": {}},
        {"type": {1: 8}, "scale": {1: 9}, "precision": {1: -1},
         "value": {1: 42}, "status": {1: 1}},
    )
    assert complete
    assert entity["entities"][0]["entity_class"] == "unknown"
    assert entity["entities"][1]["connector"] == "unknown"
    assert entity["sensors"][0]["sensor_type"] == "celsius"
    assert entity["sensors"][0]["value"] == 420


def test_counter32_wrap_and_counter64_reset_never_emit_a_rate():
    previous = Telemetry(
        observed_at=now() - timedelta(seconds=30), source="snmp",
        interfaces=[{"interface_id": "if1", "in_octets": 2**32 - 5,
                     "out_octets": 2**32 - 5, "counter_bits": 32,
                     "discontinuity": "epoch", "source": "snmp"}],
    ).model_dump(mode="json")
    wrapped = Telemetry(
        observed_at=now(), source="snmp",
        interfaces=[{"interface_id": "if1", "in_octets": 3, "out_octets": 4,
                     "counter_bits": 32, "discontinuity": "epoch", "source": "snmp"}],
    )
    assert normalize(wrapped, previous)["interfaces"][0]["rate_reason"] == "counter_reset_or_wrap"
    previous["interfaces"][0].update(in_octets=2**40, out_octets=2**40, counter_bits=64)
    reset = wrapped.model_copy(update={"interfaces": [wrapped.interfaces[0].model_copy(update={"counter_bits": 64})]})
    assert normalize(reset, previous)["interfaces"][0]["rate_reason"] == "counter_reset_or_wrap"


def test_partial_snmp_fields_merge_without_deleting_cli_last_good(system):
    client, store, _, _ = system
    login(client)
    device = store.get_device(prepare(client)["id"])
    first_meta = metadata("network", "cisco_ios", source="ssh", fields={"fdb": "ok", "lldp": "ok"})
    first = ReadResult(device, payloads={"network": {
        "interfaces": [{"interface_id": "if1", "addresses": ["192.0.2.1/24"]}],
        "endpoints": {"status": "ok", "entries": [{"id": "endpoint", "interface_id": "if1",
            "mac": "02:00:00:00:00:01", "addresses": [], "discovery": "fdb", "state": "unknown",
            "evidence": "CLI FDB"}], "truncated": False},
        "neighbors": [{"id": "peer", "interface_id": "if1", "label": "peer", "relation": "l2",
                       "evidence": "CLI LLDP"}],
    }}, metadata={"network": first_meta})
    persist(store, device, first)
    second_meta = metadata("network", "snmp_bridge_lldp", source="snmp", quality="partial",
                           complete=False, reason="snmp_standard_mib_partial",
                           fields={"vlan": "ok", "lldp": "unsupported"})
    second = ReadResult(device, payloads={"network": {
        "interfaces": [{"interface_id": "if1", "pvid": 20, "source": "snmp"}],
        "bridge_ports": [{"bridge_port": 1, "if_index": 7, "interface_id": "if1", "pvid": 20,
                          "source": "snmp"}], "vlans": [{"vlan": 20, "fid": 20, "source": "snmp"}],
        "neighbors": [],
    }}, metadata={"network": second_meta})
    persist(store, device, second)
    with store.engine.connect() as conn:
        row = conn.execute(sa.select(store.collection_groups).where(
            store.collection_groups.c.device_id == device.id,
            store.collection_groups.c.group_name == "network",
        )).mappings().one()
    assert row["payload"]["endpoints"]["entries"][0]["evidence"] == "CLI FDB"
    assert row["payload"]["neighbors"][0]["evidence"] == "CLI LLDP"
    assert row["payload"]["interfaces"][0]["pvid"] == 20
    assert row["metadata"]["field_sources"] == {"fdb": "ssh", "lldp": "ssh", "vlan": "snmp"}
    assert row["metadata"]["observed_at"].replace("Z", "+00:00") == first_meta.observed_at.isoformat()


def test_channel_pause_is_independent_and_recovers(system):
    client, store, _, _ = system
    login(client)
    device = store.get_device(prepare(client, collector="cisco_ios")["id"]).model_copy(update={"snmp_configured": True})
    scheduler.ensure_policy(store, device)
    scheduler.completed(store, device, ["fast"], 1, error="authentication_failed",
                        channel_outcomes={"ssh": "authentication_failed", "snmp": None})
    with store.engine.connect() as conn:
        row = conn.execute(sa.select(store.polling).where(store.polling.c.device_id == device.id)).mappings().one()
    assert row["paused_reason"] is None
    assert row["state"]["channels"]["ssh"]["reason"] == "authentication_failed"
    assert "snmp" not in row["state"]["channels"]
    assert not scheduler.channel_ready(row["state"], "ssh")
    assert scheduler.channel_ready(row["state"], "snmp")

    scheduler.completed(store, device, ["fast"], 1, error="snmp_authentication_failed",
                        channel_outcomes={"ssh": None, "snmp": "snmp_authentication_failed"})
    with store.engine.connect() as conn:
        row = conn.execute(sa.select(store.polling).where(
            store.polling.c.device_id == device.id)).mappings().one()
    assert "ssh" not in row["state"]["channels"]
    assert row["state"]["channels"]["snmp"]["reason"] == "snmp_authentication_failed"
    assert row["paused_reason"] is None
    assert scheduler.channel_ready(row["state"], "ssh")

    scheduler.completed(store, device, ["fast"], 1, channel_outcomes={"snmp": None})
    with store.engine.connect() as conn:
        state = conn.execute(sa.select(store.polling.c.state).where(
            store.polling.c.device_id == device.id)).scalar_one()
    assert not state["channels"]

    with store.engine.begin() as conn:
        conn.execute(store.polling.update().where(store.polling.c.device_id == device.id).values(
            paused_reason="authentication_failed", due_at=now(), state={}
        ))
    scheduler.schedule(store)
    with store.engine.connect() as conn:
        row = conn.execute(sa.select(store.polling).where(
            store.polling.c.device_id == device.id)).mappings().one()
    assert row["paused_reason"] is None
    assert row["state"]["channels"]["ssh"]["reason"] == "authentication_failed"

