"""Bounded, read-only Cisco IOS collection for Catalyst 2960-X switches.

Only fixed ``show`` commands are executed. Parsed observations enter
persistence; raw CLI output is never logged or returned to the browser. Port
geometry comes from ``show interfaces status`` rather than the model name.
"""
import asyncio
from hashlib import sha256
from ipaddress import ip_interface
import re

from pydantic import ValidationError
import sqlalchemy as sa

from .contracts import EndpointCollection, EndpointObservation, Health, InterfaceSample, ManagedDevice, Telemetry
from .database import now
from .models import Interface, Observation, PhysicalComponent, PhysicalPort, PortBinding
from .ssh import ConnectionPolicyError, connect, target_allowed


COMMANDS = ("show version", "show interfaces", "show interfaces status", "show ip interface",
            "show mac address-table", "show arp")
MAX_OUTPUT = 2_000_000
COMMAND_TIMEOUT = 20
SESSION_TIMEOUT = 120
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
MORE = re.compile(r"[ \t]*-{2,}[ \t]*More[ \t]*-{2,}[ \t]*", re.I)
INTERFACE_HEADER = re.compile(
    r"^\s*(\S+)\s+is\s+([^,\n]+),\s*line protocol is\s+([^\n(]+)(?:\s+\([^\n)]*\))?\s*$",
    re.I | re.M,
)
MAC = r"[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}"


def clean(raw):
    value = ANSI.sub("", raw).replace("\r\n", "\n").replace("\r", "\n")
    # IOS uses backspaces while repainting paged output.
    repainted = []
    for character in value:
        if character == "\x08":
            if repainted and repainted[-1] != "\n":
                repainted.pop()
        else:
            repainted.append(character)
    value = "".join(repainted)
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", value)


class IOSReader:
    def __init__(self, process):
        self.process = process
        self.prompt = None

    async def read_prompt(self):
        raw, pages = "", 0
        while True:
            chunk = await self.process.stdout.read(8192)
            if not chunk:
                raise ConnectionPolicyError("collector_disconnected")
            raw += chunk
            if len(raw) > MAX_OUTPUT:
                raise ConnectionPolicyError("collector_output_limit")
            output = clean(raw)
            if self.prompt is None:
                match = re.search(r"(?:^|\n)([^\s\n][^\n]{0,78}[>#])\s*$", output)
            else:
                match = re.search(r"(?:^|\n)" + re.escape(self.prompt) + r"\s*$", output)
            if match:
                if self.prompt is None:
                    self.prompt = match.group(1)
                return MORE.sub("", output[:match.start()])
            # Count against the raw stream too: IOS may erase ``--More--``
            # with backspaces before repainting the next page.
            page_count = max(len(MORE.findall(output)), len(MORE.findall(ANSI.sub("", raw))))
            if page_count > pages:
                if page_count > 512:
                    raise ConnectionPolicyError("collector_output_limit")
                pages = page_count
                self.process.stdin.write(" ")
                await self.process.stdin.drain()

    async def command(self, command):
        if command not in COMMANDS:
            raise ConnectionPolicyError("collector_command_denied")
        self.process.stdin.write(command + "\n")
        await self.process.stdin.drain()
        output = await asyncio.wait_for(self.read_prompt(), COMMAND_TIMEOUT)
        if re.search(r"(?:authorization failed|not authorized|permission denied|insufficient privilege)", output, re.I):
            raise ConnectionPolicyError("collector_permission_denied")
        if re.search(r"^\s*%\s*(?:Invalid input|Incomplete command|Ambiguous command|Unrecognized command)", output, re.I | re.M):
            raise ConnectionPolicyError("collector_command_unsupported")
        return output


