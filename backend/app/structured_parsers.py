"""Conservative Junos XML / NX-OS JSON mappings; no model-derived geometry."""
from hashlib import sha256
from ipaddress import ip_interface
import json
import re

from defusedxml import ElementTree as XML
from defusedxml.common import DefusedXmlException

from .collection import ReadResult, metadata
from .contracts import (
    EndpointCollection, EndpointObservation, Health, InterfaceSample, Neighbor,
    Telemetry,
)
from .database import now
from .driver_catalog import DRIVERS
from .models import Interface, Observation, PhysicalComponent, PhysicalPort, PortBinding


def xml(raw):
    start, end = raw.find("<"), raw.rfind(">")
    if start < 0 or end < start:
        raise ValueError("invalid_xml")
    root = XML.fromstring(raw[start:end + 1])
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    if root.find(".//rpc-error") is not None:
        raise ValueError("rpc_error")
    return root


def text(node, path):
    value = node.findtext(path)
    return value.strip() if value is not None else None


def number(value):
    if value is None or value == "":
        return None
    return int(value)


def state(value):
    return {"up": True, "down": False}.get((value or "").lower())


def speed(value):
    if not value:
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kmg]?)(?:bps|b/s|b)?", value.strip(), re.I)
    return float(match[1]) * {"": 1, "k": 1000, "m": 1_000_000, "g": 1_000_000_000}[match[2].lower()] if match else None


def json_rows(value, table):
    if not isinstance(value, dict):
        raise ValueError("invalid_json_object")
    container = value.get("TABLE_" + table)
    if not isinstance(container, dict):
        raise ValueError("table_missing")
    rows = container.get("ROW_" + table)
    if rows is None:
        return []
    return [rows] if isinstance(rows, dict) else rows


def json_rows_any(value, *tables):
    for table in tables:
        try:
            return json_rows(value, table)
        except ValueError:
            continue
    raise ValueError("table_missing")


def first(row, *keys):
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return str(value).strip()
    return None


def junos_interfaces(root):
    if root.tag != "interface-information" and root.find(".//interface-information") is None:
        raise ValueError("interfaces_missing")
    result = []
    for parent in root.findall(".//physical-interface"):
        for node, physical in [(parent, True), *((n, False) for n in parent.findall("logical-interface"))]:
            name = text(node, "name")
            if not name:
                raise ValueError("interface_name_missing")
            kind = "port_channel" if name.startswith(("ae", "reth")) else "loopback" if name.startswith("lo") else "svi" if name.startswith(("irb", "vlan")) else "subinterface" if "." in name else "ethernet"
            sample = dict(admin_up=state(text(node, "admin-status")), oper_up=state(text(node, "oper-status")),
                capacity_bps=speed(text(node, "speed")), vrf_known=False, counter_epoch_known=False,
                in_octets=number(text(node, "traffic-statistics/input-bytes")),
                out_octets=number(text(node, "traffic-statistics/output-bytes")),
                errors=number(text(node, "input-error-list/input-errors")),
                tx_errors=number(text(node, "output-error-list/output-errors")),
                discards=number(text(node, "input-error-list/input-drops")),
                tx_discards=number(text(node, "output-error-list/output-drops")))
            # Device bps averages have no trustworthy sampling window here.
            # Expose counters but do not label them a 30-second rate.
            sample["addresses"] = []
            for family in node.findall("address-family"):
                if text(family, "address-family-name") in {"inet", "inet6"}:
                    for addr in family.findall("interface-address"):
                        local, destination = text(addr, "ifa-local"), text(addr, "ifa-destination")
                        if local and destination and "/" in destination:
                            sample["addresses"].append(str(ip_interface(local.split("/")[0] + "/" + destination.split("/")[-1])))
            result.append({"name": name, "kind": kind, "physical": physical and kind == "ethernet",
                "index": number(text(node, "snmp-index")), "sample": sample})
    if not result or len(result) > 8192:
        raise ValueError("interfaces_empty")
    return result


