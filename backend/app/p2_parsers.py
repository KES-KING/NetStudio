"""Bounded S07 Dell, Extreme and standalone FortiSwitch CLI parsers.

Identity and interface grammars are deliberately platform-specific.  Only the
validated normalized value helpers and the bounded network row envelope are
shared.  Raw CLI output is never persisted or returned to callers.
"""
from __future__ import annotations

from hashlib import sha256
from ipaddress import ip_address
import re

from .collection import ReadResult, metadata
from .contracts import EndpointCollection, EndpointObservation, Neighbor, Telemetry
from .database import now
from .driver_catalog import DRIVERS
from .structured_parsers import merge


P2_DRIVERS = {
    "dell_os10", "dell_force10", "dell_os6", "extreme_exos",
    "extreme_vsp", "extreme_slxos", "fortinet_fortiswitchos",
}
IDENTITY_COMMANDS = {
    "dell_os10": "show version",
    "dell_force10": "show version",
    "dell_os6": "show version",
    "extreme_exos": "show version",
    "extreme_vsp": "show sys-info",
    "extreme_slxos": "show version",
    "fortinet_fortiswitchos": "get system status",
}
INTERFACE_COMMANDS = {
    "dell_os10": "show interface",
    "dell_force10": "show interfaces",
    "dell_os6": "show interfaces",
    "extreme_exos": "show ports statistics no-refresh",
    "extreme_vsp": "show interfaces",
    "extreme_slxos": "show interface",
    "fortinet_fortiswitchos": "diagnose switch physical-ports list",
}


def _int(value, *, minimum: int = 0, maximum: int = 2**64 - 1) -> int | None:
    if value in {None, "", "--", "unknown"}:
        return None
    if isinstance(value, bool):
        raise ValueError("invalid_integer")
    result = int(str(value).replace(",", "").strip())
    if not minimum <= result <= maximum:
        raise ValueError("integer_out_of_range")
    return result


def _state(value) -> bool | None:
    token = str(value or "").strip().lower()
    if token in {"up", "enabled", "enable", "active", "true"}:
        return True
    if token in {"down", "disabled", "disable", "inactive", "false", "administratively down"}:
        return False
    return None


def _speed(value, unit: str = "mbps") -> float | None:
    if value in {None, "", "--", "unknown", "-"}:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*([kmgt]?)", str(value), re.I)
    if not match:
        return None
    scale = {"": 1_000_000 if unit == "mbps" else 1, "k": 1_000,
             "m": 1_000_000, "g": 1_000_000_000, "t": 1_000_000_000_000}
    result = float(match.group(1)) * scale[match.group(2).lower()]
    return result if result > 0 else None


def _kind(name: str) -> str:
    token = name.lower().replace(" ", "")
    if re.match(r"^(?:po\d|port-channel|mlt\d|lag\d|trk\d)", token):
        return "port_channel"
    if token.startswith(("vlan", "ve")):
        return "svi"
    if token.startswith(("lo", "loopback")):
        return "loopback"
    if "." in token:
        return "subinterface"
    return "ethernet"


def _physical(name: str) -> bool:
    token = name.lower().replace(" ", "")
    return _kind(name) == "ethernet" and bool(re.match(
        r"^(?:port\d+|\d+(?::\d+|/\d+)+|(?:eth|ethernet|te|tengigabitethernet|"
        r"fo|fortygige|gi|gigabitethernet)\d|sw\d+/port\d+)", token,
    ))


def _value(raw: str, pattern: str) -> str | None:
    match = re.search(pattern, raw, re.I | re.M)
    return match.group(1).strip() if match else None


def _blocks(raw: str, pattern: str):
    headers = list(re.finditer(pattern, raw, re.I | re.M))
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(raw)
        yield header, raw[header.end():end]


def _entry(name, admin, oper, speed, duplex, counters):
    values = [_int(value) for value in counters]
    admin_up, oper_up = _state(admin), _state(oper)
    if not name or admin_up is None or oper_up is None or values[0] is None or values[1] is None:
        raise ValueError("interface_required_fields_missing")
    duplex_value = str(duplex or "").strip().lower()
    return {
        "name": name, "kind": _kind(name), "physical": _physical(name), "index": None,
        "sample": {
            "admin_up": admin_up, "oper_up": oper_up,
            "capacity_bps": _speed(speed),
            "duplex": "full" if "full" in duplex_value else "half" if "half" in duplex_value else "unknown",
            "in_octets": values[0], "out_octets": values[1],
            "errors": values[2], "discards": values[3],
            "tx_errors": values[4], "tx_discards": values[5],
            "counter_bits": 64, "counter_epoch_known": False,
            "vrf_known": False,
        },
    }


