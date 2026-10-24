"""Bounded S09 parsers for advanced, legacy and Linux-based NOS profiles.

Only normalization helpers are shared. Identity and interface grammars remain
profile-specific, and a mismatch never falls through to a neighboring family.
Raw device output is neither persisted nor returned.
"""
from __future__ import annotations

import json
import re
from xml.etree import ElementTree as StdXML

from defusedxml.common import DefusedXmlException

from .collection import ReadResult, metadata
from .contracts import Telemetry
from .database import now
from .driver_catalog import DRIVERS
from .p2_parsers import _apply_network, _entry, _require_interfaces, _rows, _value
from .structured_parsers import junos_interfaces, merge, text, xml


P3_DRIVERS = {
    "h3c_comware5", "h3c_comware9", "huawei_vrp_v600",
    "juniper_junos_evolved", "dell_sonic", "nvidia_cumulus_linux",
    "nvidia_onyx", "sonic_nos", "cisco_business",
}
IDENTITY_COMMANDS = {
    "h3c_comware5": "display version",
    "h3c_comware9": "display version",
    "huawei_vrp_v600": "display version",
    "juniper_junos_evolved": "show version | display xml | no-more",
    "dell_sonic": "show version",
    "nvidia_cumulus_linux": "nv show system --output json",
    "nvidia_onyx": "show version",
    "sonic_nos": "show version",
    "cisco_business": "show version",
}
INTERFACE_COMMANDS = {
    "h3c_comware5": "display interface",
    "h3c_comware9": "display interface",
    "huawei_vrp_v600": "display interface",
    "juniper_junos_evolved": "show interfaces extensive | display xml | no-more",
    "dell_sonic": "show interfaces status",
    "nvidia_cumulus_linux": "nv show interface --output json",
    "nvidia_onyx": "show interfaces ethernet",
    "sonic_nos": "show interfaces status",
    "cisco_business": "show interfaces status",
}
COUNTER_COMMANDS = {
    "dell_sonic": "show interfaces counters",
    "sonic_nos": "show interfaces counters",
    "cisco_business": "show interfaces counters",
}


def _blocks(raw: str, pattern: str):
    headers = list(re.finditer(pattern, raw, re.I | re.M))
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(raw)
        yield header, raw[header.end():end]


def _block_entries(raw: str, *, header: str, name, admin, oper, speed, duplex,
                   counters: tuple[str, ...]) -> list[dict]:
    result = []
    for match, block in _blocks(raw, header):
        result.append(_entry(
            name(match), admin(match, block), oper(match, block),
            _value(block, speed), _value(block, duplex),
            tuple(_value(block, pattern) for pattern in counters),
        ))
    return _require_interfaces(result)


def _comware5_interfaces(raw: str) -> list[dict]:
    return _block_entries(
        raw, header=r"^(\S+)\s+current state\s*:\s*(UP|DOWN|Administratively DOWN)\s*$",
        name=lambda m: m.group(1), admin=lambda m, _b: m.group(2),
        oper=lambda _m, b: _value(b, r"^\s*Line protocol current state\s*:\s*([^\n]+)"),
        speed=r"^\s*Speed\s*:\s*([^\n]+)", duplex=r"^\s*Duplex\s*:\s*([^\n]+)",
        counters=(r"^\s*Input bytes\s*:\s*([\d,]+)", r"^\s*Output bytes\s*:\s*([\d,]+)",
                  r"^\s*Input errors\s*:\s*([\d,]+)", r"^\s*Input discards\s*:\s*([\d,]+)",
                  r"^\s*Output errors\s*:\s*([\d,]+)", r"^\s*Output discards\s*:\s*([\d,]+)"),
    )


def _comware9_interfaces(raw: str) -> list[dict]:
    return _block_entries(
        raw, header=r"^(\S+)\s+current state is\s+(UP|DOWN|Administratively DOWN)\s*$",
        name=lambda m: m.group(1), admin=lambda m, _b: m.group(2),
        oper=lambda _m, b: _value(b, r"^\s*Protocol state is\s+([^\n]+)"),
        speed=r"^\s*Current speed\s*:\s*([^\n]+)", duplex=r"^\s*Current duplex\s*:\s*([^\n]+)",
        counters=(r"^\s*Input octets\s*:\s*([\d,]+)", r"^\s*Output octets\s*:\s*([\d,]+)",
                  r"^\s*Input errors\s*:\s*([\d,]+)", r"^\s*Input drops\s*:\s*([\d,]+)",
                  r"^\s*Output errors\s*:\s*([\d,]+)", r"^\s*Output drops\s*:\s*([\d,]+)"),
    )


