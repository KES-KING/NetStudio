"""IF-MIB/IF-X-MIB mapper with stable-name and counter-epoch rules."""
from __future__ import annotations

from uuid import uuid4

from .. import cisco, huawei
from ..contracts import InterfaceSample
from ..ssh import ConnectionPolicyError
from .common import int_value, text_value


IF = "1.3.6.1.2.1.2.2.1"
IFX = "1.3.6.1.2.1.31.1.1.1"
IF_COLUMNS = {
    "name": IFX + ".1", "admin_up": IF + ".7", "oper_up": IF + ".8",
    "capacity": IFX + ".15", "in_octets": IFX + ".6", "out_octets": IFX + ".10",
    "in32": IF + ".10", "out32": IF + ".16", "errors": IF + ".14",
    "discards": IF + ".13", "tx_errors": IF + ".20", "tx_discards": IF + ".19",
    "discontinuity": IFX + ".19",
}


def parse_if_mib(device, columns, uptime, previous=None):
    previous = previous or {}
    uptime = int_value(uptime)
    epoch = previous.get("snmp_epoch") or str(uuid4())
    if uptime < previous.get("snmp_uptime_ticks", 0):
        epoch = str(uuid4())
    canonical = huawei.canonical if (device.resolved_collector or device.collector) == "huawei_vrp" else cisco.canonical
    names: dict[str, list] = {}
    indices: dict[int, object] = {}
    for interface in device.interfaces:
        names.setdefault(canonical(interface.name), []).append(interface)
        if interface.if_index is not None:
            if interface.if_index in indices:
                raise ConnectionPolicyError("snmp_ambiguous_ifindex")
            indices[interface.if_index] = interface
    seen, samples, index_map = set(), [], {}
    for index, raw_name in columns.get("name", {}).items():
        try:
            index = int(index)
        except (TypeError, ValueError, OverflowError) as error:
            raise ConnectionPolicyError("snmp_malformed_oid") from error
        matches = names.get(canonical(text_value(raw_name, maximum=160)), [])
        if len(matches) > 1:
            raise ConnectionPolicyError("snmp_ambiguous_interface")
        interface = matches[0] if matches else None
        indexed = indices.get(index)
        if interface and indexed and indexed.id != interface.id:
            raise ConnectionPolicyError("snmp_ambiguous_ifindex")
        interface = interface or indexed
        if not interface:
            continue  # ifIndex alone is never a persistent identity.
        if interface.id in seen:
            raise ConnectionPolicyError("snmp_ambiguous_interface")
        seen.add(interface.id)
        index_map[index] = interface.id

        def value(key):
            result = columns.get(key, {}).get(index)
            return int_value(result) if result is not None else None

        incoming, outgoing = value("in_octets"), value("out_octets")
        bits = 64
        if incoming is None or outgoing is None:
            incoming, outgoing, bits = value("in32"), value("out32"), 32
        disc = value("discontinuity")
        capacity = value("capacity")
        samples.append(InterfaceSample(
            interface_id=interface.id,
            admin_up={1: True, 2: False, 3: False}.get(value("admin_up")),
            oper_up={1: True, 2: False, 3: False, 4: False, 5: False, 6: False, 7: False}.get(value("oper_up")),
            capacity_bps=capacity * 1_000_000 if capacity else None,
            in_octets=incoming, out_octets=outgoing, counter_bits=bits,
            source="snmp", vrf_known=False,
            discontinuity=f"{epoch}:{index}:{disc}", counter_epoch_known=disc is not None,
            errors=value("errors"), discards=value("discards"),
            tx_errors=value("tx_errors"), tx_discards=value("tx_discards"),
        ))
    if not samples:
        raise ConnectionPolicyError("snmp_interface_identity_missing")
    complete = {i.id for i in device.interfaces if i.kind == "ethernet"}.issubset(seen)
    return {
        "interfaces": [sample.model_dump(mode="json") for sample in samples],
        "if_index_map": {str(key): value for key, value in index_map.items()},
        "snmp_epoch": epoch,
        "snmp_uptime_ticks": uptime,
    }, complete

