"""Bounded multi-platform reads using the same pinned SSH policy as terminals."""
import asyncio
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from ipaddress import ip_address, ip_interface

import ntc_templates
import sqlalchemy as sa
import textfsm

from . import cisco, huawei
from .collection import ReadResult, metadata, upsert
from .collector import linux_snapshot, read_limited
from .contracts import Health, InterfaceSample
from .database import now
from .driver_catalog import DRIVERS, GROUPS, SUPPORTED, VERSION
from .p1_parsers import P1_DRIVERS, parse_p1
from .ssh import ConnectionPolicyError, connect
from .structured_parsers import parse_structured
from .fixture_drivers import DeviceDriver, FixtureDriver, GenericReadOnlyDriver, UnsupportedCapability

PAGER = re.compile(r"-{2,}\s*\(?more[^\r\n]{0,80}?-{2,}", re.I)


class Reader(cisco.IOSReader):
    """Exact operational command allowlist; session-only pagination responses."""
    def __init__(self, process, allowed):
        super().__init__(process)
        self.allowed = allowed

    async def read_prompt(self):
        raw, pages = "", 0
        while True:
            chunk = await self.process.stdout.read(8192)
            if not chunk:
                raise ConnectionPolicyError("collector_disconnected")
            raw += chunk
            if len(raw.encode()) > 2_000_000:
                raise ConnectionPolicyError("collector_output_limit")
            output = cisco.clean(raw)
            pattern = re.escape(self.prompt) if self.prompt else r"([^\s\n][^\n]{0,158}[>#])"
            match = re.search(r"(?:^|\n)" + pattern + r"\s*$", output)
            if match:
                if self.prompt is None:
                    self.prompt = match.group(1)
                return PAGER.sub("", output[:match.start()])
            # IOS can erase the marker with backspaces. Junos wraps "(more)".
            count = max(len(PAGER.findall(output)), len(PAGER.findall(cisco.ANSI.sub("", raw))))
            if count > pages:
                if count > 200:
                    raise ConnectionPolicyError("collector_pagination_limit")
                self.process.stdin.write(" " * (count - pages))
                await self.process.stdin.drain()
                pages = count

    async def command(self, command):
        if command not in self.allowed:
            raise ConnectionPolicyError("collector_command_denied")
        self.process.stdin.write(command + "\n")
        await self.process.stdin.drain()
        output = await asyncio.wait_for(self.read_prompt(), 20)
        # Remove the echoed command, not lines with arbitrary matching substrings.
        lines = output.splitlines()
        if lines and lines[0].strip() == command:
            output = "\n".join(lines[1:])
        if re.search(r"authorization failed|not authorized|permission denied|insufficient privilege|no permission|not enough permissions", output, re.I):
            raise ConnectionPolicyError("collector_permission_denied")
        if re.search(r"^\s*(?:%\s*(?:Invalid|Incomplete|Ambiguous|Unrecognized)|Error\s*:|Unrecognized command|syntax error|bad command name|expected end of command|failure:)", output, re.I | re.M):
            raise ConnectionPolicyError("collector_command_unsupported")
        return output


def ntc(parser, raw):
    name = parser.removeprefix("ntc.") + ".textfsm"
    # Only the literal catalog supplies parser names. No uploaded templates.
    root = Path(ntc_templates.__file__).parent / "templates"
    with (root / name).open() as template:
        machine = textfsm.TextFSM(template)
        rows = machine.ParseText(raw)
    if len(rows) > 8192:
        raise ValueError("template_row_limit")
    return [dict(zip((key.lower() for key in machine.header), row)) for row in rows]


def quality(code):
    return {"collector_permission_denied": "permission_denied", "collector_command_unsupported": "unsupported",
            "collector_timeout": "timeout", "collector_parse_failed": "parse_error"}.get(code, "error")


@dataclass(frozen=True)
class PlatformIdentity:
    profile_id: str
    runtime_driver_id: str | None
    vendor: str
    os_family: str