async def collect_cisco(store, vault, device, authorize=lambda: None):
    outputs, unavailable = {}, {}
    observed_at = None
    started_at = now()
    try:
        async with asyncio.timeout(SESSION_TIMEOUT):
            async with connect(store, vault, device) as connection:
                authorize()
                process = await connection.create_process(term_type="vt100", term_size=(200, 48))
                reader = IOSReader(process)
                try:
                    await asyncio.wait_for(reader.read_prompt(), COMMAND_TIMEOUT)
                    for command in COMMANDS:
                        authorize()
                        try:
                            outputs[command] = await reader.command(command)
                            if command == "show interfaces status":
                                observed_at = now()
                        except ConnectionPolicyError as error:
                            if command in COMMANDS[:3] or str(error) not in {
                                "collector_command_unsupported", "collector_permission_denied"
                            }:
                                raise
                            unavailable[command] = str(error)
                finally:
                    process.close()
    except TimeoutError:
        raise ConnectionPolicyError("collector_timeout") from None
    authorize()
    target_allowed(store, device)
    try:
        snapshot = parse_snapshot(device, outputs, unavailable, observed_at=observed_at)
    except (ValidationError, ValueError, OverflowError):
        raise ConnectionPolicyError("collector_parse_failed") from None
    with store.engine.begin() as connection:
        current = ManagedDevice.model_validate(connection.execute(sa.select(store.devices.c.payload)
            .where(store.devices.c.id == device.id).with_for_update()).scalar_one())
        if (current.collector, current.ssh_profile) != (device.collector, device.ssh_profile):
            raise ConnectionPolicyError("device_connection_changed")
        if current.inventory_observed_at and current.inventory_observed_at > started_at:
            raise ConnectionPolicyError("out_of_order_inventory")
        try:
            updated, batch = merge_snapshot(current, snapshot)
        except (ValidationError, ValueError, OverflowError):
            raise ConnectionPolicyError("collector_parse_failed") from None
        store.save_device(updated, connection)
    return updated, batch


def canonical(name):
    value = re.sub(r"\s+", "", name)
    prefixes = (
        ("Te", "TenGigabitEthernet"), ("Gi", "GigabitEthernet"),
        ("Fa", "FastEthernet"), ("Eth", "Ethernet"), ("Et", "Ethernet"),
        ("Vl", "Vlan"), ("Po", "Port-channel"), ("Lo", "Loopback"),
    )
    for short, full in prefixes:
        if re.match(re.escape(short) + r"(?=\d)", value, re.I):
            value = full + value[len(short):]
            break
    return value.lower()


def interface_kind(name):
    value = canonical(name)
    if "." in value:
        return "subinterface"
    if value.startswith("vlan"):
        return "svi"
    if value.startswith("port-channel"):
        return "port_channel"
    if value.startswith("loopback"):
        return "loopback"
    # Catalyst's out-of-band Fa0 has no slash and is not a front-panel port.
    if value == "fastethernet0" or value.startswith(("mgmt", "management")):
        return "management"
    if re.match(r"(?:fastethernet|gigabitethernet|tengigabitethernet|ethernet)\d+(?:/\d+)+$", value):
        return "ethernet"
    return None


def integer(pattern, text):
    match = re.search(pattern, text, re.I | re.M)
    return int(match.group(1).replace(",", "")) if match else None


def parse_speed(value):
    token = value.strip().lower().removeprefix("a-")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([gmt]?)", token)
    if not match:
        return None
    number = float(match.group(1))
    scale = {"": 1, "m": 1, "g": 1000, "t": 1_000_000}[match.group(2)]
    result = number * scale
    return int(result) if result > 0 else None


def connector_kind(media):
    value = media.strip().lower()
    if not value or value in {"unknown", "not present", "n/a", "--"}:
        return "unknown"
    if "qsfp" in value:
        return "qsfp"
    # The socket is SFP even when its removable module terminates copper.
    if "sfp" in value:
        return "sfp"
    if re.search(r"(?:base-?t\b|baset\b|10/100|100/1000)", value):
        return "rj45"
    if re.search(r"base-?(?:sx|lx|ex|zx|sr|lr|er)\b", value):
        return "sfp"
    return "unknown"


