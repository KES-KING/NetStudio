"""Bounded P1 enterprise CLI parsers.

The six profiles share normalized output models, not platform detection or
command grammars. JSON CLI is used only for AOS-CX/EOS; AOS-Switch, Comware 7
and RouterOS remain in their own text parsers. Raw output is never persisted.
"""
from __future__ import annotations

from hashlib import sha256
from ipaddress import ip_address, ip_interface
import json
import re

from .collection import ReadResult, metadata
from .contracts import EndpointCollection, EndpointObservation, Health, Neighbor, Telemetry
from .database import now
from .driver_catalog import DRIVERS
from .structured_parsers import merge


P1_DRIVERS = {
    "aruba_aoscx", "hp_procurve", "arista_eos", "hp_comware",
    "h3c_comware7", "mikrotik_routeros",
}
JSON_DRIVERS = {"aruba_aoscx", "arista_eos"}
IDENTITY_COMMANDS = {
    "aruba_aoscx": "show version",
    "hp_procurve": "show version",
    "arista_eos": "show version | json",
    "hp_comware": "display version",
    "h3c_comware7": "display version",
    "mikrotik_routeros": "/system resource print without-paging",
}
INTERFACE_COMMANDS = {
    "aruba_aoscx": "show interface | json",
    "hp_procurve": "show interfaces",
    "arista_eos": "show interfaces | json",
    "hp_comware": "display interface",
    "h3c_comware7": "display interface",
    "mikrotik_routeros": "/interface print stats-detail without-paging",
}