def _vrp600_interfaces(raw: str) -> list[dict]:
    return _block_entries(
        raw, header=r"^Interface\s*:\s*(\S+)\s*$",
        name=lambda m: m.group(1),
        admin=lambda _m, b: _value(b, r"^\s*Admin state\s*:\s*([^\n]+)"),
        oper=lambda _m, b: _value(b, r"^\s*Oper state\s*:\s*([^\n]+)"),
        speed=r"^\s*Speed\s*:\s*([^\n]+)", duplex=r"^\s*Duplex\s*:\s*([^\n]+)",
        counters=(r"^\s*Input octets\s*:\s*([\d,]+)", r"^\s*Output octets\s*:\s*([\d,]+)",
                  r"^\s*Input errors\s*:\s*([\d,]+)", r"^\s*Input discards\s*:\s*([\d,]+)",
                  r"^\s*Output errors\s*:\s*([\d,]+)", r"^\s*Output discards\s*:\s*([\d,]+)"),
    )


def _onyx_interfaces(raw: str) -> list[dict]:
    return _block_entries(
        raw, header=r"^Interface ethernet\s+(\S+)\s*$",
        name=lambda m: f"Eth{m.group(1)}",
        admin=lambda _m, b: _value(b, r"^\s*Admin state\s*:\s*([^\n]+)"),
        oper=lambda _m, b: _value(b, r"^\s*Operational state\s*:\s*([^\n]+)"),
        speed=r"^\s*Speed\s*:\s*([^\n]+)", duplex=r"^\s*Duplex\s*:\s*([^\n]+)",
        counters=(r"^\s*Rx bytes\s*:\s*([\d,]+)", r"^\s*Tx bytes\s*:\s*([\d,]+)",
                  r"^\s*Rx errors\s*:\s*([\d,]+)", r"^\s*Rx discards\s*:\s*([\d,]+)",
                  r"^\s*Tx errors\s*:\s*([\d,]+)", r"^\s*Tx discards\s*:\s*([\d,]+)"),
    )


def _table_interfaces(driver: str, outputs: dict[str, str]) -> list[dict]:
    status_rows = _rows(outputs[INTERFACE_COMMANDS[driver]], 5)
    counters = {row[0]: row[1:] for row in _rows(outputs[COUNTER_COMMANDS[driver]], 7)}
    result = []
    for name, admin, oper, speed, duplex in status_rows:
        if name not in counters:
            raise ValueError("interface_counters_missing")
        result.append(_entry(name, admin, oper, speed, duplex, tuple(counters[name])))
    return _require_interfaces(result)


def _cumulus_interfaces(raw: str) -> list[dict]:
    value = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    rows = value.get("interfaces")
    if not isinstance(rows, list) or len(rows) > 8192:
        raise ValueError("cumulus_interfaces_missing")
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise ValueError("cumulus_interface_invalid")
        kind = row.get("type")
        if kind not in {"swp", "bond", "bridge", "vrf", "loopback", "management"}:
            raise ValueError("cumulus_interface_type_unknown")
        counters = row.get("counters") or {}
        entry = _entry(
            row["name"], row.get("admin_state"), row.get("oper_state"),
            row.get("speed"), row.get("duplex"),
            tuple(counters.get(key) for key in (
                "in_octets", "out_octets", "errors", "discards",
                "tx_errors", "tx_discards",
            )),
        )
        entry["kind"] = {
            "swp": "subinterface" if row.get("breakout_parent") else "ethernet",
            "bond": "port_channel", "bridge": "svi", "vrf": "svi",
            "loopback": "loopback", "management": "management",
        }[kind]
        front_panel = row.get("front_panel_port")
        entry["physical"] = kind == "swp" and isinstance(front_panel, str) and bool(front_panel)
        if entry["physical"]:
            entry.update(
                physical_port_key=f"front-panel:{front_panel}",
                physical_port_label=front_panel,
                physical_port_group="Front panel",
            )
            if parent := row.get("breakout_parent"):
                entry.update(
                    parent_port_key=f"front-panel:{parent}",
                    parent_port_label=parent,
                )
        result.append(entry)
    return _require_interfaces(result)


INTERFACE_PARSERS = {
    "h3c_comware5": lambda outputs: _comware5_interfaces(outputs[INTERFACE_COMMANDS["h3c_comware5"]]),
    "h3c_comware9": lambda outputs: _comware9_interfaces(outputs[INTERFACE_COMMANDS["h3c_comware9"]]),
    "huawei_vrp_v600": lambda outputs: _vrp600_interfaces(outputs[INTERFACE_COMMANDS["huawei_vrp_v600"]]),
    "juniper_junos_evolved": lambda outputs: junos_interfaces(xml(outputs[INTERFACE_COMMANDS["juniper_junos_evolved"]])),
    "dell_sonic": lambda outputs: _table_interfaces("dell_sonic", outputs),
    "nvidia_cumulus_linux": lambda outputs: _cumulus_interfaces(outputs[INTERFACE_COMMANDS["nvidia_cumulus_linux"]]),
    "nvidia_onyx": lambda outputs: _onyx_interfaces(outputs[INTERFACE_COMMANDS["nvidia_onyx"]]),
    "sonic_nos": lambda outputs: _table_interfaces("sonic_nos", outputs),
    "cisco_business": lambda outputs: _table_interfaces("cisco_business", outputs),
}