def nxos_interfaces(root):
    entries = []
    for row in json_rows(root, "interface"):
        name = row["interface"]
        kind = "port_channel" if name.lower().startswith("port-channel") else "svi" if name.lower().startswith("vlan") else "subinterface" if "." in name else "ethernet"
        period = number(row.get("eth_load_interval1_rx"))
        sample = dict(admin_up=state(row.get("admin_state")), oper_up=state(row.get("state")),
            capacity_bps=speed(row.get("eth_speed")), duplex={"full": "full", "half": "half"}.get(row.get("eth_duplex"), "unknown"),
            in_octets=number(row.get("eth_inbytes")), out_octets=number(row.get("eth_outbytes")),
            counter_epoch_known=False, vrf_known=False, errors=number(row.get("eth_inerr")),
            tx_errors=number(row.get("eth_outerr")), discards=number(row.get("eth_indiscard")),
            tx_discards=number(row.get("eth_outdiscard")))
        if period and str(period) == str(row.get("eth_load_interval1_tx")):
            sample.update(rx_bps=number(row.get("eth_inrate1_bits")), tx_bps=number(row.get("eth_outrate1_bits")),
                          rate_interval_seconds=period)
        entries.append({"name": name, "kind": kind, "physical": name.lower().startswith("ethernet") and "." not in name,
                        "index": None, "sample": sample})
    if not entries or len(entries) > 8192:
        raise ValueError("interfaces_empty")
    return entries


def _interface_ids(device):
    from . import cisco
    return {cisco.canonical(interface.name): interface.id for interface in device.interfaces}


def nxos_neighbors(root, device):
    from . import cisco
    names = _interface_ids(device)
    neighbors = []
    for row in json_rows_any(root, "nbor_detail", "nbor", "lldp_neighbor_detail"):
        local = first(row, "l_port_id", "local_port", "intf_id")
        chassis = first(row, "chassis_id", "chassis-id")
        port = first(row, "port_id", "port-id")
        interface_id = names.get(cisco.canonical(local or ""))
        if not interface_id or not chassis or not port:
            raise ValueError("nxos_lldp_identity_missing")
        label = first(row, "sys_name", "system_name", "device_id") or chassis
        neighbors.append(Neighbor(
            id=sha256(f"{interface_id}:{chassis}:{port}".encode()).hexdigest()[:32],
            interface_id=interface_id, label=label[:160], relation="l2",
            evidence=f"NX-OS LLDP chassis={chassis}; port={port}"[:300],
        ))
    if len(neighbors) > 1024:
        raise ValueError("neighbor_limit")
    return neighbors


def nxos_fdb(root, device):
    from . import cisco
    names = _interface_ids(device)
    entries = []
    for row in json_rows_any(root, "mac_address", "mac_address_table"):
        raw_mac = first(row, "disp_mac_addr", "mac_addr", "mac-address")
        raw_vlan = first(row, "disp_vlan", "vlan", "vlan_id")
        raw_port = first(row, "disp_port", "ports", "port")
        if not raw_mac or not raw_vlan or not raw_port:
            raise ValueError("nxos_fdb_row_missing")
        mac = cisco.normalize_mac(raw_mac)
        vlan = int(raw_vlan)
        interface_id = names.get(cisco.canonical(raw_port.split(",", 1)[0]))
        if not mac or not interface_id or not 1 <= vlan <= 4094:
            raise ValueError("nxos_fdb_identity_missing")
        state_value = (first(row, "disp_type", "type", "mac_type") or "").lower()
        entries.append(EndpointObservation(
            id=sha256(f"nxos|{interface_id}|{vlan}|{mac}".encode()).hexdigest()[:32],
            interface_id=interface_id, mac=mac, vlan=vlan, discovery="fdb",
            state="static" if "static" in state_value else "unknown",
            evidence="NX-OS MAC address-table",
        ))
    return EndpointCollection(
        status="ok", entries=entries, total_count=len(entries), source="ssh",
    )


def nxos_inventory(root):
    modules = []
    for row in json_rows_any(root, "inv", "inventory"):
        value = {
            "name": first(row, "name", "inv_name") or "",
            "description": first(row, "desc", "description") or "",
            "part_number": first(row, "productid", "product_id", "pid") or "",
            "serial_number": first(row, "serialnum", "serial_number", "serial") or "",
        }
        if not value["name"] and not value["description"]:
            raise ValueError("nxos_inventory_identity_missing")
        modules.append(value)
    if len(modules) > 256:
        raise ValueError("inventory_limit")
    return modules


def _junos_nodes(root, *names):
    result = []
    for name in names:
        result.extend(root.findall(f".//{name}"))
    return result