def identify_platform(outputs):
    text = "\n".join(outputs.values())
    if re.search(r"ArubaOS[- ]CX|AOS-CX|\bFL\.10\.\d+", text, re.I):
        return PlatformIdentity("aruba_aoscx", "aruba_aoscx", "HPE Aruba Networking", "AOS-CX")
    if re.search(r"ArubaOS-Switch|ProVision|\bWC\.16\.\d+", text, re.I):
        return PlatformIdentity("aruba_aoss", "hp_procurve", "HPE Aruba Networking", "AOS-Switch")
    if (
        re.search(r"\bArista\b", text, re.I)
        and re.search(r"\bEOS\b|Software image version|\"systemMacAddress\"\s*:", text, re.I)
    ):
        return PlatformIdentity("arista_eos", "arista_eos", "Arista Networks", "EOS")
    if re.search(r"HP(?:E)?\s+Comware Software,\s*Version\s+7\.", text, re.I):
        return PlatformIdentity("hpe_comware", "hp_comware", "HPE Aruba Networking", "Comware")
    if re.search(r"H3C\s+Comware Software,\s*Version\s+7\.", text, re.I):
        return PlatformIdentity("h3c_comware7", "h3c_comware7", "H3C", "Comware V7")
    if re.search(r"H3C\s+Comware Software,\s*Version\s+5\.", text, re.I):
        return PlatformIdentity("h3c_comware5", None, "H3C", "Comware V5")
    if re.search(r"H3C\s+Comware Software,\s*Version\s+9\.", text, re.I):
        return PlatformIdentity("h3c_comware9", None, "H3C", "Comware V9")
    if re.search(r"^\s*platform\s*:\s*MikroTik\s*$", text, re.I | re.M) and re.search(
        r"^\s*version\s*:\s*(?:6|7)\.", text, re.I | re.M
    ):
        return PlatformIdentity("mikrotik_routeros", "mikrotik_routeros", "MikroTik", "RouterOS")
    if re.search(r"IOS[ -]?XE|CAT9K_IOSXE", text, re.I):
        return PlatformIdentity("cisco_iosxe", "cisco_iosxe", "Cisco", "IOS-XE")
    if re.search(r"VRP[^\n]{0,100}\bV600\b|CloudEngine[^\n]{0,100}\bV600\b", text, re.I):
        return PlatformIdentity("huawei_vrp_v600", None, "Huawei", "VRP V600")
    if re.search(r"VRP\s*\(R\)|Huawei Versatile Routing", text, re.I):
        if not re.search(r"\bV200\w*\b|Version\s+5\.\d+", text, re.I):
            raise ConnectionPolicyError("collector_platform_unsupported")
        return PlatformIdentity("huawei_vrp_v200", "huawei_vrp", "Huawei", "VRP V200")
    if re.search(r"Junos OS Evolved|JUNOS Evolved", text, re.I):
        return PlatformIdentity("juniper_junos_evolved", None, "Juniper", "Junos OS Evolved")
    if re.search(r"Junos:|JUNOS|<junos-version>", text):
        return PlatformIdentity("juniper_junos", "juniper_junos", "Juniper", "Junos OS")
    if re.search(r"NX-OS|NXOS|nxos_ver_str", text):
        return PlatformIdentity("cisco_nxos", "cisco_nxos", "Cisco", "NX-OS")
    if re.search(r"Cisco IOS", text, re.I):
        return PlatformIdentity("cisco_ios", "cisco_ios", "Cisco", "IOS")
    raise ConnectionPolicyError("collector_platform_unsupported")


def identify(outputs):
    """Backward-compatible runtime ID resolver for implemented profiles."""
    identity = identify_platform(outputs)
    if identity.runtime_driver_id is None:
        raise ConnectionPolicyError("collector_platform_unsupported")
    return identity.runtime_driver_id


def _identity_command(driver):
    return next(
        command.text for command in DRIVERS[driver][1]
        if command.group == "inventory" and command.required
    )


def _identity_evidence(identity, device):
    return {
        "vendor": identity.vendor,
        "model": device.model or None,
        "os_family": identity.os_family,
        "os_version": device.os_version or None,
        "management_mode": device.management_mode,
    }