def parse_interfaces(raw):
    headers = list(INTERFACE_HEADER.finditer(raw))
    if not headers or len(headers) > 8192:
        raise ConnectionPolicyError("collector_parse_failed")
    entries = {}
    for index, header in enumerate(headers):
        name = header.group(1).strip()
        kind = interface_kind(name)
        if kind is None:
            continue
        admin_state, protocol = header.group(2).strip().lower(), header.group(3).strip().lower()
        text = raw[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(raw)]
        admin = False if "administratively down" in admin_state else True if admin_state in {"up", "down", "reset"} else None
        oper = True if protocol == "up" else False if protocol == "down" else None
        hardware_absent = bool(re.search(r"^\s*Hardware is not present\s*$", text, re.I | re.M))
        if hardware_absent and oper is not False:
            raise ConnectionPolicyError("collector_parse_failed")
        speed_match = re.search(r"\b(?:a-)?(\d+(?:\.\d+)?)([GM]?)b/s\b", text, re.I)
        speed = parse_speed("".join(speed_match.groups())) if speed_match else None
        duplex_match = re.search(r"\b(?:a-)?(full|half)-duplex\b", text, re.I)
        description = re.search(r"^\s*Description:\s*([^\n]*)", text, re.I | re.M)
        intervals = []
        sample = {
            "admin_up": admin, "oper_up": oper,
            "capacity_bps": speed * 1_000_000 if speed else None,
            "duplex": duplex_match.group(1).lower() if duplex_match else "unknown",
            "in_octets": integer(r"\b\d+[\d,]*\s+packets input,\s*([\d,]+)\s+bytes", text),
            "out_octets": integer(r"\b\d+[\d,]*\s+packets output,\s*([\d,]+)\s+bytes", text),
            "errors": integer(r"^\s*([\d,]+)\s+input errors\b", text),
            "tx_errors": integer(r"^\s*([\d,]+)\s+output errors\b", text),
            "tx_discards": integer(r"^\s*Total output drops:\s*([\d,]+)", text),
            "vrf_known": False,
            "counter_epoch_known": False,
        }
        for direction, field in (("input", "rx_bps"), ("output", "tx_bps")):
            rate = re.search(r"(\d+)\s+minute\s+" + direction + r" rate\s+([\d,]+)\s+bits/sec", text, re.I)
            if rate:
                intervals.append(int(rate.group(1)) * 60)
                sample[field] = int(rate.group(2).replace(",", ""))
        sample["rate_interval_seconds"] = intervals[0] if len(intervals) == 2 and len(set(intervals)) == 1 else None
        key = canonical(name)
        if key in entries:
            raise ConnectionPolicyError("collector_parse_failed")
        entries[key] = {
            "name": name, "kind": kind, "speed": speed, "connector": "unknown",
            "description": description.group(1).strip()[:500] if description else None,
            "physical": False, "hardware_absent": hardware_absent, "sample": sample,
        }
    if not entries:
        raise ConnectionPolicyError("collector_parse_failed")
    return entries