def _json(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("invalid_json")
    value = json.loads(raw[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("invalid_json_object")
    return value


def _int(value, *, minimum: int = 0, maximum: int = 2**64 - 1) -> int | None:
    if value in {None, "", "--", "unknown"}:
        return None
    if isinstance(value, bool):
        raise ValueError("invalid_integer")
    result = int(str(value).replace(",", "").strip())
    if not minimum <= result <= maximum:
        raise ValueError("integer_out_of_range")
    return result


def _float(value, *, minimum: float = 0, maximum: float = 100) -> float | None:
    if value in {None, "", "--", "unknown"}:
        return None
    result = float(str(value).replace("%", "").strip())
    if not minimum <= result <= maximum:
        raise ValueError("number_out_of_range")
    return result


def _state(value) -> bool | None:
    token = str(value or "").strip().lower()
    if token in {"up", "enabled", "true", "yes", "running", "connected"}:
        return True
    if token in {"down", "disabled", "false", "no", "notconnect", "inactive"}:
        return False
    return None


def _speed(value, unit: str = "bps") -> float | None:
    if value in {None, "", "--", "unknown"}:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*([kmgt]?)", str(value), re.I)
    if not match:
        return None
    scale = {"": 1, "k": 1_000, "m": 1_000_000, "g": 1_000_000_000, "t": 1_000_000_000_000}
    multiplier = scale[match.group(2).lower()]
    if not match.group(2) and unit.lower() == "mbps":
        multiplier = 1_000_000
    result = float(match.group(1)) * multiplier
    return result if result > 0 else None


def _kind(name: str) -> str:
    value = name.lower()
    if value.startswith(("lag", "trk", "bridge", "bond", "port-channel", "eth-trunk")):
        return "port_channel"
    if value.startswith(("vlan", "vlan-interface")):
        return "svi"
    if value.startswith(("lo", "loopback")):
        return "loopback"
    if "." in value:
        return "subinterface"
    return "ethernet"


def _physical(name: str) -> bool:
    value = name.lower()
    return _kind(name) == "ethernet" and bool(
        re.match(r"^(?:\d+(?:/\d+)+|ether\d+|(?:hundred|forty|twenty-five|ten|x)?gigabitethernet|ethernet|ge|xge)", value)
        or value.isdigit()
    )


def _kv(line: str) -> dict[str, str]:
    return {
        match.group(1).lower(): (match.group(2) if match.group(2) is not None else match.group(3))
        for match in re.finditer(r"([a-z][a-z0-9-]*)=(?:\"([^\"]*)\"|(\S+))", line, re.I)
    }


def _routeros_records(raw: str) -> list[dict[str, str]]:
    records = []
    current = ""
    for line in raw.splitlines():
        if re.match(r"^\s*\d+\s", line):
            if current:
                records.append(_kv(current))
            current = line
        elif current and line.startswith(" "):
            current += " " + line.strip()
    if current:
        records.append(_kv(current))
    return [record for record in records if record]


def _json_interfaces(driver: str, raw: str) -> list[dict]:
    root = _json(raw)
    values = root.get("interfaces")
    if not isinstance(values, dict):
        raise ValueError("interfaces_missing")
    result = []
    for name, row in values.items():
        if not isinstance(row, dict) or not isinstance(name, str):
            raise ValueError("invalid_interface")
        counters = row.get("statistics") or row.get("interfaceCounters") or {}
        if not isinstance(counters, dict):
            raise ValueError("invalid_interface_counters")
        if driver == "aruba_aoscx":
            admin, oper = row.get("admin_state"), row.get("link_state")
            speed_value = row.get("speed_bps", row.get("speed"))
            speed_unit = "bps" if row.get("speed_bps") is not None else row.get("speed_unit", "mbps")
            duplex = str(row.get("duplex", "unknown")).lower()
            keys = ("rx_bytes", "tx_bytes", "rx_errors", "rx_discards", "tx_errors", "tx_discards")
        else:
            admin, oper = row.get("interfaceStatus"), row.get("lineProtocolStatus")
            speed_value, speed_unit = row.get("bandwidth"), "bps"
            duplex = {"duplexFull": "full", "duplexHalf": "half"}.get(row.get("duplex"), str(row.get("duplex", "unknown")).lower())
            keys = ("inOctets", "outOctets", "inputErrorsDetail", "inDiscards", "outputErrorsDetail", "outDiscards")
        values_by_key = [counters.get(key) for key in keys]
        addresses = row.get("ipv4", row.get("interfaceAddress", [])) or []
        if isinstance(addresses, str):
            addresses = [addresses]
        sample = {
            "admin_up": _state(admin), "oper_up": _state(oper),
            "capacity_bps": _speed(speed_value, speed_unit),
            "duplex": duplex if duplex in {"full", "half"} else "unknown",
            "in_octets": _int(values_by_key[0]), "out_octets": _int(values_by_key[1]),
            "errors": _int(values_by_key[2]), "discards": _int(values_by_key[3]),
            "tx_errors": _int(values_by_key[4]), "tx_discards": _int(values_by_key[5]),
            "counter_bits": 64, "counter_epoch_known": False, "vrf_known": False,
            "addresses": [str(ip_interface(address)) for address in addresses],
        }
        result.append({"name": name, "kind": _kind(name), "physical": _physical(name),
                       "index": _int(row.get("ifindex", row.get("interfaceIndex")), maximum=2**31 - 1), "sample": sample})
    if not result or len(result) > 8192:
        raise ValueError("interfaces_empty")
    return result


def _aoss_interfaces(raw: str) -> list[dict]:
    blocks = re.split(r"(?=^\s*Port\s*:\s*\S+)", raw, flags=re.I | re.M)
    result = []
    for block in blocks:
        header = re.search(r"^\s*Port\s*:\s*(\S+)", block, re.I | re.M)
        if not header:
            continue
        name = header.group(1)
        field = lambda label: (match.group(1).strip() if (match := re.search(
            rf"^\s*{label}\s*:\s*([^\n]+)", block, re.I | re.M)) else None)
        mode = field("Mode") or ""
        speed_match = re.search(r"(\d+(?:\.\d+)?)([GMT]?)", mode, re.I)
        speed_value = _speed(speed_match.group(1), "mbps") if speed_match else None
        result.append({"name": name, "kind": _kind(name), "physical": _physical(name), "index": None,
            "sample": {"admin_up": _state(field("Admin Status")), "oper_up": _state(field("Link Status")),
                "capacity_bps": speed_value, "duplex": "full" if "fdx" in mode.lower() else "half" if "hdx" in mode.lower() else "unknown",
                "in_octets": _int(field("Bytes Rx")), "out_octets": _int(field("Bytes Tx")),
                "errors": _int(field("Errors Rx")), "discards": _int(field("Drops Rx")),
                "tx_errors": _int(field("Errors Tx")), "tx_discards": _int(field("Drops Tx")),
                "counter_bits": 64, "counter_epoch_known": False, "vrf_known": False}})
    if not result or len(result) > 8192:
        raise ValueError("interfaces_empty")
    return result


def _comware_interfaces(raw: str) -> list[dict]:
    headers = list(re.finditer(r"^(\S+)\s+current state\s*:\s*([^\n]+)", raw, re.I | re.M))
    result = []
    for index, header in enumerate(headers):
        name = header.group(1)
        block = raw[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(raw)]
        protocol = re.search(r"Line protocol (?:current )?state\s*:\s*([^\n]+)", block, re.I)
        speed_match = re.search(r"Speed\s*:\s*(\d+(?:\.\d+)?)\s*([KMGT]?)bps", block, re.I)
        speed_value = _speed("".join(speed_match.groups()) + "bps") if speed_match else None
        duplex = re.search(r"Duplex\s*:\s*(Full|Half)", block, re.I)
        incoming = re.search(r"Input\s*:\s*([\d,]+)\s+bytes.*?([\d,]+)\s+errors.*?([\d,]+)\s+discards", block, re.I | re.S)
        outgoing = re.search(r"Output\s*:\s*([\d,]+)\s+bytes.*?([\d,]+)\s+errors.*?([\d,]+)\s+discards", block, re.I | re.S)
        if not incoming or not outgoing:
            raise ValueError("comware_counters_missing")
        addresses = []
        for address in re.findall(r"Internet Address(?: is)?\s*:\s*(\S+/\d+)", block, re.I):
            addresses.append(str(ip_interface(address)))
        pvid = re.search(r"PVID\s*:\s*(\d+)", block, re.I)
        result.append({"name": name, "kind": _kind(name), "physical": _physical(name), "index": None,
            "sample": {"admin_up": False if "administratively" in header.group(2).lower() else _state(header.group(2)),
                "oper_up": _state(protocol.group(1) if protocol else None), "capacity_bps": speed_value,
                "duplex": duplex.group(1).lower() if duplex else "unknown",
                "in_octets": _int(incoming.group(1)), "out_octets": _int(outgoing.group(1)),
                "errors": _int(incoming.group(2)), "discards": _int(incoming.group(3)),
                "tx_errors": _int(outgoing.group(2)), "tx_discards": _int(outgoing.group(3)),
                "pvid": _int(pvid.group(1), minimum=1, maximum=4094) if pvid else None,
                "addresses": addresses, "counter_bits": 64, "counter_epoch_known": False, "vrf_known": False}})
    if not result or len(result) > 8192:
        raise ValueError("interfaces_empty")
    return result


def _routeros_interfaces(raw: str) -> list[dict]:
    result = []
    for row in _routeros_records(raw):
        name = row.get("name")
        if not name:
            raise ValueError("routeros_interface_name_missing")
        disabled = _state(row.get("disabled"))
        result.append({"name": name, "kind": _kind(name), "physical": _physical(name),
            "index": _int(row.get("ifindex"), maximum=2**31 - 1),
            "sample": {"admin_up": None if disabled is None else not disabled, "oper_up": _state(row.get("running")),
                "capacity_bps": _speed(row.get("link-speed", row.get("speed")), "bps"),
                "in_octets": _int(row.get("rx-byte")), "out_octets": _int(row.get("tx-byte")),
                "errors": _int(row.get("rx-error")), "discards": _int(row.get("rx-drop")),
                "tx_errors": _int(row.get("tx-error")), "tx_discards": _int(row.get("tx-drop")),
                "counter_bits": 64, "counter_epoch_known": False, "vrf_known": False}})
    if not result or len(result) > 8192:
        raise ValueError("interfaces_empty")
    return result


def _interfaces(driver: str, raw: str) -> list[dict]:
    if driver in JSON_DRIVERS:
        return _json_interfaces(driver, raw)
    if driver == "hp_procurve":
        return _aoss_interfaces(raw)
    if driver in {"hp_comware", "h3c_comware7"}:
        return _comware_interfaces(raw)
    return _routeros_interfaces(raw)


def _identity(driver: str, raw: str) -> dict[str, str]:
    if driver == "arista_eos":
        value = _json(raw)
        return {"vendor": "Arista Networks", "model": str(value.get("modelName", ""))[:160],
                "version": str(value.get("version", ""))[:160], "serial": str(value.get("serialNumber", ""))[:160]}
    if driver == "aruba_aoscx":
        vendor = "HPE Aruba Networking"
        patterns = (r"Product Name\s*:\s*([^\n]+)", r"Version\s*:\s*([^\s]+)", r"Serial Number\s*:\s*(\S+)")
    elif driver == "hp_procurve":
        vendor = "HPE Aruba Networking"
        patterns = (r"(?:Product|Model)\s*:\s*([^\n]+)", r"(?:Primary Image|Software revision)\s*:\s*([^\s]+)", r"Serial Number\s*:\s*(\S+)")
    elif driver in {"hp_comware", "h3c_comware7"}:
        vendor = "HPE Aruba Networking" if driver == "hp_comware" else "H3C"
        patterns = (r"Device model\s*:\s*([^\n]+)", r"Comware Software,\s*Version\s*([^,\n]+)(?:,\s*Release\s*([^\s\n]+))?", r"Device serial number\s*:\s*(\S+)")
    else:
        values = {match.group(1).lower(): match.group(2).strip() for match in re.finditer(r"^\s*([a-z-]+)\s*:\s*([^\n]+)", raw, re.I | re.M)}
        return {"vendor": "MikroTik", "model": values.get("board-name", "")[:160],
                "version": values.get("version", "")[:160], "serial": ""}
    model = re.search(patterns[0], raw, re.I)
    version = re.search(patterns[1], raw, re.I)
    serial = re.search(patterns[2], raw, re.I)
    version_value = " ".join(part for part in (version.groups() if version else ()) if part)
    return {"vendor": vendor, "model": model.group(1).strip()[:160] if model else "",
            "version": version_value[:160], "serial": serial.group(1)[:160] if serial else ""}


def _name_map(device) -> dict[str, str]:
    from . import cisco, huawei
    result = {}
    for interface in device.interfaces:
        for value in (interface.name.lower(), cisco.canonical(interface.name), huawei.canonical(interface.name)):
            result[value] = interface.id
    return result


def _interface_id(names: dict[str, str], value: str) -> str | None:
    from . import cisco, huawei
    token = value.strip().split(".", 1)[0]
    return names.get(token.lower()) or names.get(cisco.canonical(token)) or names.get(huawei.canonical(token))


def _apply_vlans(driver: str, raw: str, device, batch) -> None:
    samples = {sample.interface_id: sample for sample in batch.interfaces}
    names = _name_map(device)
    rows = []
    if driver in JSON_DRIVERS:
        value = _json(raw).get("vlans")
        if not isinstance(value, (dict, list)):
            raise ValueError("vlans_missing")
        iterable = value.items() if isinstance(value, dict) else ((str(row.get("id", "")), row) for row in value)
        for vlan, row in iterable:
            if not isinstance(row, dict):
                raise ValueError("invalid_vlan")
            for port in row.get("untagged", row.get("interfaces", [])):
                rows.append((str(port), vlan, "access"))
            for port in row.get("tagged", []):
                rows.append((str(port), vlan, "trunk"))
    elif driver == "hp_procurve":
        rows = [(match.group(2), match.group(1), match.group(3).lower()) for match in re.finditer(
            r"^\s*(\d+)\s+\S+\s+(\S+)\s+(Untagged|Tagged)\s*$", raw, re.I | re.M)]
    elif driver in {"hp_comware", "h3c_comware7"}:
        rows = [(match.group(2), match.group(1), match.group(3).lower()) for match in re.finditer(
            r"^\s*(\d+)\s+\S+\s+(\S+)\s+(untagged|tagged)\s*$", raw, re.I | re.M)]
    else:
        for row in _routeros_records(raw):
            vlan = row.get("vlan-ids")
            for mode in ("untagged", "tagged"):
                for port in row.get(mode, "").split(","):
                    if vlan and port:
                        rows.append((port, vlan, "access" if mode == "untagged" else "trunk"))
    if not rows and raw.strip():
        raise ValueError("vlan_rows_missing")
    for name, vlan_value, mode in rows:
        identifier = _interface_id(names, name)
        vlan = _int(vlan_value, minimum=1, maximum=4094)
        if not identifier or identifier not in samples or vlan is None:
            raise ValueError("vlan_interface_missing")
        sample = samples[identifier]
        if mode in {"access", "untagged"}:
            sample.access_vlan = vlan
            sample.pvid = vlan
            sample.vlan_mode = "access"
        else:
            sample.vlan_mode = "trunk"
            sample.allowed_vlans = sorted(set((sample.allowed_vlans or []) + [vlan]))


def _network_rows(driver: str, kind: str, raw: str) -> list[dict[str, str]]:
    if driver == "aruba_aoscx":
        key = {"fdb": "mac_table", "arp": "arp_entries", "lldp": "neighbors"}[kind]
        rows = _json(raw).get(key)
    elif driver == "arista_eos":
        root = _json(raw)
        rows = {
            "fdb": root.get("unicastTable", {}).get("tableEntries") if isinstance(root.get("unicastTable"), dict) else None,
            "arp": root.get("ipV4Neighbors"), "lldp": root.get("lldpNeighbors"),
        }[kind]
    elif driver == "mikrotik_routeros":
        rows = _routeros_records(raw)
    else:
        rows = []
        patterns = {
            "fdb": r"^\s*([0-9a-f.:-]{12,17})\s+(\d+)\s+(\S+)(?:\s+(\S+))?\s*$",
            "arp": r"^\s*(\d+(?:\.\d+){3})\s+([0-9a-f.:-]{12,17})\s+(\S+)\s*$",
            "lldp": r"^\s*(\S+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\s*$",
        }
        for match in re.finditer(patterns[kind], raw, re.I | re.M):
            if kind == "fdb":
                rows.append({"mac": match.group(1), "vlan": match.group(2), "interface": match.group(3), "type": match.group(4) or "dynamic"})
            elif kind == "arp":
                rows.append({"address": match.group(1), "mac": match.group(2), "interface": match.group(3)})
            else:
                rows.append({"interface": match.group(1), "chassis": match.group(2).strip(),
                             "port": match.group(3).strip(), "name": match.group(4).strip()})
    if not isinstance(rows, list):
        raise ValueError(f"{kind}_rows_missing")
    return rows


def _row_value(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return str(value)
    return ""


def _apply_network(driver: str, outputs: dict[str, str], unavailable: dict[str, str], device, batch) -> None:
    from . import cisco
    command_by_parser = {command.parser: command.text for command in DRIVERS[driver][1]}
    names = _name_map(device)
    by_mac: dict[str, dict] = {}

    fdb_command = next((text for parser, text in command_by_parser.items() if parser.endswith(".fdb")), None)
    if fdb_command in outputs:
        try:
            for row in _network_rows(driver, "fdb", outputs[fdb_command]):
                mac = cisco.normalize_mac(_row_value(row, "mac", "macAddress", "mac-address"))
                vlan = _int(_row_value(row, "vlan", "vlanId", "vid"), minimum=1, maximum=4094)
                interface_id = _interface_id(names, _row_value(row, "interface", "port", "on-interface"))
                if not mac or vlan is None or not interface_id:
                    raise ValueError("fdb_identity_missing")
                by_mac[mac] = {"interface_id": interface_id, "vlan": vlan, "addresses": [],
                               "state": "static" if "static" in _row_value(row, "type", "entryType").lower() else "unknown"}
        except (ValueError, TypeError):
            unavailable[fdb_command] = "collector_parse_failed"

    arp_command = next((text for parser, text in command_by_parser.items() if parser.endswith(".arp")), None)
    if arp_command in outputs:
        try:
            for row in _network_rows(driver, "arp", outputs[arp_command]):
                mac = cisco.normalize_mac(_row_value(row, "mac", "hwAddress", "mac-address"))
                address = str(ip_address(_row_value(row, "address", "ipAddress", "ip-address")))
                if not mac:
                    raise ValueError("arp_mac_missing")
                value = by_mac.get(mac)
                if value is None:
                    interface_id = _interface_id(names, _row_value(row, "interface", "port", "on-interface"))
                    if not interface_id:
                        raise ValueError("arp_interface_missing")
                    value = by_mac.setdefault(mac, {"interface_id": interface_id, "vlan": None,
                                                    "addresses": [], "state": "unknown"})
                value["addresses"].append(address)
        except (ValueError, TypeError):
            unavailable[arp_command] = "collector_parse_failed"

    entries = [EndpointObservation(
        id=sha256(f"{driver}|{value['interface_id']}|{value['vlan']}|{mac}".encode()).hexdigest()[:32],
        interface_id=value["interface_id"], mac=mac, addresses=value["addresses"], vlan=value["vlan"],
        vrf_known=False, discovery="fdb" if value["vlan"] is not None else "arp", state=value["state"],
        evidence=f"{driver} read-only FDB/ARP correlation",
    ) for mac, value in sorted(by_mac.items())]
    if len(entries) > 2048:
        raise ValueError("endpoint_limit")
    if fdb_command in outputs or arp_command in outputs:
        failed = any(unavailable.get(command) == "collector_parse_failed" for command in (fdb_command, arp_command))
        batch.endpoints = EndpointCollection(status="partial" if failed else "ok", entries=entries,
                                             total_count=len(entries), source="ssh")

    lldp_command = next((text for parser, text in command_by_parser.items() if parser.endswith(".lldp")), None)
    if lldp_command in outputs:
        try:
            rows = _network_rows(driver, "lldp", outputs[lldp_command])
            for row in rows:
                local = _row_value(row, "interface", "localInterface", "interface-name")
                chassis = _row_value(row, "chassis", "chassisId", "mac-address")
                port = _row_value(row, "port", "neighborPort", "interface-name", "interface")
                label = _row_value(row, "name", "neighborDevice", "identity", "systemName") or chassis
                interface_id = _interface_id(names, local)
                if not interface_id or not chassis or not port:
                    raise ValueError("lldp_identity_missing")
                batch.neighbors.append(Neighbor(
                    id=sha256(f"{driver}|{interface_id}|{chassis}|{port}".encode()).hexdigest()[:32],
                    interface_id=interface_id, label=label[:160], relation="l2",
                    evidence=f"{driver} LLDP chassis={chassis}; port={port}"[:300],
                ))
            if len(batch.neighbors) > 1024:
                raise ValueError("neighbor_limit")
        except (ValueError, TypeError):
            unavailable[lldp_command] = "collector_parse_failed"

    vlan_command = next((text for parser, text in command_by_parser.items() if parser.endswith(".vlan")), None)
    if vlan_command in outputs:
        try:
            _apply_vlans(driver, outputs[vlan_command], device, batch)
        except (ValueError, TypeError):
            unavailable[vlan_command] = "collector_parse_failed"


def _health(driver: str, outputs: dict[str, str], unavailable: dict[str, str]) -> Health:
    command_by_parser = {command.parser: command.text for command in DRIVERS[driver][1]}
    result = Health()
    try:
        if driver == "aruba_aoscx":
            resource = _json(outputs.get(command_by_parser.get("aoscx.health"), "{}"))
            environment = _json(outputs.get(command_by_parser.get("aoscx.environment"), "{}"))
            result.cpu_percent = _float(resource.get("cpu_percent"))
            result.memory_percent = _float(resource.get("memory_percent"))
            result.temperature_c = _float(environment.get("temperature_c"), minimum=-100, maximum=250)
            result.fan = str(environment.get("fan", ""))[:160] or None
            result.power_supply = str(environment.get("power_supply", ""))[:160] or None
        elif driver == "arista_eos":
            resource = _json(outputs.get(command_by_parser.get("eos.health"), "{}"))
            environment = _json(outputs.get(command_by_parser.get("eos.environment"), "{}"))
            result.cpu_percent = _float(resource.get("cpuPercent"))
            result.memory_percent = _float(resource.get("memoryPercent"))
            result.temperature_c = _float(environment.get("temperatureC"), minimum=-100, maximum=250)
            result.fan = str(environment.get("fanStatus", ""))[:160] or None
            result.power_supply = str(environment.get("powerSupplyStatus", ""))[:160] or None
        elif driver in {"hp_comware", "h3c_comware7"}:
            cpu_command, memory_command = command_by_parser.get("comware7.cpu"), command_by_parser.get("comware7.memory")
            cpu = re.search(r"CPU (?:usage|utilization).*?:\s*(\d+(?:\.\d+)?)%", outputs.get(cpu_command, ""), re.I)
            memory = re.search(r"Memory (?:usage|using percentage).*?:\s*(\d+(?:\.\d+)?)%", outputs.get(memory_command, ""), re.I)
            result.cpu_percent = _float(cpu.group(1)) if cpu else None
            result.memory_percent = _float(memory.group(1)) if memory else None
            environment_command = command_by_parser.get("comware7.environment")
            environment = outputs.get(environment_command, "")
            temperature = re.search(r"Temperature\s*:\s*(-?\d+(?:\.\d+)?)", environment, re.I)
            result.temperature_c = _float(temperature.group(1), minimum=-100, maximum=250) if temperature else None
            fan = re.search(r"^(Fan[^\n]+)", environment, re.I | re.M)
            power = re.search(r"^((?:Power|PSU)[^\n]+)", environment, re.I | re.M)
            result.fan = fan.group(1)[:160] if fan else None
            result.power_supply = power.group(1)[:160] if power else None
        elif driver == "mikrotik_routeros":
            values = {match.group(1).lower(): match.group(2).strip() for match in re.finditer(
                r"^\s*([a-z-]+)\s*:\s*([^\n]+)", outputs.get(IDENTITY_COMMANDS[driver], ""), re.I | re.M)}
            result.cpu_percent = _float(values.get("cpu-load"))
            units = {"kib": 1024, "mib": 1024**2, "gib": 1024**3}
            def memory(value):
                match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(KiB|MiB|GiB)", value or "", re.I)
                return float(match.group(1)) * units[match.group(2).lower()] if match else None
            total, free = memory(values.get("total-memory")), memory(values.get("free-memory"))
            result.memory_percent = 100 * (total - free) / total if total and free is not None else None
            health_command = command_by_parser.get("routeros.health")
            health_values = {match.group(1).lower(): match.group(2).strip() for match in re.finditer(
                r"^\s*([a-z-]+)\s*:\s*([^\n]+)", outputs.get(health_command, ""), re.I | re.M)}
            result.temperature_c = _float(health_values.get("temperature", "").rstrip("C"), minimum=-100, maximum=250)
            result.power_supply = (f"voltage={health_values['voltage']}"[:160] if health_values.get("voltage") else None)
    except (ValueError, TypeError, ZeroDivisionError):
        for command in DRIVERS[driver][1]:
            if command.group == "health" and command.text in outputs:
                unavailable[command.text] = "collector_parse_failed"
        return Health()
    return result


def _modules(driver: str, outputs: dict[str, str], unavailable: dict[str, str]) -> list[dict]:
    command = next((item for item in DRIVERS[driver][1] if item.parser.endswith((".hardware",))), None)
    if not command or command.text not in outputs:
        return []
    try:
        if driver in JSON_DRIVERS:
            rows = _json(outputs[command.text]).get("inventory")
            if not isinstance(rows, list):
                raise ValueError("inventory_missing")
            result = [{"name": _row_value(row, "name"), "description": _row_value(row, "description"),
                       "part_number": _row_value(row, "partNumber", "part-number"),
                       "serial_number": _row_value(row, "serialNumber", "serial-number")} for row in rows]
        elif driver == "mikrotik_routeros":
            values = {match.group(1).lower(): match.group(2).strip() for match in re.finditer(
                r"^\s*([a-z-]+)\s*:\s*([^\n]+)", outputs[command.text], re.I | re.M)}
            result = [{"name": "routerboard", "description": values.get("model", ""),
                       "part_number": values.get("model", ""), "serial_number": values.get("serial-number", "")}]
        else:
            result = [{"name": match.group(1).strip(), "description": match.group(2).strip(),
                       "part_number": match.group(3).strip(), "serial_number": match.group(4).strip()}
                      for match in re.finditer(r"^\s*([^|]+)\|([^|]*)\|([^|]*)\|([^|]*)\s*$", outputs[command.text], re.M)]
        if not result or len(result) > 256:
            raise ValueError("inventory_empty")
        return result
    except (ValueError, TypeError):
        unavailable[command.text] = "collector_parse_failed"
        return []


def parse_p1(device, driver: str, outputs: dict[str, str], unavailable: dict[str, str], groups: set[str]) -> ReadResult:
    """Parse one P1 grammar and fail closed on cross-platform identity."""
    from .drivers import _identity_evidence, identify_platform, quality, split

    if driver not in P1_DRIVERS:
        raise ValueError("unsupported_p1_driver")
    required = [command for command in DRIVERS[driver][1] if command.required and command.group in groups]
    if any(command.text in unavailable for command in required):
        return ReadResult(device, metadata={group: metadata(
            group, driver, quality="error", complete=False,
            reason="required_command_unavailable",
            diagnostics={command: quality(code) for command, code in unavailable.items()},
        ) for group in groups})

    identity_command = IDENTITY_COMMANDS[driver]
    raw_identity = outputs.get(identity_command, "")
    try:
        platform = identify_platform({identity_command: raw_identity}) if raw_identity else None
        if platform and platform.runtime_driver_id != driver:
            result = ReadResult(device, metadata={group: metadata(
                group, driver, quality="error", complete=False,
                reason="collector_platform_mismatch",
            ) for group in groups})
            result.observed_profile_id = platform.profile_id
            result.identity_evidence = _identity_evidence(platform, device)
            return result
        details = _identity(driver, raw_identity)
        if not details["model"] or not details["version"]:
            raise ValueError("identity_fields_missing")
        interface_command = INTERFACE_COMMANDS[driver]
        entries = _interfaces(driver, outputs[interface_command]) if interface_command in outputs else []
        if entries:
            updated, batch = merge(device, driver, entries)
        else:
            updated, batch = device, Telemetry(observed_at=now(), source="ssh", reachability="reachable")
        updated = updated.model_copy(update={"vendor": details["vendor"], "model": details["model"],
            "os_version": details["version"], "serial": details["serial"] or device.serial})
        if "network" in groups:
            _apply_network(driver, outputs, unavailable, updated, batch)
        if "health" in groups:
            batch.health = _health(driver, outputs, unavailable)
        modules = _modules(driver, outputs, unavailable)
        if not details["serial"] and modules and modules[0].get("serial_number"):
            updated = updated.model_copy(update={"serial": modules[0]["serial_number"][:160]})
        extra = {"modules": modules}
        result = split(updated, batch, groups, driver, unavailable, extra)
        result.inventory_complete = bool(entries)
        if platform:
            result.observed_profile_id = platform.profile_id
            result.identity_evidence = _identity_evidence(platform, updated)
        return result
    except (ValueError, KeyError, TypeError, OverflowError):
        return ReadResult(device, metadata={group: metadata(
            group, driver, quality="parse_error", complete=False,
            reason="collector_parse_failed",
        ) for group in groups})