async def collect(store, vault, device, groups=GROUPS, authorize=lambda: None):
    requested = set(groups)
    driver = device.resolved_collector if device.collector == "auto" else device.collector
    if driver and driver not in DRIVERS:
        raise ConnectionPolicyError("collector_platform_unsupported")
    if driver == "linux_ssh":
        async with connect(store, vault, device) as connection:
            values = []
            for command in ("ip -j -s link show", "ip -j address show", "cat /proc/uptime",
                            "cat /proc/sys/kernel/random/boot_id", "ip -j neigh show"):
                authorize()
                try:
                    values.append(await read_limited(connection, command))
                except ValueError:
                    if command != "ip -j neigh show":
                        raise
                    values.append(None)
        updated, batch = linux_snapshot(device, *values[:3], values[3].strip(), values[4])
        updated = updated.model_copy(update={"resolved_collector": driver, "driver_version": VERSION,
            "validation_level": DRIVERS[driver][3]})
        result = split(updated, batch, requested, driver, {}, {})
        result.inventory_complete = True
        return result
    outputs, unavailable = {}, {}
    platform = None
    identity_failure = None
    async with asyncio.timeout(180):
        async with connect(store, vault, device) as connection:
            authorize()
            process = await connection.create_process(term_type="vt100", term_size=(240, 60))
            all_commands = {c.text for _, plan, _, _ in DRIVERS.values() for c in plan} | {
                "show version", "display version", "/system resource print without-paging",
            }
            reader = Reader(process, all_commands)
            try:
                await asyncio.wait_for(reader.read_prompt(), 20)
                if not driver:
                    for probe in ("show version", "display version", "/system resource print without-paging"):
                        authorize()
                        try:
                            outputs[probe] = await reader.command(probe)
                            platform = identify_platform(outputs)
                            driver = platform.runtime_driver_id
                            break
                        except ConnectionPolicyError as error:
                            if str(error) not in {"collector_platform_unsupported", "collector_command_unsupported"}:
                                raise
                    if not driver:
                        identity_failure = platform
                        if identity_failure is None:
                            raise ConnectionPolicyError("collector_platform_unsupported")
                else:
                    identity_command = _identity_command(driver)
                    authorize()
                    outputs[identity_command] = await reader.command(identity_command)
                    platform = identify_platform({identity_command: outputs[identity_command]})
                    if platform.runtime_driver_id is None:
                        identity_failure = platform
                    else:
                        driver = platform.runtime_driver_id
                if not device.driver_version:
                    requested.update(GROUPS)
                # Current interface identity is needed to correlate slow network
                # tables. It is read once in this SSH session, not per command.
                if requested & {"inventory", "network"}:
                    requested.add("fast")
                if identity_failure:
                    authorize()
                    process.close()
                revision = sha256(f"{device.connection_revision}:{driver or platform.profile_id}:{VERSION}:{device.os_version}".encode()).hexdigest()
                with store.engine.connect() as conn:
                    cached = dict(conn.execute(sa.select(store.capabilities.c.command_id, store.capabilities.c.status)
                        .where(store.capabilities.c.device_id == device.id, store.capabilities.c.revision_key == revision)).all())
                for command in (() if identity_failure else DRIVERS[driver][1]):
                    if command.group not in requested or command.text in outputs:
                        continue
                    authorize()
                    status = cached.get(command.text)
                    if status in {"collector_command_unsupported", "collector_permission_denied"} or (
                        status == "collector_parse_failed" and not command.required
                    ):
                        unavailable[command.text] = cached[command.text]
                        continue
                    try:
                        outputs[command.text] = await reader.command(command.text)
                    except ConnectionPolicyError as error:
                        if str(error) not in {"collector_command_unsupported", "collector_permission_denied"}:
                            raise
                        unavailable[command.text] = str(error)
                authorize()
            finally:
                process.close()
    if identity_failure:
        result = ReadResult(device, metadata={group: metadata(
            group, identity_failure.profile_id, quality="error", complete=False,
            reason="collector_platform_unsupported",
        ) for group in requested})
        result.observed_profile_id = identity_failure.profile_id
        result.identity_evidence = _identity_evidence(identity_failure, device)
        return result
    if driver in P1_DRIVERS:
        result = parse_p1(device, driver, outputs, unavailable, requested)
    elif driver in {"juniper_junos", "cisco_nxos"}:
        result = parse_structured(device, driver, outputs, unavailable, requested)
    else:
        result = parse_text(device, driver, outputs, unavailable, requested)
    result.device = result.device.model_copy(update={"resolved_collector": driver, "driver_version": VERSION,
        "validation_level": DRIVERS[driver][3]})
    if platform:
        result.observed_profile_id = platform.profile_id
        result.identity_evidence = _identity_evidence(platform, result.device)
    # Cache only status, never CLI output. Unsupported commands are invalidated
    # by driver, software version or credential/connection revision changes.
    authorize()
    with store.engine.begin() as conn:
        # A successful fresh read replaces any older negative capability.
        # Required parse failures are retried under scheduler backoff; they are
        # not evidence that a supported command can never be read again.
        successful = outputs.keys() - unavailable.keys()
        if successful:
            conn.execute(store.capabilities.delete().where(
                store.capabilities.c.device_id == device.id,
                store.capabilities.c.command_id.in_(successful)))
        for command, code in unavailable.items():
            upsert(conn, store.capabilities,
                (store.capabilities.c.device_id == device.id) & (store.capabilities.c.command_id == command),
                dict(device_id=device.id, command_id=command, revision_key=revision, status=code, checked_at=now()))
    return result