def _dell_os10_interfaces(raw: str) -> list[dict]:
    result = []
    pattern = r"^Ethernet\s+(\S+)\s+is\s+([^,]+),\s*line protocol is\s+(\S+)\s*$"
    for header, block in _blocks(raw, pattern):
        result.append(_entry(
            f"ethernet{header.group(1)}", header.group(2), header.group(3),
            _value(block, r"^\s*Speed\s*:\s*([^\n]+)"),
            _value(block, r"^\s*Duplex\s*:\s*([^\n]+)"),
            (_value(block, r"^\s*Input bytes\s*:\s*([\d,]+)"),
             _value(block, r"^\s*Output bytes\s*:\s*([\d,]+)"),
             _value(block, r"^\s*Input errors\s*:\s*([\d,]+)"),
             _value(block, r"^\s*Input discards\s*:\s*([\d,]+)"),
             _value(block, r"^\s*Output errors\s*:\s*([\d,]+)"),
             _value(block, r"^\s*Output discards\s*:\s*([\d,]+)")),
        ))
    return _require_interfaces(result)


def _dell_os9_interfaces(raw: str) -> list[dict]:
    result = []
    pattern = r"^((?:TenGigabitEthernet|FortyGigE|GigabitEthernet)\S+)\s+is\s+([^,]+),\s*line protocol is\s+(\S+)\s*$"
    for header, block in _blocks(raw, pattern):
        incoming = re.search(r"Input Statistics\s*:\s*([\d,]+)\s+bytes,\s*([\d,]+)\s+errors,\s*([\d,]+)\s+discards", block, re.I)
        outgoing = re.search(r"Output Statistics\s*:\s*([\d,]+)\s+bytes,\s*([\d,]+)\s+errors,\s*([\d,]+)\s+discards", block, re.I)
        if not incoming or not outgoing:
            raise ValueError("os9_counters_missing")
        result.append(_entry(
            header.group(1), header.group(2), header.group(3),
            _value(block, r"^\s*LineSpeed\s*:\s*([^\n]+)"),
            _value(block, r"^\s*Duplex\s*:\s*([^\n]+)"),
            (incoming.group(1), outgoing.group(1), incoming.group(2), incoming.group(3), outgoing.group(2), outgoing.group(3)),
        ))
    return _require_interfaces(result)


def _dell_os6_interfaces(raw: str) -> list[dict]:
    result = []
    for header, block in _blocks(raw, r"^Interface\s*:\s*(\S+)\s*$"):
        result.append(_entry(
            header.group(1), _value(block, r"^\s*Admin Mode\s*:\s*([^\n]+)"),
            _value(block, r"^\s*Link Status\s*:\s*([^\n]+)"),
            _value(block, r"^\s*Speed\s*:\s*([^\n]+)"),
            _value(block, r"^\s*Duplex\s*:\s*([^\n]+)"),
            tuple(_value(block, pattern) for pattern in (
                r"^\s*Input Octets\s*:\s*([\d,]+)", r"^\s*Output Octets\s*:\s*([\d,]+)",
                r"^\s*Input Errors\s*:\s*([\d,]+)", r"^\s*Input Discards\s*:\s*([\d,]+)",
                r"^\s*Output Errors\s*:\s*([\d,]+)", r"^\s*Output Discards\s*:\s*([\d,]+)",
            )),
        ))
    return _require_interfaces(result)


def _extreme_exos_interfaces(raw: str) -> list[dict]:
    result = []
    for header, block in _blocks(raw, r"^Port\s*:\s*(\d+:\d+)\s*$"):
        result.append(_entry(
            header.group(1), _value(block, r"^\s*Admin State\s*:\s*([^\n]+)"),
            _value(block, r"^\s*Link State\s*:\s*([^\n]+)"),
            _value(block, r"^\s*Port Speed\s*:\s*([^\n]+)"),
            _value(block, r"^\s*Duplex\s*:\s*([^\n]+)"),
            tuple(_value(block, pattern) for pattern in (
                r"^\s*Rx Byte Count\s*:\s*([\d,]+)", r"^\s*Tx Byte Count\s*:\s*([\d,]+)",
                r"^\s*Rx Error Count\s*:\s*([\d,]+)", r"^\s*Rx Discard Count\s*:\s*([\d,]+)",
                r"^\s*Tx Error Count\s*:\s*([\d,]+)", r"^\s*Tx Discard Count\s*:\s*([\d,]+)",
            )),
        ))
    return _require_interfaces(result)


