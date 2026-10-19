"""Bounded, read-only Huawei VRP CLI collection (including VRP 5.120).

Only parsed device observations enter persistence. No configuration commands,
model-derived socket counts, inferred cables, or raw CLI logging. See
docs/huawei-vrp.md for the command/measurement contract and limitations.
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

COMMANDS = ("display version", "display interface", "display ip interface brief",
            "display mac-address", "display arp all", "display cpu-usage", "display memory-usage")
MAX_OUTPUT = 2_000_000
COMMAND_TIMEOUT = 20
SESSION_TIMEOUT = 120
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
MORE = re.compile(r"[ \t]*-{2,}[ \t]*More[ \t]*-{2,}[ \t]*", re.I)
HEADER = re.compile(r"^\s*([A-Za-z][A-Za-z-]*\s*\d[\w/.:\-]*)\s+current state\s*:\s*([^\n]+)", re.M | re.I)
MAC = r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"


def clean(raw):
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", ANSI.sub("", raw).replace("\r\n", "\n"))


class VRPReader:
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
                match = re.search(r"(?:^|\n)(<[^<>\n]{1,80}>)\s*$", output)
            else:
                match = re.search(r"(?:^|\n)" + re.escape(self.prompt) + r"\s*$", output)
            if match:
                if self.prompt is None:
                    self.prompt = match.group(1)
                return MORE.sub("", output[:match.start()])
            page_count = len(MORE.findall(output))
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
        if re.search(r"(?:permission denied|no permission|insufficient privilege|not authorized)", output, re.I):
            raise ConnectionPolicyError("collector_permission_denied")
        if re.search(r"^\s*(?:Error\s*:|%\s*Error\b|Unrecognized command|Incomplete command|Wrong parameter)", output, re.I | re.M):
            raise ConnectionPolicyError("collector_command_unsupported")
        return output


async def collect_huawei(store, vault, device, authorize=lambda: None):
    outputs, unavailable = {}, {}
    observed_at = None
    started_at = now()
    try:
        async with asyncio.timeout(SESSION_TIMEOUT):
            async with connect(store, vault, device) as connection:
                authorize()
                process = await connection.create_process(term_type="vt100", term_size=(200, 48))
                reader = VRPReader(process)
                try:
                    await asyncio.wait_for(reader.read_prompt(), COMMAND_TIMEOUT)
                    for command in COMMANDS:
                        authorize()
                        try:
                            outputs[command] = await reader.command(command)
                            if command == "display interface":
                                observed_at = now()
                        except ConnectionPolicyError as error:
                            # Continuing after a timeout/EOF would mix responses.
                            if command in COMMANDS[:2] or str(error) not in {"collector_command_unsupported", "collector_permission_denied"}:
                                raise
                            unavailable[command] = str(error)
                finally:
                    process.close()
    except TimeoutError:
        raise ConnectionPolicyError("collector_timeout") from None
    authorize()
    target_allowed(store, device)
    # Parse before opening a transaction, then merge against the locked inventory.
    try:
        snapshot = parse_snapshot(device, outputs, unavailable, observed_at=observed_at)
    except (ValidationError, ValueError, OverflowError):
        raise ConnectionPolicyError("collector_parse_failed") from None
    with store.engine.begin() as conn:
        current = ManagedDevice.model_validate(conn.execute(sa.select(store.devices.c.payload)
            .where(store.devices.c.id == device.id).with_for_update()).scalar_one())
        if (current.collector, current.ssh_profile) != (device.collector, device.ssh_profile):
            raise ConnectionPolicyError("device_connection_changed")
        if current.inventory_observed_at and current.inventory_observed_at > started_at:
            raise ConnectionPolicyError("out_of_order_inventory")
        try:
            updated, batch = merge_snapshot(current, snapshot)
        except (ValidationError, ValueError, OverflowError):
            raise ConnectionPolicyError("collector_parse_failed") from None
        store.save_device(updated, conn)
    return updated, batch


def canonical(name):
    name = re.sub(r"\s+", "", name)
    for short, full in (("XGE", "XGigabitEthernet"), ("GE", "GigabitEthernet"), ("Eth", "Ethernet")):
        if re.match(short + r"\d", name, re.I):
            name = full + name[len(short):]
            break
    return name.lower()


def match_value(pattern, text, cast=int):
    match = re.search(pattern, text, re.I | re.M)
    return cast(match.group(1)) if match else None


def interface_kind(name):
    value = canonical(name)
    if "." in value:
        return "subinterface"
    if value.startswith("vlanif"):
        return "svi"
    if value.startswith(("eth-trunk", "trunk")):
        return "port_channel"
    if value.startswith("loopback"):
        return "loopback"
    if value.startswith("meth"):
        return "management"
    if re.match(r"(?:gigabitethernet|xgigabitethernet|ethernet|10ge|25ge|40ge|100ge)\d+/\d+/\d+$", value):
        return "ethernet"
    return None  # NULL/tunnel/unknown types are not physical sockets.


def connector_kind(name, text):
    """Classify only connector families evidenced by the interface output.

    Huawei reports the active medium separately from module presence. GE,
    XGE/10GE and 25GE optical interfaces use the small-form-factor cage family
    represented by ``sfp`` in our inventory contract (SFP/SFP+/SFP28). Faster
    optical interfaces remain unknown unless the CLI explicitly names QSFP.
    """
    if re.search(r"\bPort Mode\s*:\s*(?:COMMON|FORCE)\s+COPPER\b", text, re.I):
        return "rj45"
    upper = text.upper()
    if re.search(r"(?:^|[^A-Z0-9])QSFP(?:\+|28|DD)?(?:[^A-Z0-9]|$)", upper):
        return "qsfp"
    if re.search(r"(?:^|[^A-Z0-9Q])SFP(?:\+|28)?(?:[^A-Z0-9]|$)", upper):
        return "sfp"
    if not re.search(r"\bPort Mode\s*:\s*(?:COMMON|FORCE)\s+FIBER\b", text, re.I):
        return "unknown"
    value = canonical(name)
    if re.match(r"(?:gigabitethernet|xgigabitethernet|10ge|25ge)\d+/\d+/\d+$", value):
        return "sfp"
    return "unknown"


def parse_interfaces(raw):
    headers = list(HEADER.finditer(raw))
    if not headers or len(headers) > 8192:
        raise ConnectionPolicyError("collector_parse_failed")
    entries = {}
    for index, header in enumerate(headers):
        name, state = re.sub(r"\s+", "", header.group(1)), header.group(2).strip().upper()
        if len(name) > 160:
            raise ConnectionPolicyError("collector_parse_failed")
        kind = interface_kind(name)
        if kind is None:
            continue
        text = raw[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(raw)]
        admin = False if "ADMINISTRATIVELY DOWN" in state else True if state in {"UP", "DOWN"} else None
        oper = True if state == "UP" else False if "DOWN" in state else None
        speed = match_value(r"\bSpeed\s*:\s*(\d+)\b", text)
        speed = speed if speed and speed > 0 else None
        vlan = match_value(r"\bPVID\s*:\s*(\d+)", text)
        vlan = vlan if vlan and 1 <= vlan <= 4094 else None
        mode = match_value(r"\bLink-type\s*:\s*(access|trunk)\b", text, str)
        duplex = match_value(r"\bDuplex\s*:\s*(FULL|HALF)\b", text, str)
        connector = connector_kind(name, text)
        description = match_value(r"^\s*Description\s*:[ \t]*([^\n]*)", text, str)
        sample = {"admin_up": admin, "oper_up": oper, "capacity_bps": speed * 1_000_000 if speed else None,
                  "duplex": duplex.lower() if duplex else "unknown", "pvid": vlan,
                  "vrf_known": False,
                  "access_vlan": vlan if mode and mode.lower() == "access" else None,
                  "vlan_mode": mode.lower() if mode else "unknown"}
        # Rates are the device-reported averaging window, NOT instantaneous values.
        intervals = []
        for direction, prefix in (("Input", "rx"), ("Output", "tx")):
            section = re.search(r"^\s*" + direction + r"\s*:\s*([^\n]*)(.*?)(?=^\s*(?:Input|Output)\s*:|\Z)", text, re.I | re.M | re.S)
            octets = match_value(r"(\d+)\s+bytes\b", section.group(1)) if section else None
            sample["in_octets" if prefix == "rx" else "out_octets"] = octets
            if section:
                sample[prefix + "_errors"] = match_value(r"Total Error\s*:\s*(\d+)", section.group(2))
                sample[prefix + "_discards"] = match_value(r"Discard\s*:\s*(\d+)", section.group(2))
            rate = re.search(r"Last\s+(\d+)\s+seconds\s+" + direction + r"\s+rate\s+(\d+)\s+bits/sec", text, re.I)
            if rate and int(rate.group(1)) > 0:
                sample[prefix + "_bps"] = int(rate.group(2))
                intervals.append(int(rate.group(1)))
        sample["rate_interval_seconds"] = intervals[0] if len(intervals) == 2 and len(set(intervals)) == 1 else None
        for metric in ("errors", "discards"):
            sample[metric] = sample.pop("rx_" + metric, None)
        # Without validated rate text, do not derive counters across unknown reboot/reset epochs.
        sample["counter_epoch_known"] = False
        key = canonical(name)
        if key in entries:
            raise ConnectionPolicyError("collector_parse_failed")
        entries[key] = {"name": name, "kind": kind, "speed": speed, "connector": connector,
                        "description": description[:500] if description else None, "sample": sample}
    if not entries:
        raise ConnectionPolicyError("collector_parse_failed")
    return entries


def parse_snapshot(device, outputs, unavailable=None, observed_at=None):
    version = outputs.get("display version", "")
    if "Huawei Versatile Routing Platform" not in version and not re.search(r"VRP\s*\(R\)", version, re.I):
        raise ConnectionPolicyError("collector_not_huawei_vrp")
    release = match_value(r"VRP\s*\(R\)\s*software,\s*Version\s+([^\n]+)", version, str)
    uptime_line = match_value(r"^[^\n]*\buptime is\s+([^\n]+)", version, str)
    uptime = None
    if uptime_line:
        units = {"week": 604800, "day": 86400, "hour": 3600, "minute": 60, "second": 1}
        parts = re.findall(r"(\d+)\s+(week|day|hour|minute|second)s?", uptime_line)
        if parts:
            uptime = sum(int(n) * units[unit] for n, unit in parts)
    entries = parse_interfaces(outputs.get("display interface", ""))
    warnings = [f"{command}: okunamadı ({code})." for command, code in (unavailable or {}).items()]
    ip_raw = outputs.get("display ip interface brief")
    if ip_raw is not None:
        if not re.search(r"IP Address/Mask", ip_raw, re.I):
            warnings.append("display ip interface brief: çıktı biçimi tanınmadı.")
        else:
            for line in ip_raw.splitlines():
                fields = line.split()
                if len(fields) < 2 or canonical(fields[0]) not in entries or "/" not in fields[1]:
                    continue
                try:
                    address = str(ip_interface(fields[1]))
                except ValueError:
                    continue
                entries[canonical(fields[0])]["sample"]["addresses"] = [address]
    cpu = match_value(r"CPU (?:usage|utilization)\s*(?:for five seconds)?\s*:\s*(\d+(?:\.\d+)?)%", outputs.get("display cpu-usage", ""), float)
    memory = match_value(r"Memory Using Percentage Is\s*:\s*(\d+(?:\.\d+)?)%", outputs.get("display memory-usage", ""), float)
    for command, value in (("display cpu-usage", cpu), ("display memory-usage", memory)):
        if command in outputs and (value is None or not 0 <= value <= 100):
            warnings.append(f"{command}: ölçüm biçimi tanınmadı.")
    return {"at": observed_at or now(), "entries": entries, "release": release[:160] if release else device.os_version,
            "health": Health(uptime_seconds=uptime, cpu_percent=cpu if cpu is not None and 0 <= cpu <= 100 else None,
                             memory_percent=memory if memory is not None and 0 <= memory <= 100 else None, alerts=warnings),
            "outputs": outputs, "unavailable": unavailable or {}}


def merge_snapshot(device, snapshot):
    at, entries = snapshot["at"], snapshot["entries"]
    existing = {canonical(i.name): i for i in device.interfaces}
    if len(existing) != len(device.interfaces):
        raise ConnectionPolicyError("collector_parse_failed")
    interfaces, samples, ports, bindings = [], [], [], []
    chassis_id = f"{device.id}:vrp:chassis"
    for ordinal, (key, row) in enumerate(entries.items(), 1):
        previous = existing.get(key)
        identifier = previous.id if previous else f"{device.id}:vrp:if:{sha256(key.encode()).hexdigest()[:20]}"
        def obs(value):
            return Observation(value=value, observed_at=at, stale_after_seconds=120, source="ssh", quality="ok" if value is not None else "unknown")
        sample = InterfaceSample(interface_id=identifier, **row["sample"])
        interfaces.append(Interface(id=identifier, name=row["name"], kind=row["kind"],
            if_index=previous.if_index if previous else None, admin_up=obs(sample.admin_up), oper_up=obs(sample.oper_up),
            speed_mbps=obs(row["speed"]), access_vlan=obs(sample.access_vlan)))
        samples.append(sample)
        if row["kind"] == "ethernet":
            port_id = f"{device.id}:vrp:port:{sha256(key.encode()).hexdigest()[:20]}"
            group, label = row["name"].rsplit("/", 1)
            ports.append(PhysicalPort(id=port_id, component_id=chassis_id, label=label, connector=row["connector"],
                group=group, ordinal=ordinal, description=row["description"]))
            bindings.append(PortBinding(id=port_id + ":binding", physical_port_id=port_id, interface_id=identifier, binding_quality="explicit"))
    own_geometry = not device.physical_ports or all(p.id.startswith(f"{device.id}:vrp:port:") for p in device.physical_ports)
    updates = {"interfaces": interfaces, "os_version": snapshot["release"]}
    if own_geometry:
        updates.update(physical_ports=ports, bindings=bindings,
            components=[PhysicalComponent(id=chassis_id, kind="chassis", label="Şematik cihaz")],
            inventory_source="ssh", inventory_observed_at=at)
    else:
        # Never relabel imported geometry as freshly discovered/verified.
        ids = {i.id for i in interfaces}
        updates["bindings"] = [b for b in device.bindings if b.interface_id in ids]
    endpoints = parse_endpoints(interfaces, snapshot["outputs"], snapshot["unavailable"])
    if endpoints.status in {"partial", "error"}:
        snapshot["health"].alerts.append("MAC/ARP gözlemleri eksik; fiziksel bağlantı kanıtı değildir.")
    return device.model_copy(update=updates), Telemetry(observed_at=at, source="ssh", reachability="reachable",
        interfaces=samples, health=snapshot["health"], endpoints=endpoints)


def parse_endpoints(interfaces, outputs, unavailable):
    names = {canonical(i.name): i.id for i in interfaces}
    fdb_raw, arp_raw = outputs.get("display mac-address"), outputs.get("display arp all")
    recognized_fdb = fdb_raw is not None and bool(re.search(r"MAC Address\s+VLAN|Total (?:items|MAC)|no mac address", fdb_raw, re.I))
    recognized_arp = arp_raw is not None and bool(re.search(r"IP ADDRESS\s+MAC ADDRESS|Total\s*:\s*\d+", arp_raw, re.I))
    entries, arp, arp_scopes, partial = {}, [], {}, not (recognized_fdb and recognized_arp)
    arp_vrf_column = bool(re.search(r"VPN[- ]INSTANCE", arp_raw or "", re.I))
    if not (recognized_fdb or recognized_arp):
        unsupported = all(unavailable.get(command) == "collector_command_unsupported" for command in ("display mac-address", "display arp all"))
        return EndpointCollection(status="unsupported" if unsupported else "error")
    def mac_address(value):
        digits = value.replace("-", "").lower()
        return ":".join(digits[n:n + 2] for n in range(0, 12, 2))
    if recognized_arp:
        for row_number, line in enumerate(arp_raw.splitlines()):
            if row_number >= 16384:
                partial = True
                break
            match = re.match(r"\s*(\d+(?:\.\d+){3})\s+(" + MAC + r")\s+(.*?)\s+((?:GigabitEthernet|XGigabitEthernet|Ethernet|GE|XGE|Eth-Trunk|Vlanif|MEth|LoopBack|10GE|25GE|40GE|100GE)\s*\d[\w/.]*)(?:\s+(.*))?$", line, re.I)
            if not match:
                if re.match(r"\s*\d+(?:\.\d+){3}\s", line):
                    partial = True
                continue
            address, mac, flags, interface, vrf = match.groups()
            if re.search(r"\bI\b", flags):
                continue  # local interface address, not an attached endpoint
            if canonical(interface) not in names:
                partial = True
                continue
            key, mac, vrf = canonical(interface), mac_address(mac), (vrf or "").strip()
            arp.append((address, mac, key, vrf, "static" if re.search(r"\bS\b", flags) else "unknown"))
            if arp_vrf_column and vrf in {"", "-"}:
                scope = arp_scopes.setdefault((mac, key), set())
                if len(scope) < 32:
                    scope.add(address)
                else:
                    partial = True
    if recognized_fdb:
        for line in fdb_raw.splitlines():
            match = re.match(r"\s*(" + MAC + r")\s+(\d+)(?:/\S*)?\s+([A-Za-z][\w-]*\s*\d[\w/.]*)\s+(dynamic|static|security|sticky)\b", line, re.I)
            if not match:
                if re.match(r"\s*" + MAC, line):
                    partial = True
                continue
            mac, vlan, interface, kind = match.groups()
            key, mac, vlan = canonical(interface), mac_address(mac), int(vlan)
            if key not in names:
                partial = True
                continue
            # Correlate only the SAME interface, or a default-VRF VLANIF with
            # the explicit FDB VLAN. Never join a MAC across unrelated VRFs/VLANs.
            addresses = sorted(arp_scopes.get((mac, key), set()) | arp_scopes.get((mac, f"vlanif{vlan}"), set()))
            if len(addresses) > 32:
                addresses, partial = addresses[:32], True
            identifier = sha256(f"fdb|{names[key]}|{mac}|{vlan}".encode()).hexdigest()[:32]
            try:
                entries[identifier] = EndpointObservation(id=identifier, interface_id=names[key], mac=mac, vlan=vlan,
                    addresses=addresses, discovery="fdb", state="static" if kind.lower() == "static" else "unknown",
                    evidence="display mac-address" + (" + display arp all (aynı arayüz/VLAN, varsayılan VRF)" if addresses else ""))
            except ValidationError:
                partial = True
            if len(entries) >= 2048:
                partial = True
                break
    for address, mac, key, vrf, state in arp:
        if len(entries) >= 2048:
            partial = True
            break
        if any(e.mac == mac and address in e.addresses for e in entries.values()):
            continue
        identifier = sha256(f"arp|{names[key]}|{mac}|{address}|{vrf}".encode()).hexdigest()[:32]
        try:
            entries[identifier] = EndpointObservation(id=identifier, interface_id=names[key], mac=mac,
                addresses=[address], discovery="arp", state=state, evidence="display arp all; L3 gözlemi, fiziksel kablo kanıtı değil")
        except ValidationError:
            partial = True
    return EndpointCollection(status="partial" if partial else "ok", entries=list(entries.values()))