def _identity(driver: str, raw: str) -> dict[str, str]:
    if driver == "juniper_junos_evolved":
        root = xml(raw)
        if "evolved" not in " ".join(root.itertext()).lower():
            raise ValueError("junos_evolved_identity_missing")
        return {
            "vendor": "Juniper", "model": text(root, ".//product-model") or "",
            "version": text(root, ".//junos-version") or "",
            "serial": text(root, ".//chassis-serial-number") or "",
        }
    if driver == "nvidia_cumulus_linux":
        value = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        if value.get("os") != "Cumulus Linux":
            raise ValueError("cumulus_identity_missing")
        return {"vendor": "NVIDIA Networking", "model": str(value.get("model", "")),
                "version": str(value.get("version", "")), "serial": str(value.get("serial", ""))}
    patterns = {
        "h3c_comware5": ("H3C", r"^Device model\s*:\s*([^\n]+)", r"Comware Software,\s*Version\s+(5\.[^,\n]+)(?:,\s*Release\s+([^\n]+))?", r"^Device serial number\s*:\s*(\S+)"),
        "h3c_comware9": ("H3C", r"^Device model\s*:\s*([^\n]+)", r"Comware Software,\s*Version\s+(9\.[^,\n]+)(?:,\s*Release\s+([^\n]+))?", r"^Device serial number\s*:\s*(\S+)"),
        "huawei_vrp_v600": ("Huawei", r"^Device model\s*:\s*([^\n]+)", r"VRP[^\n]*\b(V600R\w+)", r"^Device serial number\s*:\s*(\S+)"),
        "dell_sonic": ("Dell Technologies", r"^Platform\s*:\s*([^\n]+)", r"^SONiC Software Version\s*:\s*([^\n]+)", r"^Service Tag\s*:\s*(\S+)"),
        "nvidia_onyx": ("NVIDIA Networking", r"^System model\s*:\s*([^\n]+)", r"^Onyx version\s*:\s*([^\n]+)", r"^System serial number\s*:\s*(\S+)"),
        "sonic_nos": ("Unknown", r"^Platform\s*:\s*([^\n]+)", r"^SONiC Software Version\s*:\s*([^\n]+)", r"^Serial Number\s*:\s*(\S+)"),
        "cisco_business": ("Cisco", r"^System Description\s*:\s*(CBS\S+)", r"^Firmware Version\s*:\s*([^\n]+)", r"^Serial Number\s*:\s*(\S+)"),
    }
    vendor, model_pattern, version_pattern, serial_pattern = patterns[driver]
    model = _value(raw, model_pattern)
    version_match = re.search(version_pattern, raw, re.I | re.M)
    version = " ".join(value for value in version_match.groups() if value).strip() if version_match else None
    serial = _value(raw, serial_pattern)
    if driver == "dell_sonic" and not re.search(r"^Distribution\s*:\s*Dell Enterprise SONiC\s*$", raw, re.I | re.M):
        raise ValueError("dell_sonic_distribution_missing")
    if driver == "sonic_nos":
        distribution = _value(raw, r"^Distribution\s*:\s*([^\n]+)")
        image = _value(raw, r"^Docker images\s*:\s*([^\n]+)")
        if not distribution or not image or re.search(r"Dell Enterprise SONiC", distribution, re.I):
            raise ValueError("sonic_distribution_or_image_missing")
    return {"vendor": vendor, "model": model or "", "version": version or "", "serial": serial or ""}


def parse_p3(device, driver: str, outputs: dict[str, str], unavailable: dict[str, str], groups: set[str]) -> ReadResult:
    """Parse exactly one P3 profile and fail closed on family ambiguity."""
    from .drivers import _identity_evidence, identify_platform, quality, split

    if driver not in P3_DRIVERS:
        raise ValueError("unsupported_p3_driver")
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
        entries = INTERFACE_PARSERS[driver](outputs) if interface_command in outputs else []
        if entries:
            updated, batch = merge(device, driver, entries)
        else:
            updated, batch = device, Telemetry(observed_at=now(), source="ssh", reachability="reachable")
        updated = updated.model_copy(update={
            "vendor": details["vendor"], "model": details["model"][:160],
            "os_version": details["version"][:160],
            "serial": details["serial"][:160] or device.serial,
        })
        if "network" in groups:
            _apply_network(driver, outputs, unavailable, updated, batch)
        result = split(updated, batch, groups, driver, unavailable, {"modules": []})
        result.inventory_complete = bool(entries)
        if platform:
            result.observed_profile_id = platform.profile_id
            result.identity_evidence = _identity_evidence(platform, updated)
        return result
    except (
        ValueError, KeyError, TypeError, OverflowError, json.JSONDecodeError,
        StdXML.ParseError, DefusedXmlException,
    ):
        return ReadResult(device, metadata={group: metadata(
            group, driver, quality="parse_error", complete=False,
            reason="collector_parse_failed",
        ) for group in groups})