def _extreme_fabric_interfaces(raw: str) -> list[dict]:
    result = []
    for header, block in _blocks(raw, r"^Port\s+(\d+/\d+)\s*$"):
        result.append(_entry(
            header.group(1), _value(block, r"^\s*Admin\s*:\s*([^\n]+)"),
            _value(block, r"^\s*Oper\s*:\s*([^\n]+)"),
            _value(block, r"^\s*Speed\s*:\s*([^\n]+)"),
            _value(block, r"^\s*Duplex\s*:\s*([^\n]+)"),
            tuple(_value(block, pattern) for pattern in (
                r"^\s*In Octets\s*:\s*([\d,]+)", r"^\s*Out Octets\s*:\s*([\d,]+)",
                r"^\s*In Errors\s*:\s*([\d,]+)", r"^\s*In Discards\s*:\s*([\d,]+)",
                r"^\s*Out Errors\s*:\s*([\d,]+)", r"^\s*Out Discards\s*:\s*([\d,]+)",
            )),
        ))
    return _require_interfaces(result)


def _extreme_slx_interfaces(raw: str) -> list[dict]:
    result = []
    pattern = r"^Ethernet\s+(\S+)\s+is\s+([^,]+),\s*line protocol is\s+(\S+)\s*$"
    for header, block in _blocks(raw, pattern):
        result.append(_entry(
            f"Ethernet {header.group(1)}", header.group(2), header.group(3),
            _value(block, r"^\s*LineSpeed\s*:\s*([^\n]+)"),
            _value(block, r"^\s*Duplex\s*:\s*([^\n]+)"),
            tuple(_value(block, pattern) for pattern in (
                r"^\s*Input octets\s*:\s*([\d,]+)", r"^\s*Output octets\s*:\s*([\d,]+)",
                r"^\s*Input errors\s*:\s*([\d,]+)", r"^\s*Input discards\s*:\s*([\d,]+)",
                r"^\s*Output errors\s*:\s*([\d,]+)", r"^\s*Output discards\s*:\s*([\d,]+)",
            )),
        ))
    return _require_interfaces(result)


def _fortiswitch_interfaces(raw: str) -> list[dict]:
    result = []
    pattern = r"^Port\(([^)]+)\)\s+is Admin\s+(up|down),\s*line protocol is\s+(up|down)\s*$"
    for header, block in _blocks(raw, pattern):
        mode = re.search(r"(full|half)-duplex,\s*([\d.]+\s*[KMGT]?)b/s", block, re.I)
        incoming = re.search(r"^\s*input\s*:\s*([\d,]+)\s+bytes.*?([\d,]+)\s+errors,\s*([\d,]+)\s+drops", block, re.I | re.M)
        outgoing = re.search(r"^\s*output\s*:\s*([\d,]+)\s+bytes.*?([\d,]+)\s+errors,\s*([\d,]+)\s+drops", block, re.I | re.M)
        if not mode or not incoming or not outgoing:
            raise ValueError("fortiswitch_counters_missing")
        result.append(_entry(
            header.group(1), header.group(2), header.group(3), mode.group(2), mode.group(1),
            (incoming.group(1), outgoing.group(1), incoming.group(2), incoming.group(3), outgoing.group(2), outgoing.group(3)),
        ))
    return _require_interfaces(result)


def _require_interfaces(result: list[dict]) -> list[dict]:
    if not result or len(result) > 8192:
        raise ValueError("interfaces_empty")
    return result


INTERFACE_PARSERS = {
    "dell_os10": _dell_os10_interfaces,
    "dell_force10": _dell_os9_interfaces,
    "dell_os6": _dell_os6_interfaces,
    "extreme_exos": _extreme_exos_interfaces,
    "extreme_vsp": _extreme_fabric_interfaces,
    "extreme_slxos": _extreme_slx_interfaces,
    "fortinet_fortiswitchos": _fortiswitch_interfaces,
}