NETWORK_FIELDS = {"interface_id", "addresses", "vrf", "vrf_known", "access_vlan", "pvid", "vlan_mode",
                  "native_vlan", "allowed_vlans", "lag_interface_id", "optical_rx_dbm", "optical_tx_dbm",
                  "transceiver_media", "transceiver_model", "transceiver_present"}


def split(updated, batch, groups, driver, unavailable, extra):
    data = batch.model_dump(mode="json")
    result = ReadResult(updated)
    for group in groups:
        diagnostics = {c.text: quality(unavailable[c.text]) for c in DRIVERS[driver][1]
                       if c.group == group and c.text in unavailable}
        required = [c for c in DRIVERS[driver][1] if c.group == group and c.required]
        failed = next((unavailable[c.text] for c in required if c.text in unavailable), None)
        if failed:
            result.metadata[group] = metadata(group, driver, quality=quality(failed), complete=False,
                reason=failed, diagnostics=diagnostics)
            continue
        if group == "fast":
            payload = {"interfaces": [{k: v for k, v in s.items() if k not in NETWORK_FIELDS - {"interface_id"}} for s in data["interfaces"]]}
        elif group == "network":
            payload = {k: data[k] for k in ("endpoints", "neighbors")}
            payload["interfaces"] = [{k: v for k, v in s.items() if k in NETWORK_FIELDS} for s in data["interfaces"]]
            if data["endpoints"]["status"] in {"partial", "error"}:
                diagnostics["endpoints"] = "partial" if data["endpoints"]["status"] == "partial" else "parse_error"
        elif group == "health":
            payload = {"health": data["health"], "interfaces": [
                {"interface_id": s["interface_id"], "poe_watts": s["poe_watts"]} for s in data["interfaces"] if s.get("poe_watts") is not None]}
        else:
            payload = {"model": updated.model, "serial": updated.serial, "os_version": updated.os_version,
                       "components": [c.model_dump(mode="json") for c in updated.components], **extra}
            result.inventory_complete = True
        # Unsupported fields are explicit even where the valid subset succeeds.
        fields = {key: "unsupported" for key in SUPPORTED[driver][group]}
        if group in {"fast", "health"}:
            values = payload.get("interfaces", []) if group == "fast" else [payload["health"]]
            for key in fields:
                if any(s.get(key) is not None and s.get(key) != "unknown" for s in values):
                    fields[key] = "ok"
        else:
            for key in fields:
                if payload.get(key):
                    fields[key] = "ok"
            if group == "network":
                if data["endpoints"]["status"] == "ok":
                    if "arp" in fields:
                        fields["arp"] = "ok"
                    if driver == "linux_ssh" and "ndp" in fields:
                        fields["ndp"] = "ok"
                    elif "fdb" in fields:
                        fields["fdb"] = "ok"
                if data["neighbors"]:
                    fields["lldp"] = "ok"
                for name in ("addresses", "vrf"):
                    if any(s.get(name) for s in data["interfaces"]):
                        fields[name] = "ok"
                for name, columns in {"vlan": ("access_vlan", "pvid", "native_vlan", "allowed_vlans"),
                                      "lag": ("lag_interface_id",), "dom": ("optical_rx_dbm", "optical_tx_dbm")}.items():
                    if any(s.get(column) is not None for s in data["interfaces"] for column in columns):
                        fields[name] = "ok"
            elif group == "inventory" and any(c["kind"] == "chassis" for c in payload["components"]):
                fields["chassis"] = "ok"
        if group == "health" and payload["interfaces"] and "poe_watts" in fields:
            fields["poe_watts"] = "ok"
        result.payloads[group] = payload
        result.metadata[group] = metadata(group, driver, quality="partial" if diagnostics else "ok",
            complete=not diagnostics, diagnostics=diagnostics, fields=fields,
            reason="optional_commands_unavailable" if diagnostics else None)
    return result