def apply_status(entries, raw):
    header = next((line for line in raw.splitlines()
                   if re.search(r"\bPort\b.*\bName\b.*\bStatus\b.*\bVlan\b.*\bDuplex\b.*\bSpeed\b.*\bType\b", line, re.I)), None)
    if not header:
        raise ConnectionPolicyError("collector_parse_failed")
    labels = ("Port", "Name", "Status", "Vlan", "Duplex", "Speed", "Type")
    starts = [header.lower().find(label.lower()) for label in labels]
    if starts != sorted(starts) or any(value < 0 for value in starts):
        raise ConnectionPolicyError("collector_parse_failed")
    matched = set()
    for line in raw.splitlines()[raw.splitlines().index(header) + 1:]:
        if not line.strip() or re.match(r"^\s*-{3,}", line):
            continue
        values = [line[starts[index]:starts[index + 1]].strip() for index in range(len(starts) - 1)]
        values.append(line[starts[-1]:].strip())
        port, description, status, vlan, duplex, speed_token, media = values
        key = canonical(port)
        row = entries.get(key)
        if not row or key in matched:
            # A partially parsed table must not replace complete port inventory.
            raise ConnectionPolicyError("collector_parse_failed")
        matched.add(key)
        if row["kind"] not in {"ethernet", "management"}:
            continue
        if not all((status, vlan, duplex, speed_token, media)):
            raise ConnectionPolicyError("collector_parse_failed")
        if row.get("hardware_absent"):
            # Conflicting hardware evidence must not create a physical socket.
            raise ConnectionPolicyError("collector_parse_failed")
        state = status.lower()
        if state == "connected":
            row["sample"].update(admin_up=True, oper_up=True)
        elif state == "disabled":
            row["sample"].update(admin_up=False, oper_up=False)
        elif state in {"notconnect", "err-disabled", "inactive", "suspended", "monitoring"}:
            row["sample"].update(admin_up=True, oper_up=False)
        parsed_speed = parse_speed(speed_token)
        if parsed_speed:
            row["speed"] = parsed_speed
            row["sample"]["capacity_bps"] = parsed_speed * 1_000_000
        normalized_duplex = duplex.lower().removeprefix("a-")
        if normalized_duplex in {"full", "half"}:
            row["sample"]["duplex"] = normalized_duplex
        if vlan.isdigit() and 1 <= int(vlan) <= 4094:
            row["sample"].update(pvid=int(vlan), access_vlan=int(vlan), vlan_mode="access")
        elif vlan.lower() == "trunk":
            row["sample"]["vlan_mode"] = "trunk"
        row.update(connector=connector_kind(media), physical=row["kind"] == "ethernet",
                   description=(description or row["description"]))
        row["sample"]["transceiver_media"] = media[:160] if "sfp" in media.lower() else None
    physical = {key for key in matched if entries[key]["kind"] == "ethernet"}
    # IOS may list inactive hardware personalities in `show interfaces` only.
    # Exempt them solely on explicit device evidence, never model/port numbers
    # or a down link. Ordinary missing rows still reject the entire snapshot.
    expected = {key for key, row in entries.items()
                if row["kind"] == "ethernet" and not row.get("hardware_absent")}
    if not physical or physical != expected:
        raise ConnectionPolicyError("collector_parse_failed")


def apply_addresses(entries, raw, warnings):
    headers = list(INTERFACE_HEADER.finditer(raw))
    if not headers:
        warnings.append("show ip interface: çıktı biçimi tanınmadı.")
        return
    for index, header in enumerate(headers):
        row = entries.get(canonical(header.group(1)))
        if not row:
            continue
        text = raw[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(raw)]
        addresses = []
        for value in re.findall(r"^\s*Internet address is\s+(\S+)", text, re.I | re.M):
            try:
                addresses.append(str(ip_interface(value)))
            except ValueError:
                warnings.append(f"show ip interface: {row['name']} adresi tanınmadı.")
        if addresses:
            row["sample"]["addresses"] = sorted(set(addresses))
            svi = re.fullmatch(r"Vlan(\d+)", row["name"], re.I)
            if svi and 1 <= int(svi.group(1)) <= 4094:
                row["sample"]["l3_vlan"] = int(svi.group(1))


def parse_snapshot(device, outputs, unavailable=None, observed_at=None):
    version = outputs.get("show version", "")
    models = re.findall(r"\bWS-C2960X-[A-Z0-9-]+\b", version, re.I)
    if not re.search(r"Cisco IOS Software", version, re.I) or not models:
        raise ConnectionPolicyError("collector_not_cisco_2960x")
    release = re.search(r"Cisco IOS Software[^\n]*\bVersion\s+([^,\s]+)", version, re.I)
    serial = re.search(r"(?:System serial number\s*:|Processor board ID)\s*(\S+)", version, re.I)
    uptime_line = re.search(r"^\S+\s+uptime is\s+([^\n]+)", version, re.I | re.M)
    uptime = None
    if uptime_line:
        units = {"year": 31536000, "week": 604800, "day": 86400, "hour": 3600, "minute": 60, "second": 1}
        parts = re.findall(r"(\d+)\s+(year|week|day|hour|minute|second)s?", uptime_line.group(1), re.I)
        if parts:
            uptime = sum(int(number) * units[unit.lower()] for number, unit in parts)
    entries = parse_interfaces(outputs.get("show interfaces", ""))
    apply_status(entries, outputs.get("show interfaces status", ""))
    warnings = [f"{command}: okunamadı ({code})." for command, code in (unavailable or {}).items()]
    if "show ip interface" in outputs:
        apply_addresses(entries, outputs["show ip interface"], warnings)
    return {
        "at": observed_at or now(), "entries": entries, "model": models[0].upper(),
        "release": release.group(1)[:160] if release else device.os_version,
        "serial": serial.group(1)[:160] if serial else device.serial,
        "health": Health(uptime_seconds=uptime, alerts=warnings),
        "outputs": outputs, "unavailable": unavailable or {},
    }


