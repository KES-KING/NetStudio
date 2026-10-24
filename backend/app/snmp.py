"""Standard-MIB SNMPv3 authPriv collection orchestration."""
from __future__ import annotations

import sqlalchemy as sa

from .collection import ReadResult, metadata
from .contracts import Health
from .driver_catalog import GROUPS
from .snmp_mappers import (
    BRIDGE_COLUMNS, ENTITY_COLUMNS, IF_COLUMNS, LLDP_COLUMNS, QBRIDGE_COLUMNS,
    QBRIDGE_FDB_COLUMNS,
    SENSOR_COLUMNS, SYSTEM_SCALARS, SYS_UPTIME, parse_bridge_mib,
    parse_entity_mib, parse_if_mib, parse_lldp_mib, parse_system_mib,
)
from .snmp_mappers.common import column_map
from .snmp_transport import BoundedSNMPReader, PysnmpV3Session, SNMPLimits
from .ssh import ConnectionPolicyError
from .transport import TransportContext


# Backwards-compatible imports used by earlier tests and integrations.
COLUMNS = IF_COLUMNS
ALL_ROOTS = tuple({
    *SYSTEM_SCALARS, *IF_COLUMNS.values(), *BRIDGE_COLUMNS.values(),
    *QBRIDGE_COLUMNS.values(), *QBRIDGE_FDB_COLUMNS.values(),
    *LLDP_COLUMNS.values(), *ENTITY_COLUMNS.values(),
    *SENSOR_COLUMNS.values(),
})


def _one_index(bindings, prefix):
    result = {}
    for suffix, value in column_map(bindings, prefix).items():
        if len(suffix) != 1:
            raise ConnectionPolicyError("snmp_malformed_oid")
        result[suffix[0]] = value
    return result


async def _columns(reader, definitions, *, tuple_indices=False):
    values = {}
    for name, prefix in definitions.items():
        bindings = await reader.walk(prefix)
        raw = column_map(bindings, prefix)
        values[name] = raw if tuple_indices else _one_index(bindings, prefix)
    return values


def _quality(complete, has_payload):
    return "ok" if complete else "partial" if has_payload else "unsupported"