def parse_text(device, driver, outputs, unavailable, groups):
    """Health parsing cannot invalidate otherwise valid interface inventory."""
    health_commands = {c.text for c in DRIVERS[driver][1] if c.group == "health"}
    result = _parse_text(device, driver, {k: v for k, v in outputs.items() if k not in health_commands},
                         unavailable, groups - {"health"}) if groups - {"health"} else ReadResult(device)
    if "health" in groups:
        health = _parse_text(result.device, driver, {k: v for k, v in outputs.items()
            if k in health_commands or k in {"show version", "display version"}}, unavailable, {"health"})
        result.payloads.update(health.payloads)
        result.metadata.update(health.metadata)
        if health.observed_profile_id:
            result.observed_profile_id = health.observed_profile_id
            result.identity_evidence = health.identity_evidence
    return result


def _parse_text(device, driver, outputs, unavailable, groups):
    module = huawei if driver == "huawei_vrp" else cisco
    interface_command = "display interface" if module is huawei else "show interfaces"
    required = [c for c in DRIVERS[driver][1] if c.required and c.group in groups]
    if any(c.text in unavailable for c in required):
        return ReadResult(device, metadata={g: metadata(g, driver, quality="error", complete=False,
            reason="required_command_unavailable", diagnostics={c: quality(v) for c, v in unavailable.items()}) for g in groups})
    parsing_command = None
    try:
        at = now()
        parsing_command = interface_command if interface_command in outputs else None
        entries = module.parse_interfaces(outputs[interface_command]) if interface_command in outputs else {}
        warnings = []
        parsing_command = "display version" if module is huawei else "show version"
        version = outputs.get("display version" if module is huawei else "show version", "")
        platform = identify_platform({"version": version}) if version else None
        if platform and platform.runtime_driver_id != driver:
            result = ReadResult(device, metadata={group: metadata(
                group, driver, quality="error", complete=False,
                reason="collector_platform_mismatch",
            ) for group in groups})
            result.observed_profile_id = platform.profile_id
            result.identity_evidence = _identity_evidence(platform, device)
            return result
        snapshot = {"at": at, "entries": entries, "release": device.os_version, "model": device.model,
                    "serial": device.serial, "health": Health(), "outputs": outputs, "unavailable": unavailable}
        if module is cisco:
            if entries:
                parsing_command = "show interfaces status"
                cisco.apply_status(entries, outputs["show interfaces status"])
            if "show ip interface" in outputs:
                parsing_command = "show ip interface"
                cisco.apply_addresses(entries, outputs["show ip interface"], warnings)
            parsing_command = None
            release = re.search(r"\bVersion\s+([^,\s]+)", version)
            model = re.search(r"^\s*Model [Nn]umber\s*:\s*(\S+)", version, re.I | re.M) or re.search(
                r"^\s*cisco\s+([A-Z][A-Z0-9-]+)\s+\(", version, re.I | re.M)
            serial = re.search(r"(?:System serial number\s*:|Processor board ID)\s*(\S+)", version, re.I)
            snapshot.update(release=release[1] if release else device.os_version,
                            model=model[1] if model else device.model, serial=serial[1] if serial else device.serial)
            cpu = re.search(r"CPU utilization for five seconds:\s*(\d+(?:\.\d+)?)%", outputs.get("show processes cpu", ""), re.I)
            memory = re.search(r"(?:Processor|System)\s+\S+\s+(\d+)\s+(\d+)", outputs.get("show memory statistics", ""))
            snapshot["health"] = Health(cpu_percent=float(cpu[1]) if cpu else None,
                memory_percent=100 * int(memory[2]) / int(memory[1]) if memory and int(memory[1]) else None)
            for command, value in (("show processes cpu", cpu), ("show memory statistics", memory)):
                if command in outputs and value is None:
                    unavailable[command] = "collector_parse_failed"
            environment = outputs.get("show environment all")
            if environment is not None:
                temperature = re.search(r"System Temperature Value\s*:\s*(-?\d+(?:\.\d+)?)", environment, re.I)
                fan = re.search(r"^\s*((?:FAN|Fan|System FAN)[^\n]{0,100}(?:OK|Good|Failed|Faulty))\s*$", environment, re.M)
                psu = re.search(r"^\s*((?:Power Supply|PSU)[^\n]{0,100}(?:OK|Good|Failed|Faulty))\s*$", environment, re.M)
                snapshot["health"].temperature_c = float(temperature[1]) if temperature else None
                snapshot["health"].fan = fan[1] if fan else None
                snapshot["health"].power_supply = psu[1] if psu else None
                if not any((temperature, fan, psu)):
                    unavailable["show environment all"] = "collector_parse_failed"
        else:
            parsing_command = None
            release = re.search(r"VRP\s*\(R\)\s*software,\s*Version\s+([^\n]+)", version, re.I)
            snapshot["release"] = release[1][:160] if release else device.os_version
            model = re.search(r"^(?:Quidway|HUAWEI)\s+(\S+)\s+(?:Routing\s+)?Switch\s+uptime is", version, re.I | re.M)
            snapshot["model"] = model[1][:160] if model else device.model
            for line in outputs.get("display ip interface brief", "").splitlines():
                fields = line.split()
                if len(fields) > 1 and module.canonical(fields[0]) in entries and "/" in fields[1]:
                    try:
                        address = str(ip_interface(fields[1]))
                        entries[module.canonical(fields[0])]["sample"]["addresses"] = [address]
                    except ValueError:
                        unavailable["display ip interface brief"] = "collector_parse_failed"
            snapshot["health"] = Health(
                cpu_percent=huawei.match_value(r"CPU (?:usage|utilization)\s*(?:for five seconds)?\s*:\s*(\d+(?:\.\d+)?)%", outputs.get("display cpu-usage", ""), float),
                memory_percent=huawei.match_value(r"Memory Using Percentage Is\s*:\s*(\d+(?:\.\d+)?)%", outputs.get("display memory-usage", ""), float))
            for command, value in (("display cpu-usage", snapshot["health"].cpu_percent),
                                   ("display memory-usage", snapshot["health"].memory_percent)):
                if command in outputs and value is None:
                    unavailable[command] = "collector_parse_failed"
        uptime = re.search(r"uptime is\s+([^\n]+)", version)
        if uptime:
            units = {"year": 31536000, "week": 604800, "day": 86400, "hour": 3600, "minute": 60, "second": 1}
            parts = re.findall(r"(\d+)\s+(year|week|day|hour|minute|second)s?", uptime[1])
            snapshot["health"].uptime_seconds = sum(int(n) * units[u] for n, u in parts) if parts else None
        parsing_command = None
        if entries:
            updated, batch = module.merge_snapshot(device, snapshot)
            if module is huawei and version:
                updated = updated.model_copy(update={"model": snapshot["model"], "vendor": "Huawei"})
        else:
            from .contracts import Telemetry
            updated, batch = device, Telemetry(observed_at=at, source="ssh", reachability="reachable", health=snapshot["health"],
                interfaces=[InterfaceSample(interface_id=i.id, quality="unknown") for i in device.interfaces])
        extra = enrich_ios(driver, updated, batch, outputs, unavailable) if module is cisco else {}
        result = split(updated, batch, groups, driver, unavailable, extra)
        result.inventory_complete = bool(entries)
        if platform:
            result.observed_profile_id = platform.profile_id
            result.identity_evidence = _identity_evidence(platform, updated)
        return result
    except (ValueError, KeyError, OverflowError, ConnectionPolicyError):
        # A status-table failure says nothing about `show version` or the
        # interface-detail command. Do not poison unrelated capability entries.
        if parsing_command and parsing_command in outputs:
            unavailable[parsing_command] = "collector_parse_failed"
        diagnostics = {parsing_command or "parsed_data_validation": "parse_error"}
        return ReadResult(device, metadata={g: metadata(g, driver, quality="parse_error",
            complete=False, reason="collector_parse_failed", diagnostics=diagnostics) for g in groups})