def merge_snapshot(device, snapshot):
    at, entries = snapshot["at"], snapshot["entries"]
    existing = {canonical(interface.name): interface for interface in device.interfaces}
    if len(existing) != len(device.interfaces):
        raise ConnectionPolicyError("collector_parse_failed")
    interfaces, samples, ports, bindings = [], [], [], []
    chassis_id = f"{device.id}:cisco-ios:chassis"

    def observation(value):
        return Observation(value=value, observed_at=at, stale_after_seconds=120, source="ssh",
                           quality="ok" if value is not None else "unknown")

    for ordinal, (key, row) in enumerate(entries.items(), 1):
        previous = existing.get(key)
        identifier = previous.id if previous else f"{device.id}:cisco-ios:if:{sha256(key.encode()).hexdigest()[:20]}"
        sample = InterfaceSample(interface_id=identifier, **row["sample"])
        interfaces.append(Interface(
            id=identifier, name=row["name"], kind=row["kind"],
            if_index=previous.if_index if previous else None,
            admin_up=observation(sample.admin_up), oper_up=observation(sample.oper_up),
            speed_mbps=observation(row["speed"]), access_vlan=observation(sample.access_vlan),
        ))
        samples.append(sample)
        if row["physical"]:
            port_id = f"{device.id}:cisco-ios:port:{sha256(key.encode()).hexdigest()[:20]}"
            group, label = row["name"].rsplit("/", 1)
            ports.append(PhysicalPort(
                id=port_id, component_id=chassis_id, label=label, connector=row["connector"],
                group=group, ordinal=len(ports) + 1, description=row["description"],
            ))
            bindings.append(PortBinding(
                id=port_id + ":binding", physical_port_id=port_id,
                interface_id=identifier, binding_quality="explicit",
            ))
    if not ports:
        raise ConnectionPolicyError("collector_parse_failed")
    own_geometry = not device.physical_ports or all(
        port.id.startswith(f"{device.id}:cisco-ios:port:") for port in device.physical_ports
    )
    updates = {
        "interfaces": interfaces, "vendor": "Cisco", "model": snapshot["model"],
        "os_version": snapshot["release"], "serial": snapshot["serial"],
    }
    if own_geometry:
        updates.update(
            physical_ports=ports, bindings=bindings,
            components=[PhysicalComponent(id=chassis_id, kind="chassis", label=snapshot["model"])],
            inventory_source="ssh", inventory_observed_at=at,
        )
    else:
        interface_ids = {interface.id for interface in interfaces}
        updates["bindings"] = [binding for binding in device.bindings if binding.interface_id in interface_ids]
    endpoints = parse_endpoints(interfaces, snapshot["outputs"], snapshot["unavailable"], samples)
    if endpoints.status in {"partial", "error"}:
        snapshot["health"].alerts.append("MAC/ARP gözlemleri eksik; fiziksel bağlantı kanıtı değildir.")
    return device.model_copy(update=updates), Telemetry(
        observed_at=at, source="ssh", reachability="reachable", interfaces=samples,
        health=snapshot["health"], endpoints=endpoints,
    )


def normalize_mac(value):
    digits = value.replace(".", "").lower()
    return ":".join(digits[index:index + 2] for index in range(0, 12, 2))