def junos_endpoints(fdb_root, arp_root, device):
    from . import cisco
    names = _interface_ids(device)
    by_mac = {}
    if fdb_root is not None:
        for row in _junos_nodes(fdb_root, "l2ng-l2ald-mac-entry-vlan", "mac-table-entry"):
            raw_mac = text(row, "l2ng-l2-mac-address") or text(row, "mac-address")
            raw_interface = text(row, "l2ng-l2-mac-logical-interface") or text(row, "interface-name")
            raw_vlan = text(row, "l2ng-l2-vlan-id") or text(row, "mac-vlan")
            mac = cisco.normalize_mac(raw_mac or "")
            interface_id = names.get(cisco.canonical((raw_interface or "").split(".0", 1)[0]))
            vlan_match = re.search(r"\d+", raw_vlan or "")
            if not mac or not interface_id or not vlan_match:
                raise ValueError("junos_fdb_identity_missing")
            vlan = int(vlan_match.group())
            if not 1 <= vlan <= 4094:
                raise ValueError("junos_vlan_invalid")
            by_mac[mac] = {
                "interface_id": interface_id, "vlan": vlan, "addresses": [],
                "state": "static" if "static" in (text(row, "mac-type") or "").lower() else "unknown",
            }
    if arp_root is not None:
        for row in _junos_nodes(arp_root, "arp-table-entry"):
            raw_mac = text(row, "mac-address")
            address = text(row, "ip-address")
            raw_interface = text(row, "interface-name")
            mac = cisco.normalize_mac(raw_mac or "")
            if not mac or not address:
                raise ValueError("junos_arp_identity_missing")
            value = by_mac.get(mac)
            if value is None:
                interface_id = names.get(cisco.canonical((raw_interface or "").split(".0", 1)[0]))
                if not interface_id:
                    raise ValueError("junos_arp_interface_missing")
                value = by_mac.setdefault(mac, {
                    "interface_id": interface_id, "vlan": None,
                    "addresses": [], "state": "unknown",
                })
            value["addresses"].append(address)
    entries = [EndpointObservation(
        id=sha256(f"junos|{value['interface_id']}|{value['vlan']}|{mac}".encode()).hexdigest()[:32],
        interface_id=value["interface_id"], mac=mac,
        addresses=value["addresses"], vlan=value["vlan"], vrf_known=False,
        discovery="fdb" if value["vlan"] is not None else "arp",
        state=value["state"], evidence="Junos FDB/ARP correlation",
    ) for mac, value in sorted(by_mac.items())]
    if len(entries) > 2048:
        raise ValueError("endpoint_limit")
    return EndpointCollection(
        status="ok", entries=entries, total_count=len(entries), source="ssh",
    )


def junos_environment(root):
    temperatures, fans, power = [], [], []
    for row in _junos_nodes(root, "environment-item"):
        name = text(row, "name") or ""
        item_class = (text(row, "class") or "").lower()
        status_value = text(row, "status") or "unknown"
        temperature = text(row, "temperature")
        if temperature and (match := re.search(r"-?\d+(?:\.\d+)?", temperature)):
            temperatures.append(float(match.group()))
        summary = f"{name}: {status_value}"[:160]
        if "fan" in item_class or "fan" in name.lower():
            fans.append(summary)
        if "power" in item_class or re.search(r"\b(?:pem|psu)\b", name, re.I):
            power.append(summary)
    return Health(
        temperature_c=max(temperatures) if temperatures else None,
        fan="; ".join(fans)[:160] or None,
        power_supply="; ".join(power)[:160] or None,
    )


