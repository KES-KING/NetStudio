"""Read-time IP enrichment. No probing, historical resurrection or cable inference.

Only authorized inventory enters this module. An FDB VLAN is local to a device:
cross-device correlation additionally requires an explicit observed L2 adjacency.
Manual diagram links and matching site/VLAN numbers alone are not that evidence.
"""
from collections import defaultdict
from datetime import datetime
from ipaddress import ip_address

import sqlalchemy as sa

from .database import now


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def latest_payloads(store, devices):
    ids = list(devices)
    if not ids:
        return {}
    with store.engine.connect() as conn:
        ranked = sa.select(store.telemetry.c.device_id, store.telemetry.c.payload,
            sa.func.row_number().over(partition_by=store.telemetry.c.device_id,
                order_by=store.telemetry.c.observed_at.desc()).label("rank")).where(
                    store.telemetry.c.device_id.in_(ids)).subquery()
        latest = dict(conn.execute(sa.select(ranked.c.device_id, ranked.c.payload).where(ranked.c.rank == 1)).all())
        automatic = conn.execute(sa.select(store.latest_telemetry.c.device_id, store.latest_telemetry.c.payload)
            .where(store.latest_telemetry.c.device_id.in_(ids))).all()
    for device_id, payload in automatic:
        if device_id not in latest or stamp(payload["observed_at"]) >= stamp(latest[device_id]["observed_at"]):
            latest[device_id] = payload
    return latest


def network_clock(data, at, *, endpoints=False, neighbor=None):
    group = data.get("groups", {}).get("network")
    measured = group.get("observed_at") if group else data.get("observed_at")
    quality = group.get("quality") if group else ("error" if data.get("error") else "ok")
    ttl = group.get("stale_after_seconds", 120) if group else data.get("stale_after_seconds", 120)
    table = neighbor if neighbor is not None else data.get("endpoints") or {}
    if (endpoints or neighbor is not None) and table.get("observed_at"):
        measured = table["observed_at"]
        ttl = table.get("stale_after_seconds") or ttl
    diagnostics = (group or {}).get("diagnostics", {})
    if ((endpoints and diagnostics.get("endpoints"))
            or (neighbor is not None and any("lldp" in key.lower() for key in diagnostics))):
        quality = "error"
    try:
        age = (at - stamp(measured)).total_seconds() if measured else None
    except (TypeError, ValueError):
        age = None  # Unknown timezone/invalid legacy metadata is not current evidence.
    fresh = bool(age is not None and 0 <= age <= ttl
                 and quality in {"ok", "partial"} and data.get("reachability") == "reachable")
    return measured, fresh


def resolve_endpoints(devices, payloads, at=None):
    """Build one bounded index, preserving endpoint IDs and original observations."""
    at = at or now()
    collections, clocks, adjacency = {}, {}, defaultdict(set)
    by_mac = defaultdict(list)
    management = defaultdict(set)
    for device_id, device in devices.items():
        if getattr(device, "management_address", None):
            management[(device.site, device.management_address)].add(device_id)
    for device_id, device in devices.items():
        data = payloads.get(device_id) or {}
        observed, fresh = clocks[device_id] = network_clock(data, at, endpoints=True)
        original = data.get("endpoints") or {"status": "unknown", "entries": []}
        ids = {i.id for i in device.interfaces}
        entries = [dict(e) for e in original.get("entries", []) if e["interface_id"] in ids]
        collections[device_id] = {
            "status": "partial" if len(entries) != len(original.get("entries", [])) else original.get("status", "unknown"),
            "entries": entries,
        }
        for neighbor in data.get("neighbors", []):
            if network_clock(data, at, neighbor=neighbor)[1]:
                remote = neighbor.get("remote_device_id")
                if not remote:
                    # LLDP's advertised management address is identity evidence,
                    # unlike an arbitrary MAC/IP endpoint or a neighbor's name.
                    peers = set()
                    for address in neighbor.get("addresses", []):
                        peers.update(management.get((device.site, address), set()))
                    remote = next(iter(peers)) if len(peers) == 1 else None
                if (neighbor["interface_id"] in ids and remote in devices and remote != device_id
                        and devices[remote].site == device.site
                        and neighbor.get("relation") in {"l2", "physical"}):
                    adjacency[device_id].add(remote)
                    adjacency[remote].add(device_id)
        for entry in entries:
            if fresh and entry["state"] != "stale" and entry["addresses"]:
                by_mac[(device.site, entry["mac"])].append((device_id, entry, observed))

    for device_id, collection in collections.items():
        observed, fresh = clocks[device_id]
        for entry in collection["entries"]:
            resolution = {"status": "observed" if entry["addresses"] else "unresolved",
                          "reason": None if entry["addresses"] else "no_scoped_neighbor",
                          "observed_at": observed, "sources": []}
            entry["resolution"] = resolution
            if not fresh or entry["state"] == "stale":
                resolution.update(status="stale", reason="network_observation_stale")
                continue
            if entry["addresses"] or entry["discovery"] != "fdb":
                continue
            candidates = []
            for source_id, source, source_at in by_mac.get((devices[device_id].site, entry["mac"]), []):
                same_interface = source_id == device_id and source["interface_id"] == entry["interface_id"]
                same_vlan = entry.get("vlan") is not None and source.get("vlan") == entry["vlan"]
                if not (same_interface or same_vlan):
                    continue
                if source_id != device_id and (source_id not in adjacency[device_id] or not same_vlan):
                    continue
                # Never import addresses from unknown or conflicting routing scopes.
                if not source.get("vrf_known"):
                    continue
                if entry.get("vrf_known") and entry.get("vrf") != source.get("vrf"):
                    continue
                # IPv6 link-local addresses cannot be carried across interfaces.
                addresses = [a for a in source["addresses"] if same_interface or not ip_address(a).is_link_local]
                if addresses:
                    candidates.append((source_id, source, source_at, addresses))
            scopes = {source.get("vrf") for _, source, _, _ in candidates}
            # Different snapshots disagreeing about the same MAC are not silently unioned.
            by_source = defaultdict(set)
            for source_id, source, _, addresses in candidates:
                by_source[(source_id, source["interface_id"])].update(addresses)
            address_sets = {tuple(sorted(values)) for values in by_source.values()}
            if len(scopes) > 1 or len(address_sets) > 1:
                resolution.update(status="ambiguous", reason="conflicting_neighbor_observations")
            elif candidates:
                addresses = sorted({a for _, _, _, values in candidates for a in values})
                if len(addresses) > 32:
                    resolution.update(status="ambiguous", reason="address_limit")
                    continue
                entry["addresses"] = addresses
                entry["vrf"], entry["vrf_known"] = next(iter(scopes)), True
                resolution.update(status="resolved", reason="scoped_mac_match",
                    observed_at=min((source_at for _, _, source_at, _ in candidates), key=stamp),
                    sources=[{"device_id": source_id, "device_name": devices[source_id].name,
                              "interface_id": source["interface_id"], "discovery": source["discovery"],
                              "observed_at": source_at, "evidence": source["evidence"]}
                             for source_id, source, source_at, _ in candidates[:8]])
    return collections