def enrich_ios(driver, device, batch, outputs, unavailable):
    samples = {cisco.canonical(i.name): next((s for s in batch.interfaces if s.interface_id == i.id), None) for i in device.interfaces}
    extra = {}
    for command in DRIVERS[driver][1]:
        if not command.parser.startswith("ntc.") or command.text not in outputs:
            continue
        try:
            rows = ntc(command.parser, outputs[command.text])
            if not rows and outputs[command.text].strip():
                raise ValueError("unrecognized_empty_result")
            if command.text == "show inventory":
                extra["modules"] = rows
            for row in rows:
                sample = samples.get(cisco.canonical(row.get("interface", row.get("local_interface", ""))))
                if command.text == "show interfaces switchport" and sample:
                    sample.access_vlan = int(row["access_vlan"]) if row["access_vlan"].isdigit() else None
                    sample.native_vlan = int(row["native_vlan"]) if row["native_vlan"].isdigit() else None
                    sample.vlan_mode = "trunk" if "trunk" in row["mode"] else "access" if "access" in row["mode"] else "unknown"
                    vlans = set()
                    for value in row["trunking_vlans"]:
                        for token in value.split(","):
                            if re.fullmatch(r"\d+(?:-\d+)?", token):
                                bounds = [int(v) for v in token.split("-")]
                                if not 1 <= bounds[0] <= bounds[-1] <= 4094:
                                    raise ValueError("vlan_range")
                                vlans.update(range(bounds[0], bounds[-1] + 1))
                    sample.allowed_vlans = sorted(vlans) if vlans else None
                elif command.text == "show etherchannel summary":
                    bundle = samples.get(cisco.canonical(row["bundle_name"]))
                    for member in row["member_interface"]:
                        if bundle and (member_sample := samples.get(cisco.canonical(member))):
                            member_sample.lag_interface_id = bundle.interface_id
                elif command.text == "show power inline" and sample:
                    sample.poe_watts = float(row["power"]) if re.fullmatch(r"\d+(?:\.\d+)?", row["power"]) else None
                elif command.text == "show lldp neighbors detail" and sample:
                    from .contracts import Neighbor
                    peer = row.get("neighbor_name") or row.get("chassis_id")
                    if peer:
                        addresses = []
                        for value in re.split(r"[\s,]+", row.get("mgmt_address", "")):
                            try:
                                address = ip_address(value)
                                if not (address.is_unspecified or address.is_multicast or address.is_loopback):
                                    addresses.append(str(address))
                            except ValueError:
                                pass  # An absent/non-IP management field is not an address.
                        batch.neighbors.append(Neighbor(id=sha256(f"{sample.interface_id}:{peer}:{row.get('neighbor_port_id')}".encode()).hexdigest(),
                            interface_id=sample.interface_id, label=peer[:160], relation="l2", addresses=addresses[:32],
                            evidence=("LLDP: " + row.get("neighbor_port_id", ""))[:300]))
        except (ValueError, KeyError, textfsm.TextFSMError):
            unavailable[command.text] = "collector_parse_failed"
    return extra