def merge(device, driver, entries):
    at = now()
    existing = {i.name.lower(): i for i in device.interfaces}
    interfaces, samples, ports, bindings = [], [], [], []
    chassis = f"{device.id}:{driver}:chassis"
    seen = set()
    for entry in entries:
        name = entry["name"]
        if name.lower() in seen or len(name) > 160:
            raise ValueError("duplicate_interface")
        seen.add(name.lower())
        previous = existing.get(name.lower())
        suffix = sha256(name.lower().encode()).hexdigest()[:20]
        identifier = previous.id if previous else f"{device.id}:{driver}:if:{suffix}"
        sample = InterfaceSample(interface_id=identifier, **entry["sample"])
        def observation(value):
            return Observation(value=value, observed_at=at, source="ssh", stale_after_seconds=120,
                               quality="ok" if value is not None else "unknown")
        interfaces.append(Interface(id=identifier, name=name, kind=entry["kind"], if_index=entry["index"],
            admin_up=observation(sample.admin_up), oper_up=observation(sample.oper_up),
            speed_mbps=observation(sample.capacity_bps / 1_000_000 if sample.capacity_bps else None)))
        samples.append(sample)
        if entry["physical"]:
            port_id = f"{device.id}:{driver}:port:{suffix}"
            group, _, label = name.rpartition("/")
            ports.append(PhysicalPort(id=port_id, component_id=chassis, label=label, group=group or "Interfaces",
                                      ordinal=len(ports) + 1, connector="unknown"))
            bindings.append(PortBinding(id=port_id + ":binding", physical_port_id=port_id,
                                        interface_id=identifier, binding_quality="explicit"))
    updates = {"interfaces": interfaces}
    if not device.physical_ports or all(p.id.startswith(f"{device.id}:{driver}:port:") for p in device.physical_ports):
        updates.update(physical_ports=ports, bindings=bindings, inventory_source="ssh", inventory_observed_at=at,
                       components=[PhysicalComponent(id=chassis, kind="chassis", label="Gözlenen chassis")])
    return device.model_copy(update=updates), Telemetry(observed_at=at, source="ssh", reachability="reachable", interfaces=samples)


def parse_structured(device, driver, outputs, unavailable, groups):
    """A malformed health/table response cannot invalidate a valid port read."""
    result = ReadResult(device)
    for group in ("fast", "inventory", "network", "health"):
        if group not in groups:
            continue
        commands = {c.text for c in DRIVERS[driver][1] if c.group == group}
        # Interface output carries logical addresses needed by the network group.
        if group == "network" and result.metadata.get("fast") and result.metadata["fast"].complete:
            commands.update(c.text for c in DRIVERS[driver][1] if c.group == "fast")
        subset = {command: raw for command, raw in outputs.items() if command in commands}
        part = _parse_structured(result.device, driver, subset, unavailable, {group})
        result.device = part.device
        result.payloads.update(part.payloads)
        result.metadata.update(part.metadata)
        if part.observed_profile_id:
            result.observed_profile_id = part.observed_profile_id
            result.identity_evidence = part.identity_evidence
        if group == "fast":
            result.inventory_complete = part.inventory_complete
    return result