def _identity(driver: str, raw: str) -> dict:
    if driver == "dell_os10":
        model, version, serial, vendor = (
            _value(raw, r"^\s*Product\s*:\s*([^\n]+)"),
            _value(raw, r"^\s*OS Version\s*:\s*([^\n]+)"),
            _value(raw, r"^\s*Service Tag\s*:\s*(\S+)"), "Dell Technologies",
        )
    elif driver == "dell_force10":
        model, version, serial, vendor = (
            _value(raw, r"^\s*System Type\s*:\s*([^\n]+)"),
            _value(raw, r"^\s*Dell(?: EMC)? Networking OS Version\s*:\s*([^\n]+)"),
            _value(raw, r"^\s*Service Tag\s*:\s*(\S+)"), "Dell Technologies",
        )
    elif driver == "dell_os6":
        model, version, serial, vendor = (
            _value(raw, r"^\s*System Model ID\s*:\s*([^\n]+)"),
            _value(raw, r"^\s*Software Version\s*:\s*([^\n]+)"),
            _value(raw, r"^\s*Serial Number\s*:\s*(\S+)"), "Dell Technologies",
        )
    elif driver == "extreme_exos":
        model, version, serial, vendor = (
            _value(raw, r"^\s*Switch\s*:\s*([^\n]+)"),
            _value(raw, r"ExtremeXOS version\s+([^\s]+)") or _value(raw, r"Switch Engine version\s+([^\s]+)"),
            _value(raw, r"^\s*System Serial Number\s*:\s*(\S+)"), "Extreme Networks",
        )
    elif driver == "extreme_vsp":
        model, version, serial, vendor = (
            _value(raw, r"^\s*System Description\s*:\s*Extreme Networks\s+(.+?)\s+(?:Fabric Engine|VOSS)\s*$"),
            _value(raw, r"^\s*System Software Version\s*:\s*([^\n]+)"),
            _value(raw, r"^\s*Chassis Serial Number\s*:\s*(\S+)"), "Extreme Networks",
        )
    elif driver == "extreme_slxos":
        model, version, serial, vendor = (
            _value(raw, r"^\s*System Type\s*:\s*([^\n]+)"),
            _value(raw, r"^\s*SLX-OS Version\s*:\s*([^\n]+)"),
            _value(raw, r"^\s*Chassis Serial Number\s*:\s*(\S+)"), "Extreme Networks",
        )
    else:
        version_line = _value(raw, r"^\s*Version\s*:\s*(FortiSwitch-\S+\s+v[^,\n]+)")
        model_match = re.search(r"FortiSwitch-([^\s,]+)", version_line or "", re.I)
        version_match = re.search(r"\bv([^,\s]+)", version_line or "", re.I)
        model, version, serial, vendor = (
            f"FortiSwitch-{model_match.group(1)}" if model_match else None,
            version_match.group(1) if version_match else None,
            _value(raw, r"^\s*Serial-Number\s*:\s*(\S+)"), "Fortinet",
        )
    constraints = {}
    if driver == "extreme_vsp" and re.search(r"^\s*SSH Secure Mode\s*:\s*(?:enabled|on)\s*$", raw, re.I | re.M):
        constraints["snmp"] = "blocked_by_ssh_secure_mode"
    return {
        "vendor": vendor, "model": (model or "")[:160],
        "version": (version or "")[:160], "serial": (serial or "")[:160],
        "transport_constraints": constraints,
    }


def _port_key(value: str) -> str:
    token = re.sub(r"\s+", "", value.strip().lower())
    replacements = (
        ("tengigabitethernet", "te"), ("gigabitethernet", "gi"),
        ("fortygige", "fo"), ("ethernet", "eth"),
    )
    for source, target in replacements:
        if token.startswith(source):
            token = target + token[len(source):]
            break
    return token


def _name_map(device) -> dict[str, str]:
    return {_port_key(interface.name): interface.id for interface in device.interfaces}


def _rows(raw: str, fields: int) -> list[list[str]]:
    rows = [
        [value.strip() for value in line.split("|")]
        for line in raw.splitlines() if "|" in line
    ]
    rows = [row for row in rows if len(row) == fields and all(row)]
    if not rows and raw.strip():
        raise ValueError("bounded_rows_missing")
    if len(rows) > 8192:
        raise ValueError("bounded_rows_limit")
    return rows


def _command(driver: str, suffix: str) -> str | None:
    return next((item.text for item in DRIVERS[driver][1] if item.parser.endswith(suffix)), None)


