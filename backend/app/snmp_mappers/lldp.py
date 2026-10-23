"""LLDP-MIB mapper; evidence never becomes an inferred physical cable."""
from __future__ import annotations

from hashlib import sha256

from .. import cisco, huawei
from ..contracts import Neighbor
from .common import text_value


LLDP_COLUMNS = {
    "local_port": "1.0.8802.1.1.2.1.3.7.1.3",
    "remote_chassis": "1.0.8802.1.1.2.1.4.1.1.5",
    "remote_port": "1.0.8802.1.1.2.1.4.1.1.7",
    "remote_name": "1.0.8802.1.1.2.1.4.1.1.9",
}


def parse_lldp_mib(device, local_ports, remote_chassis, remote_ports, remote_names):
    canonical = huawei.canonical if (device.resolved_collector or device.collector) == "huawei_vrp" else cisco.canonical
    interfaces = {canonical(interface.name): interface.id for interface in device.interfaces}
    neighbors, partial = [], False
    for key in sorted(set(remote_chassis) | set(remote_ports)):
        if len(key) < 3 or key not in remote_chassis or key not in remote_ports:
            partial = True
            continue
        local_number = key[-2]
        local_name = text_value(local_ports.get((local_number,), ""), maximum=160)
        interface_id = interfaces.get(canonical(local_name))
        chassis = text_value(remote_chassis[key], maximum=160)
        port = text_value(remote_ports[key], maximum=160)
        if not interface_id or not chassis or not port:
            partial = True
            continue
        label = text_value(remote_names.get(key, chassis), maximum=160) or chassis
        evidence = f"LLDP-MIB chassis={chassis}; port={port}"[:300]
        identifier = sha256(f"{interface_id}|{chassis}|{port}".encode()).hexdigest()[:32]
        neighbors.append(Neighbor(id=identifier, interface_id=interface_id, label=label,
                                  relation="l2", evidence=evidence))
    return [neighbor.model_dump(mode="json") for neighbor in neighbors], bool(neighbors) and not partial