def _parse_structured(device, driver, outputs, unavailable, groups):
    from .drivers import _identity_evidence, identify_platform, split
    junos = driver == "juniper_junos"
    parsed = {}
    for command, raw in outputs.items():
        try:
            parsed[command] = xml(raw) if junos else json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        except (ValueError, XML.ParseError, DefusedXmlException):
            unavailable[command] = "collector_parse_failed"
    fast_command = "show interfaces extensive | display xml" if junos else "show interface | json"
    try:
        identity_command = "show version | display xml" if junos else "show version | json"
        platform = identify_platform({identity_command: outputs[identity_command]}) if identity_command in outputs else None
        if platform and platform.runtime_driver_id != driver:
            result = ReadResult(device, metadata={group: metadata(
                group, driver, quality="error", complete=False,
                reason="collector_platform_mismatch",
            ) for group in groups})
            result.observed_profile_id = platform.profile_id
            result.identity_evidence = _identity_evidence(platform, device)
            return result
        if fast_command in parsed:
            entries = junos_interfaces(parsed[fast_command]) if junos else nxos_interfaces(parsed[fast_command])
            updated, batch = merge(device, driver, entries)
        else:
            updated, batch = device, Telemetry(observed_at=now(), source="ssh", reachability="reachable")
        extra = {}
        if junos:
            version = parsed.get("show version | display xml")
            if version is not None:
                updated = updated.model_copy(update={"model": text(version, ".//product-model") or device.model,
                    "os_version": text(version, ".//junos-version") or device.os_version, "vendor": "Juniper"})
            hardware = parsed.get("show chassis hardware | display xml")
            if hardware is not None:
                updated = updated.model_copy(update={"serial": text(hardware, ".//chassis/serial-number") or device.serial})
                extra["modules"] = [{key: text(node, key) for key in ("name", "serial-number", "part-number", "description")}
                                    for node in hardware.findall(".//chassis-module")]
            health = parsed.get("show chassis routing-engine | display xml")
            if health is not None:
                engines = health.findall(".//route-engine")
                extra_health = [{"slot": text(n, "slot"), "cpu_idle": number(text(n, "cpu-idle")),
                                 "memory_percent": number(text(n, "memory-buffer-utilization"))} for n in engines]
                # Report the busiest routing engine; don't add CPU percentages.
                cpus = [100 - n["cpu_idle"] for n in extra_health if n["cpu_idle"] is not None]
                memories = [n["memory_percent"] for n in extra_health if n["memory_percent"] is not None]
                batch.health = Health(cpu_percent=max(cpus) if cpus else None, memory_percent=max(memories) if memories else None)
            environment = parsed.get("show chassis environment | display xml")
            if environment is not None:
                environment_health = junos_environment(environment)
                batch.health = batch.health.model_copy(update={
                    "temperature_c": environment_health.temperature_c,
                    "fan": environment_health.fan,
                    "power_supply": environment_health.power_supply,
                })
            lldp = parsed.get("show lldp neighbors | display xml")
            if lldp is not None:
                names = {i.name: i.id for i in updated.interfaces}
                for row in lldp.findall(".//lldp-neighbor-information"):
                    local, peer = text(row, "lldp-local-interface"), text(row, "lldp-remote-system-name") or text(row, "lldp-remote-chassis-id")
                    if local in names and peer:
                        batch.neighbors.append(Neighbor(id=sha256(f"{local}:{peer}".encode()).hexdigest(), interface_id=names[local],
                            label=peer[:160], relation="l2", evidence=("LLDP: " + (text(row, "lldp-remote-port-id") or ""))[:300]))
            fdb = parsed.get("show ethernet-switching table | display xml")
            arp = parsed.get("show arp no-resolve | display xml")
            if fdb is not None or arp is not None:
                batch.endpoints = junos_endpoints(fdb, arp, updated)
        else:
            version = parsed.get("show version | json", {})
            updated = updated.model_copy(update={"model": version.get("chassis_id", device.model)[:160],
                "os_version": version.get("nxos_ver_str", version.get("kickstart_ver_str", device.os_version))[:160],
                "serial": version.get("proc_board_id", device.serial)[:160], "vendor": "Cisco"})
            resources = parsed.get("show system resources | json", {})
            idle = resources.get("cpu_state_idle")
            total, used = resources.get("memory_usage_total"), resources.get("memory_usage_used")
            batch.health = Health(cpu_percent=100 - float(idle) if idle is not None else None,
                memory_percent=100 * float(used) / float(total) if total and used is not None else None)
            lldp = parsed.get("show lldp neighbors detail | json")
            if lldp is not None:
                batch.neighbors.extend(nxos_neighbors(lldp, updated))
            fdb = parsed.get("show mac address-table | json")
            if fdb is not None:
                batch.endpoints = nxos_fdb(fdb, updated)
            hardware = parsed.get("show inventory | json")
            if hardware is not None:
                extra["modules"] = nxos_inventory(hardware)
        # No raw structured output is retained. Unmapped commands are explicit
        # parser gaps, not silently accepted empty network tables.
        mapped = {
            fast_command, "show version | display xml", "show chassis hardware | display xml",
            "show chassis routing-engine | display xml", "show chassis environment | display xml",
            "show lldp neighbors | display xml", "show ethernet-switching table | display xml",
            "show arp no-resolve | display xml", "show version | json",
            "show system resources | json", "show lldp neighbors detail | json",
            "show mac address-table | json", "show inventory | json",
        }
        for command in parsed.keys() - mapped:
            unavailable[command] = "collector_parse_failed"
        result = split(updated, batch, groups, driver, unavailable, extra)
        result.inventory_complete = fast_command in parsed and "fast" in result.payloads
        if platform:
            result.observed_profile_id = platform.profile_id
            result.identity_evidence = _identity_evidence(platform, updated)
        return result
    except (ValueError, KeyError, TypeError, AttributeError, ZeroDivisionError):
        for command in outputs:
            unavailable[command] = "collector_parse_failed"
        return ReadResult(device, metadata={g: metadata(g, driver, quality="parse_error",
            complete=False, reason="collector_parse_failed") for g in groups})
