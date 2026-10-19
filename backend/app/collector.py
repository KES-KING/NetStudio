"""Read-only Linux SSH adapter; external collectors use the validated telemetry API.

No vendor CLI or hardware geometry is guessed. Linux link data alone cannot
prove a front-panel socket count, so only supplied physical inventory is drawn.
"""
import asyncio
import json
from hashlib import sha256
from ipaddress import ip_address
import sqlalchemy as sa
from pydantic import ValidationError

from .contracts import EndpointCollection, EndpointObservation, Health, InterfaceSample, ManagedDevice, Telemetry
from .database import now
from .models import Interface, Observation, ReadQuality
from .ssh import ConnectionPolicyError, connect, target_allowed


async def read_limited(conn, command):
    process = await conn.create_process(command)
    async def read():
        output = ""
        while part := await process.stdout.read(8192):
            output += part
            if len(output) > 2_000_000:
                process.close()
                raise ValueError("collector_output_limit")
        await process.wait_closed()
        if process.exit_status != 0:
            raise ValueError("collector_command_failed")
        return output
    try:
        return await asyncio.wait_for(read(), 15)
    finally:
        process.close()


async def collect_linux(store, vault, device, authorize=lambda: None):
    async with connect(store, vault, device) as conn:
        # Fixed read-only commands; no browser-provided shell fragments.
        links_raw = await read_limited(conn, "ip -j -s link show")
        addresses_raw = await read_limited(conn, "ip -j address show")
        uptime_raw = await read_limited(conn, "cat /proc/uptime")
        boot_id = (await read_limited(conn, "cat /proc/sys/kernel/random/boot_id")).strip()
        try:
            neighbors_raw = await read_limited(conn, "ip -j neigh show")
        except (ValueError, TimeoutError):
            neighbors_raw = None  # Optional read failure must not erase core telemetry.
    authorize()
    target_allowed(store, device)
    with store.engine.begin() as connection:
        current = connection.execute(sa.select(store.devices.c.payload).where(store.devices.c.id == device.id).with_for_update()).scalar_one()
        current = ManagedDevice.model_validate(current)
        if (current.collector, current.ssh_profile) != (device.collector, device.ssh_profile):
            raise ConnectionPolicyError("device_connection_changed")
        device, batch = linux_snapshot(current, links_raw, addresses_raw, uptime_raw, boot_id, neighbors_raw)
        store.save_device(device, connection)
    return device, batch


def linux_snapshot(device, links_raw, addresses_raw, uptime_raw, boot_id, neighbors_raw=None):
    links, addresses = json.loads(links_raw), json.loads(addresses_raw)
    if not isinstance(links, list) or len(links) > 8192:
        raise ValueError("invalid_collector_inventory")
    at = now()
    existing = {i.name: i for i in device.interfaces}
    interfaces, samples = [], []
    for link in links:
        name = link["ifname"]
        prior = existing.get(name)
        identifier = prior.id if prior else f"{device.id}:if:{link['ifindex']}"
        def obs(value):
            return Observation(value=value, observed_at=at, stale_after_seconds=120, source="ssh", quality=ReadQuality.OK if value is not None else ReadQuality.UNKNOWN)
        kind = (link.get("linkinfo") or {}).get("info_kind")
        interface_kind = "loopback" if link.get("link_type") == "loopback" else "svi" if kind == "vlan" else "port_channel" if kind in {"bond", "bridge"} else "subinterface" if kind else "ethernet"
        up = "UP" in link.get("flags", [])
        oper = True if link.get("operstate") == "UP" else False if link.get("operstate") == "DOWN" else None
        interfaces.append(Interface(id=identifier, name=name, kind=interface_kind, if_index=link["ifindex"], admin_up=obs(up), oper_up=obs(oper), speed_mbps=obs(None)))
        stats = link.get("stats64") or link.get("stats") or {}
        address = next((a for a in addresses if a.get("ifindex") == link["ifindex"]), {})
        samples.append(InterfaceSample(interface_id=identifier, admin_up=up, oper_up=oper,
            in_octets=stats.get("rx", {}).get("bytes"), out_octets=stats.get("tx", {}).get("bytes"),
            errors=stats.get("rx", {}).get("errors"), discards=stats.get("rx", {}).get("dropped"), discontinuity=boot_id,
            addresses=[f"{a['local']}/{a['prefixlen']}" for a in address.get("addr_info", [])]))
    # Keep separately supplied hardware geometry, only retain bindings to present interfaces.
    updates = {"interfaces": interfaces,
        "bindings": [b for b in device.bindings if b.interface_id in {i.id for i in interfaces}]}
    if not device.physical_ports:
        updates.update(inventory_source="ssh", inventory_observed_at=at)
    # The SSH interface read does not re-verify separately supplied chassis data.
    device = device.model_copy(update=updates)
    batch = Telemetry(observed_at=at, source="ssh", reachability="reachable", interfaces=samples,
        health=Health(uptime_seconds=int(float(uptime_raw.split()[0]))), endpoints=linux_endpoints(interfaces, neighbors_raw))
    return device, batch


def linux_endpoints(interfaces, raw):
    """ARP/NDP records are interface-scoped observations, not physical neighbors.

    Do not join a bridge/SVI's ARP table to member ports without FDB/VLAN evidence.
    NUD STALE is retained independently from the age of the telemetry batch.
    """
    if raw is None:
        return EndpointCollection(status="error")
    try:
        rows = json.loads(raw)
        if not isinstance(rows, list) or len(rows) > 16384:
            raise ValueError
    except (ValueError, TypeError):
        return EndpointCollection(status="error")
    names = {i.name: i.id for i in interfaces}
    entries, partial = {}, False
    for row in rows:
        if not isinstance(row, dict):
            partial = True
            continue
        states = row.get("state", [])
        states = {states.upper()} if isinstance(states, str) else {str(s).upper() for s in states} if isinstance(states, list) else set()
        if states & {"FAILED", "INCOMPLETE", "NONE"} or not row.get("lladdr") or row.get("proxy"):
            continue
        try:
            interface_id = names[row["dev"]]
            address = ip_address(row["dst"])
            mac = row["lladdr"].lower()
            identifier = sha256(f"{interface_id}|{mac}|{address}".encode()).hexdigest()[:32]
            entry = EndpointObservation(id=identifier, interface_id=interface_id, mac=mac, addresses=[str(address)],
                discovery="arp" if address.version == 4 else "ndp", evidence="ip -j neigh show",
                state="reachable" if "REACHABLE" in states else "static" if "PERMANENT" in states else "stale" if "STALE" in states else "unknown")
            entries[identifier] = entry
        except (KeyError, ValueError, TypeError, AttributeError, ValidationError):
            partial = True
        if len(entries) >= 2048:
            partial = True
            break
    return EndpointCollection(status="partial" if partial else "ok", entries=list(entries.values()))