def _apply_network(driver: str, outputs: dict[str, str], unavailable: dict[str, str], device, batch) -> None:
    from . import cisco

    names = _name_map(device)
    samples = {sample.interface_id: sample for sample in batch.interfaces}
    by_mac: dict[str, dict] = {}

    vlan_command = _command(driver, ".vlan")
    if vlan_command in outputs:
        try:
            for vlan_value, _name, port, mode in _rows(outputs[vlan_command], 4):
                interface_id = names.get(_port_key(port))
                vlan = _int(vlan_value, minimum=1, maximum=4094)
                if interface_id not in samples or vlan is None:
                    raise ValueError("vlan_interface_missing")
                sample = samples[interface_id]
                if mode.lower() in {"untagged", "access", "u"}:
                    sample.access_vlan = sample.pvid = vlan
                    sample.vlan_mode = "access"
                elif mode.lower() in {"tagged", "trunk", "t"}:
                    sample.vlan_mode = "trunk"
                    sample.allowed_vlans = sorted(set((sample.allowed_vlans or []) + [vlan]))
                else:
                    raise ValueError("vlan_mode_unknown")
        except (ValueError, TypeError):
            unavailable[vlan_command] = "collector_parse_failed"

    fdb_command = _command(driver, ".fdb")
    if fdb_command in outputs:
        try:
            fdb_rows = _rows(outputs[fdb_command], 4)
            for vlan_value, raw_mac, entry_type, port in fdb_rows:
                mac = cisco.normalize_mac(raw_mac)
                vlan = _int(vlan_value, minimum=1, maximum=4094)
                interface_id = names.get(_port_key(port))
                if not mac or vlan is None or not interface_id:
                    raise ValueError("fdb_identity_missing")
                by_mac[mac] = {
                    "interface_id": interface_id, "vlan": vlan, "addresses": [],
                    "state": "static" if "static" in entry_type.lower() else "unknown",
                }
        except (ValueError, TypeError):
            unavailable[fdb_command] = "collector_parse_failed"

    arp_command = _command(driver, ".arp")
    if arp_command in outputs:
        try:
            for raw_address, raw_mac, port in _rows(outputs[arp_command], 3):
                mac = cisco.normalize_mac(raw_mac)
                address = str(ip_address(raw_address))
                if not mac:
                    raise ValueError("arp_mac_missing")
                value = by_mac.get(mac)
                if value is None:
                    interface_id = names.get(_port_key(port))
                    if not interface_id:
                        raise ValueError("arp_interface_missing")
                    value = by_mac.setdefault(mac, {
                        "interface_id": interface_id, "vlan": None,
                        "addresses": [], "state": "unknown",
                    })
                value["addresses"].append(address)
        except (ValueError, TypeError):
            unavailable[arp_command] = "collector_parse_failed"

    entries = [EndpointObservation(
        id=sha256(f"{driver}|{value['interface_id']}|{value['vlan']}|{mac}".encode()).hexdigest()[:32],
        interface_id=value["interface_id"], mac=mac,
        addresses=value["addresses"], vlan=value["vlan"], vrf_known=False,
        discovery="fdb" if value["vlan"] is not None else "arp",
        state=value["state"], evidence=f"{driver} read-only FDB/ARP correlation",
    ) for mac, value in sorted(by_mac.items())]
    if len(entries) > 2048:
        raise ValueError("endpoint_limit")
    if fdb_command in outputs or arp_command in outputs:
        failed = any(unavailable.get(command) == "collector_parse_failed" for command in (fdb_command, arp_command))
        batch.endpoints = EndpointCollection(
            status="partial" if failed else "ok", entries=entries,
            total_count=len(entries), source="ssh",
        )

    lldp_command = _command(driver, ".lldp")
    if lldp_command in outputs:
        try:
            for local, chassis, port, label in _rows(outputs[lldp_command], 4):
                interface_id = names.get(_port_key(local))
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


def parse_p2(device, driver: str, outputs: dict[str, str], unavailable: dict[str, str], groups: set[str]) -> ReadResult:
    """Parse one S07 grammar and stop before cross-platform fallback."""
    from .drivers import _identity_evidence, identify_platform, quality, split

    if driver not in P2_DRIVERS:
        raise ValueError("unsupported_p2_driver")
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
        entries = INTERFACE_PARSERS[driver](outputs[interface_command]) if interface_command in outputs else []
        if entries:
            updated, batch = merge(device, driver, entries)
        else:
            updated, batch = device, Telemetry(
                observed_at=now(), source="ssh", reachability="reachable",
            )
        updated = updated.model_copy(update={
            "vendor": details["vendor"], "model": details["model"],
            "os_version": details["version"],
            "serial": details["serial"] or device.serial,
        })
        if "network" in groups:
            _apply_network(driver, outputs, unavailable, updated, batch)
        extra = {"modules": []}
        if details["transport_constraints"]:
            extra["transport_constraints"] = details["transport_constraints"]
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