def parse_endpoints(interfaces, outputs, unavailable, samples=()):
    names = {canonical(interface.name): interface.id for interface in interfaces}
    fdb_raw, arp_raw = outputs.get("show mac address-table"), outputs.get("show arp")
    recognized_fdb = fdb_raw is not None and bool(re.search(r"Mac Address Table|Vlan\s+Mac Address\s+Type\s+Ports", fdb_raw, re.I))
    recognized_arp = arp_raw is not None and bool(re.search(r"Protocol\s+Address\s+Age.*Hardware Addr\s+Type\s+Interface", arp_raw, re.I))
    if not (recognized_fdb or recognized_arp):
        unsupported = all(unavailable.get(command) == "collector_command_unsupported"
                          for command in ("show mac address-table", "show arp"))
        return EndpointCollection(status="unsupported" if unsupported else "error")
    arp_by_scope, partial = {}, not (recognized_fdb and recognized_arp)
    local_addresses = {str(ip_interface(address).ip) for sample in samples for address in sample.addresses}
    if recognized_arp:
        for row_number, line in enumerate(arp_raw.splitlines()):
            if row_number >= 16384:
                partial = True
                break
            match = re.match(r"\s*Internet\s+(\d+(?:\.\d+){3})\s+(?:\S+)\s+(" + MAC + r")\s+ARPA\s+(\S+)\s*$", line, re.I)
            if not match:
                if re.match(r"\s*Internet\s+\d", line, re.I):
                    partial = True
                continue
            address, mac, interface = match.groups()
            if address in local_addresses:
                continue
            scope = arp_by_scope.setdefault((normalize_mac(mac), canonical(interface)), set())
            if len(scope) < 32:
                scope.add(address)
            else:
                partial = True
    entries = {}
    if recognized_fdb:
        for line in fdb_raw.splitlines():
            match = re.match(r"\s*(?:\*\s*)?(\d+)\s+(" + MAC + r")\s+(DYNAMIC|STATIC)\s+(\S+)\s*$", line, re.I)
            if not match:
                continue
            vlan, mac, kind, interface = match.groups()
            key, vlan_number, mac = canonical(interface), int(vlan), normalize_mac(mac)
            if key not in names or not 1 <= vlan_number <= 4094:
                partial = True
                continue
            addresses = sorted(arp_by_scope.get((mac, canonical(f"Vlan{vlan_number}")), set())
                               | arp_by_scope.get((mac, key), set()))[:32]
            identifier = sha256(f"{names[key]}|{mac}|{vlan_number}".encode()).hexdigest()[:32]
            try:
                entries[identifier] = EndpointObservation(
                    id=identifier, interface_id=names[key], mac=mac, addresses=addresses,
                    vlan=vlan_number, discovery="fdb", state="static" if kind.upper() == "STATIC" else "unknown",
                    vrf_known=bool(addresses),
                    evidence="show mac address-table" + (" + same-interface/VLAN show arp correlation" if addresses else ""),
                )
            except ValidationError:
                partial = True
                continue
            if len(entries) >= 2048:
                partial = True
                break
    # Preserve ARP-only rows (e.g. a gateway with no local FDB entry). These
    # observations can resolve an adjacent switch's FDB, but are not cables.
    for (mac, key), addresses in arp_by_scope.items():
        if key not in names:
            partial = True
            continue
        vlan = re.fullmatch(r"vlan(\d+)", key)
        vlan_number = int(vlan[1]) if vlan else None
        if any(e.mac == mac and e.vlan == vlan_number and set(addresses) <= set(e.addresses) for e in entries.values()):
            continue
        if len(entries) >= 2048:
            partial = True
            break
        identifier = sha256(f"arp|{names[key]}|{mac}".encode()).hexdigest()[:32]
        try:
            entries[identifier] = EndpointObservation(id=identifier, interface_id=names[key], mac=mac,
                addresses=sorted(addresses), vlan=vlan_number, vrf_known=True, discovery="arp",
                evidence="show arp; default VRF, L3 observation, not a physical cable")
        except ValidationError:
            partial = True
    return EndpointCollection(status="partial" if partial else "ok", entries=list(entries.values()),
                              truncated=len(entries) >= 2048, total_count=None if partial else len(entries))
