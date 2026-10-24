"""BRIDGE-MIB/Q-BRIDGE-MIB VLAN and bridge-port mapper."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from hashlib import sha256
from typing import Literal

from pydantic import Field

from ..contracts import EndpointCollection, EndpointObservation, StrictModel
from ..ssh import ConnectionPolicyError


BRIDGE_COLUMNS = {"port_ifindex": "1.3.6.1.2.1.17.1.4.1.2"}
QBRIDGE_COLUMNS = {
    "vlan_fid": "1.3.6.1.2.1.17.7.1.4.2.1.3",
    "pvid": "1.3.6.1.2.1.17.7.1.4.5.1.1",
}
QBRIDGE_FDB_COLUMNS = {
    "fdb_port": "1.3.6.1.2.1.17.7.1.2.2.1.2",
    "fdb_status": "1.3.6.1.2.1.17.7.1.2.2.1.3",
}


class BridgePort(StrictModel):
    bridge_port: int = Field(ge=1)
    if_index: int = Field(ge=1)
    interface_id: str
    pvid: int | None = Field(default=None, ge=1, le=4094)
    source: Literal["snmp"] = "snmp"


class VlanFid(StrictModel):
    vlan: int = Field(ge=1, le=4094)
    fid: int = Field(ge=0)
    source: Literal["snmp"] = "snmp"


def _pairs(values: Mapping | Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    return [(int(key), int(value)) for key, value in (values.items() if isinstance(values, Mapping) else values)]


def _vlan_fid_pairs(values) -> list[tuple[int, int]]:
    """Normalize dot1qVlanCurrentFdbId's (timeMark, VLAN) table index."""
    rows = values.items() if isinstance(values, Mapping) else values
    result, time_marks = {}, set()
    for raw_key, raw_fid in rows:
        if isinstance(raw_key, (tuple, list)):
            key = tuple(int(part) for part in raw_key)
            if len(key) == 2:
                time_marks.add(key[0])
                vlan = key[1]
            elif len(key) == 1:  # Compatibility with older synthetic callers.
                vlan = key[0]
            else:
                raise ConnectionPolicyError("snmp_malformed_oid")
        else:
            vlan = int(raw_key)
        fid = int(raw_fid)
        if vlan in result and result[vlan] != fid:
            raise ConnectionPolicyError("snmp_vlan_fid_conflict")
        result[vlan] = fid
    if len(time_marks) > 1:
        # Mixing two Q-BRIDGE snapshots can associate an FDB row with the wrong
        # VLAN. Retry the bounded poll rather than choosing a time mark.
        raise ConnectionPolicyError("snmp_vlan_snapshot_conflict")
    return sorted(result.items())


def _fdb_entries(vlans, ports, interface_ids, fdb_port, fdb_status):
    """Map Q-BRIDGE FID+MAC indices without assuming FID equals VLAN."""
    vlan_by_fid = {}
    for vlan, fid in vlans:
        if fid in vlan_by_fid and vlan_by_fid[fid] != vlan:
            raise ConnectionPolicyError("snmp_fid_vlan_conflict")
        vlan_by_fid[fid] = vlan
    entries, partial = [], False
    statuses = {
        tuple(int(part) for part in key): int(value)
        for key, value in fdb_status.items()
    }
    for raw_key, raw_port in sorted(fdb_port.items()):
        key = tuple(int(part) for part in raw_key)
        if len(key) != 7 or any(not 0 <= octet <= 255 for octet in key[1:]):
            raise ConnectionPolicyError("snmp_malformed_oid")
        status = statuses.get(key)
        if status in {1, 2, 4}:  # other/invalid/self are not learned endpoints.
            continue
        if status not in {3, 5}:
            partial = True
            continue
        bridge_port = int(raw_port)
        if_index = ports.get(bridge_port)
        interface_id = interface_ids.get(if_index)
        vlan = vlan_by_fid.get(key[0])
        if not interface_id or vlan is None:
            partial = True
            continue
        mac = ":".join(f"{octet:02x}" for octet in key[1:])
        try:
            entry = EndpointObservation(
                id=sha256(f"snmp|{interface_id}|{vlan}|{mac}".encode()).hexdigest()[:32],
                interface_id=interface_id, mac=mac, vlan=vlan,
                discovery="fdb", state="static" if status == 5 else "unknown",
                evidence=f"Q-BRIDGE-MIB FID {key[0]} mapped to VLAN {vlan}",
            )
        except ValueError as error:
            raise ConnectionPolicyError("snmp_fdb_invalid") from error
        entries.append(entry)
        if len(entries) > 2048:
            raise ConnectionPolicyError("snmp_output_limit")
    complete = bool(fdb_port) and not partial
    return EndpointCollection(
        status="ok" if complete else "partial" if entries else "unsupported",
        entries=entries, total_count=len(entries), source="snmp",
    ).model_dump(mode="json")


def parse_bridge_mib(
    if_index_map, port_ifindex, vlan_fid, pvid, fdb_port=None, fdb_status=None,
):
    mapping, used_ifindices = {}, set()
    for bridge_port, if_index in _pairs(port_ifindex):
        if bridge_port in mapping and mapping[bridge_port] != if_index:
            raise ConnectionPolicyError("snmp_bridge_port_conflict")
        if if_index in used_ifindices:
            raise ConnectionPolicyError("snmp_bridge_port_conflict")
        mapping[bridge_port] = if_index
        used_ifindices.add(if_index)
    pvids = dict(_pairs(pvid))
    interfaces = {int(key): value for key, value in if_index_map.items()}
    ports, partial = [], False
    for bridge_port, if_index in sorted(mapping.items()):
        interface_id = interfaces.get(if_index)
        if not interface_id:
            partial = True
            continue
        vlan = pvids.get(bridge_port)
        if vlan is not None and not 1 <= vlan <= 4094:
            raise ConnectionPolicyError("snmp_vlan_invalid")
        ports.append(BridgePort(bridge_port=bridge_port, if_index=if_index,
                                interface_id=interface_id, pvid=vlan))
    vlan_pairs = _vlan_fid_pairs(vlan_fid)
    vlans = []
    for vlan, fid in vlan_pairs:
        if not 1 <= vlan <= 4094:
            raise ConnectionPolicyError("snmp_vlan_invalid")
        vlans.append(VlanFid(vlan=vlan, fid=fid))
    endpoints = _fdb_entries(
        vlan_pairs, mapping, interfaces, fdb_port or {}, fdb_status or {},
    )
    complete = bool(ports and vlans) and not partial
    return {
        "bridge_ports": [value.model_dump(mode="json") for value in ports],
        "vlans": [value.model_dump(mode="json") for value in vlans],
        "interfaces": [{"interface_id": value.interface_id, "pvid": value.pvid,
                        "source": "snmp"} for value in ports if value.pvid is not None],
        "endpoints": endpoints,
    }, complete