async def collect_snmp(store, vault, device, authorize=lambda: None, groups=("fast",), *,
                       transport_context: TransportContext | None = None,
                       limits: SNMPLimits = SNMPLimits()):
    requested = set(groups) & set(GROUPS)
    if not requested:
        return ReadResult(device)
    context = transport_context or TransportContext.create(
        store, vault, device, authorize, timeout_seconds=25
    )
    context.checkpoint()
    credentials = vault.get_protocol(device.id, "snmp")
    session = None
    try:
        session = await PysnmpV3Session(context, credentials).open()
        reader = BoundedSNMPReader(context, session, ALL_ROOTS, limits)
        identity = parse_system_mib(await reader.get(*SYSTEM_SCALARS))
        result = ReadResult(device)
        if identity.sys_descr:
            # A recognized standard sysDescr is corroborating profile evidence;
            # unknown/free-form descriptions never become an automatic guess.
            from .drivers import identify_platform
            try:
                platform = identify_platform({"sysDescr": identity.sys_descr})
            except ConnectionPolicyError:
                platform = None
            if platform:
                result.observed_profile_id = platform.profile_id
                result.identity_evidence = {
                    "vendor": platform.vendor, "os_family": platform.os_family,
                    "sys_object_id": identity.sys_object_id,
                    "management_mode": device.management_mode,
                }
        with store.engine.connect() as conn:
            previous_fast = conn.execute(sa.select(store.collection_groups.c.payload).where(
                store.collection_groups.c.device_id == device.id,
                store.collection_groups.c.group_name == "fast",
            )).scalar_one_or_none()

        # Network tables also need the IF-MIB identity bridge, but need not
        # collect every high-frequency counter when fast was not requested.
        interface_payload, interface_complete = ({}, False)
        if requested & {"fast", "network"}:
            definitions = IF_COLUMNS if "fast" in requested else {"name": IF_COLUMNS["name"]}
            interface_columns = await _columns(reader, definitions)
            interface_payload, interface_complete = parse_if_mib(
                device, interface_columns, identity.sys_uptime_ticks, previous_fast
            )
        if "fast" in requested:
            result.payloads["fast"] = interface_payload
            samples = interface_payload["interfaces"]
            field_names = (
                "admin_up", "oper_up", "capacity_bps", "in_octets", "out_octets",
                "errors", "discards", "tx_errors", "tx_discards",
            )
            fields = {name: (
                "ok" if all(sample.get(name) is not None for sample in samples)
                else "partial" if any(sample.get(name) is not None for sample in samples)
                else "unsupported"
            ) for name in field_names}
            fast_complete = interface_complete and all(status == "ok" for status in fields.values())
            result.metadata["fast"] = metadata(
                "fast", "snmp_if_ifx", source="snmp",
                quality="ok" if fast_complete else "partial",
                complete=fast_complete,
                reason=None if fast_complete else "snmp_if_mib_partial",
                fields=fields,
            )

        entity_payload, entity_complete = ({"entities": [], "sensors": []}, False)
        if requested & {"inventory", "health"}:
            entity_columns = await _columns(reader, ENTITY_COLUMNS)
            sensor_columns = await _columns(reader, SENSOR_COLUMNS)
            entity_payload, entity_complete = parse_entity_mib(entity_columns, sensor_columns)

        if "network" in requested:
            bridge_columns = await _columns(reader, {
                **BRIDGE_COLUMNS, "pvid": QBRIDGE_COLUMNS["pvid"],
            })
            # TimeFilter index 0 requests the current table. Walking the
            # narrower .0 subtree also stops before the agent's next
            # time-filter sentinel instead of traversing conceptual snapshots.
            vlan_fid_prefix = QBRIDGE_COLUMNS["vlan_fid"]
            vlan_columns = {"vlan_fid": column_map(
                await reader.walk(vlan_fid_prefix + ".0"), vlan_fid_prefix,
            )}
            fdb_columns = await _columns(reader, QBRIDGE_FDB_COLUMNS, tuple_indices=True)
            bridge, bridge_complete = parse_bridge_mib(
                interface_payload.get("if_index_map", {}),
                bridge_columns["port_ifindex"], vlan_columns["vlan_fid"],
                bridge_columns["pvid"],
                fdb_columns["fdb_port"], fdb_columns["fdb_status"],
            )
            lldp_columns = await _columns(reader, LLDP_COLUMNS, tuple_indices=True)
            neighbors, lldp_complete = parse_lldp_mib(
                device, lldp_columns["local_port"], lldp_columns["remote_chassis"],
                lldp_columns["remote_port"], lldp_columns["remote_name"],
            )
            payload = {
                **bridge, "neighbors": neighbors,
            }
            fdb_complete = payload["endpoints"]["status"] == "ok"
            result.payloads["network"] = payload
            result.metadata["network"] = metadata(
                "network", "snmp_bridge_lldp", source="snmp",
                quality=_quality(False, bridge_complete or fdb_complete or lldp_complete),
                # Standard VLAN/LLDP is not the entire network group (for
                # example FDB/ARP/address data). It must merge, never replace.
                complete=False,
                reason="snmp_standard_mib_partial",
                fields={
                    "vlan": "ok" if bridge_complete else "unsupported",
                    "fdb": "ok" if fdb_complete else (
                        "partial" if payload["endpoints"]["entries"] else "unsupported"
                    ),
                    "lldp": "ok" if lldp_complete else "unsupported",
                },
            )

        if "inventory" in requested:
            payload = {
                "system_identity": identity.model_dump(mode="json"),
                "entities": entity_payload["entities"],
            }
            result.payloads["inventory"] = payload
            result.metadata["inventory"] = metadata(
                "inventory", "snmp_system_entity", source="snmp",
                quality="partial", complete=False,
                reason="snmp_standard_mib_partial" if entity_complete else "snmp_entity_partial",
                fields={"system_identity": "ok", "modules": "ok" if entity_complete else "partial"},
            )

        if "health" in requested:
            temperatures = [value["value"] for value in entity_payload["sensors"]
                            if value["sensor_type"] == "celsius" and value["status"] == "ok"
                            and value["value"] is not None and -100 <= value["value"] <= 250]
            health = Health(
                uptime_seconds=identity.sys_uptime_ticks // 100,
                temperature_c=temperatures[0] if temperatures else None,
            )
            result.payloads["health"] = {
                "health": health.model_dump(mode="json"),
                "sensors": entity_payload["sensors"],
                "interfaces": [],
            }
            sensor_ok = bool(entity_payload["sensors"]) and entity_complete
            result.metadata["health"] = metadata(
                "health", "snmp_system_entity_sensor", source="snmp",
                quality="partial", complete=False,
                reason="snmp_standard_mib_partial" if sensor_ok else "snmp_entity_sensor_partial",
                fields={"uptime_seconds": "ok", "temperature_c": "ok" if temperatures else "unsupported"},
            )

        result.reboot_detected = bool(
            previous_fast and previous_fast.get("snmp_epoch")
            and previous_fast["snmp_epoch"] != interface_payload.get("snmp_epoch")
        )
        context.checkpoint()
        return result
    finally:
        if session is not None:
            session.close()
        else:
            credentials.clear()


class SNMPTransportAdapter:
    kind = "snmp"

    async def collect(self, context: TransportContext, groups: set[str]) -> ReadResult:
        context = context.bounded(25)
        return await collect_snmp(
            context.store, context.vault, context.device, context.checkpoint,
            groups, transport_context=context,
        )
