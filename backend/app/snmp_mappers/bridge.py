"""BRIDGE-MIB/Q-BRIDGE-MIB VLAN and bridge-port mapper."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal

from pydantic import Field

from ..contracts import StrictModel
from ..ssh import ConnectionPolicyError


BRIDGE_COLUMNS = {"port_ifindex": "1.3.6.1.2.1.17.1.4.1.2"}
QBRIDGE_COLUMNS = {
    "vlan_fid": "1.3.6.1.2.1.17.7.1.4.2.1.3",
    "pvid": "1.3.6.1.2.1.17.7.1.4.5.1.1",
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


def parse_bridge_mib(if_index_map, port_ifindex, vlan_fid, pvid):
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
    vlans = []
    for vlan, fid in sorted(_pairs(vlan_fid)):
        if not 1 <= vlan <= 4094:
            raise ConnectionPolicyError("snmp_vlan_invalid")
        vlans.append(VlanFid(vlan=vlan, fid=fid))
    complete = bool(ports and vlans) and not partial
    return {
        "bridge_ports": [value.model_dump(mode="json") for value in ports],
        "vlans": [value.model_dump(mode="json") for value in vlans],
        "interfaces": [{"interface_id": value.interface_id, "pvid": value.pvid,
                        "source": "snmp"} for value in ports if value.pvid is not None],
    }, complete

