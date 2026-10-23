"""Atomic last-good group projections. Network IO never occurs in transactions."""
from dataclasses import dataclass, field
from hashlib import sha256
import json
from uuid import uuid4

import sqlalchemy as sa

from .contracts import GroupObservation, ManagedDevice, Telemetry
from .database import now
from .driver_catalog import VERSION
from .ssh import ConnectionPolicyError
from .profile_resolution import record_collected_resolution, save_capability_observation
from .telemetry import normalize, physical_summary, timestamp


@dataclass
class ReadResult:
    device: ManagedDevice
    payloads: dict = field(default_factory=dict)
    metadata: dict[str, GroupObservation] = field(default_factory=dict)
    inventory_complete: bool = False
    reboot_detected: bool = False


def metadata(group, driver, *, quality="ok", reason=None, complete=True, source="ssh", diagnostics=None, fields=None):
    at = now()
    return GroupObservation(quality=quality, attempted_at=at, observed_at=at if quality in {"ok", "partial"} else None,
        source=source, driver=driver, parser_version=VERSION, reason=reason, complete=complete,
        stale_after_seconds={"fast": 120, "health": 480, "network": 1200, "inventory": 14400}[group],
        diagnostics=diagnostics or {}, fields=fields or {})


def upsert(conn, table, condition, values):
    if not conn.execute(table.update().where(condition).values(**values)).rowcount:
        conn.execute(table.insert().values(**values))


def preserve_inventory(current, proposed, complete):
    """Keep manual geometry and stable identities even when discovery is partial."""
    if not complete:
        return current
    manual = current.inventory_source == "manual" or any(p.verified_layout for p in current.physical_ports)
    if manual:
        known = {i.id: i for i in current.interfaces}
        known.update({i.id: i for i in proposed.interfaces})
        proposed = proposed.model_copy(update={"physical_ports": current.physical_ports, "bindings": current.bindings,
            "components": current.components, "inventory_source": current.inventory_source,
            "inventory_observed_at": current.inventory_observed_at, "interfaces": list(known.values())})
    return proposed


def persist(store, original, result, *, fence=lambda conn: None):
    """Fence and device lock protect both inventory and all associated samples."""
    with store.engine.begin() as conn:
        current = ManagedDevice.model_validate(conn.execute(sa.select(store.devices.c.payload)
            .where(store.devices.c.id == original.id).with_for_update()).scalar_one())
        fence(conn)
        if current.connection_revision != original.connection_revision:
            raise ConnectionPolicyError("device_connection_changed")
        # A manual inventory edit which raced the read always wins.
        if current.inventory_observed_at != original.inventory_observed_at:
            raise ConnectionPolicyError("out_of_order_inventory")
        binding = record_collected_resolution(store, result.device, conn)
        device = preserve_inventory(current, result.device, result.inventory_complete)
        if device != current:
            store.save_device(device, conn)
        rows = conn.execute(sa.select(store.collection_groups).where(store.collection_groups.c.device_id == device.id)).mappings()
        groups = {r["group_name"]: {"payload": r["payload"], "metadata": r["metadata"], "content_hash": r["content_hash"]} for r in rows}
        if not groups:
            # First automated failure must not hide a pre-migration/external
            # last-good observation. Keep its original source and timestamps.
            legacy = conn.execute(sa.select(store.telemetry.c.payload).where(store.telemetry.c.device_id == device.id)
                .order_by(store.telemetry.c.observed_at.desc()).limit(1)).scalar_one_or_none()
            if legacy:
                for name, payload in {
                    "fast": {"interfaces": legacy.get("interfaces", [])},
                    "health": {"health": legacy.get("health", {})},
                    "network": {key: legacy.get(key, {} if key == "endpoints" else []) for key in ("endpoints", "neighbors")},
                }.items():
                    # rate_reason is a derived output, not an input sample field.
                    if name == "fast":
                        payload["interfaces"] = [{key: value for key, value in sample.items() if key != "rate_reason"}
                                                 for sample in payload["interfaces"]]
                    details = GroupObservation(quality="ok" if legacy.get("reachability") == "reachable" and not legacy.get("error") else "unknown",
                        observed_at=timestamp(legacy["observed_at"]), attempted_at=timestamp(legacy["observed_at"]),
                        source=legacy["source"], parser_version="legacy-v1", driver="external",
                        stale_after_seconds=legacy["stale_after_seconds"], complete=True).model_dump(mode="json")
                    digest = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                    groups[name] = dict(device_id=device.id, group_name=name, payload=payload, metadata=details, content_hash=digest)
                    conn.execute(store.collection_groups.insert().values(**groups[name]))
        for name, meta in result.metadata.items():
            save_capability_observation(store, binding, name, meta, conn)
            prior = groups.get(name, {})
            details = meta.model_dump(mode="json")
            good = meta.quality == "ok" and meta.complete
            # Partial replacements would silently erase fields/ports. Retain the
            # complete previous group until a complete read succeeds.
            if good or not prior.get("payload"):
                payload = result.payloads.get(name, {})
            else:
                payload = prior["payload"]
                details["observed_at"] = prior["metadata"].get("observed_at")
                # Metadata describes the retained values, not the failed
                # replacement channel. Keep the attempt provenance separately.
                for key in ("source", "driver", "parser_version"):
                    details["attempted_" + key] = details[key]
                    details[key] = prior["metadata"].get(key, details[key])
            if not result.payloads.get(name):
                details["observed_at"] = prior.get("metadata", {}).get("observed_at")
            if name == "network":
                endpoints = result.payloads.get(name, {}).get("endpoints", {})
                if endpoints.get("status") == "ok" and meta.quality in {"ok", "partial"} and meta.observed_at:
                    # An unsupported optional LLDP/DOM command must not freeze a
                    # complete, newly validated ARP/FDB table. Other last-good
                    # network fields and their original group clock stay intact.
                    payload = {**payload, "endpoints": {**endpoints,
                        "observed_at": meta.observed_at.isoformat(),
                        "stale_after_seconds": meta.stale_after_seconds, "source": meta.source}}
                if meta.fields.get("lldp") == "ok" and meta.quality in {"ok", "partial"} and meta.observed_at:
                    neighbors = result.payloads.get(name, {}).get("neighbors")
                    if neighbors:
                        payload = {**payload, "neighbors": [{**neighbor,
                            "observed_at": meta.observed_at.isoformat(), "stale_after_seconds": meta.stale_after_seconds}
                            for neighbor in neighbors]}
            digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            values = dict(device_id=device.id, group_name=name, payload=payload, metadata=details, content_hash=digest)
            upsert(conn, store.collection_groups,
                (store.collection_groups.c.device_id == device.id) & (store.collection_groups.c.group_name == name), values)
            groups[name] = values
            if name in {"inventory", "network"} and payload and digest != prior.get("content_hash"):
                conn.execute(store.collection_history.insert().values(id=str(uuid4()), device_id=device.id,
                    group_name=name, observed_at=meta.attempted_at, payload=payload))
        prior = conn.execute(sa.select(store.latest_telemetry.c.payload).where(store.latest_telemetry.c.device_id == device.id)).scalar_one_or_none()
        external = conn.execute(sa.select(store.telemetry.c.payload).where(store.telemetry.c.device_id == device.id)
            .order_by(store.telemetry.c.observed_at.desc()).limit(1)).scalar_one_or_none()
        if external and (not prior or timestamp(external["observed_at"]) > timestamp(prior["observed_at"])):
            # Switching back from a newer external observation also resets the
            # rate baseline. Do not silently bridge across a different source.
            prior = external
        data = compose(device, groups, prior)
        upsert(conn, store.latest_telemetry, store.latest_telemetry.c.device_id == device.id,
            dict(device_id=device.id, observed_at=timestamp(data["observed_at"]), payload=data))
        for name in ("fast", "health"):
            if name in result.metadata and result.metadata[name].quality == "ok" and result.metadata[name].complete:
                # No large endpoint tables in high-frequency history.
                metrics = {"interfaces": data["interfaces"]} if name == "fast" else {"health": data["health"]}
                metrics["physical_summary"] = data["physical_summary"] if name == "fast" else None
                metrics["stale_after_seconds"] = result.metadata[name].stale_after_seconds
                conn.execute(store.metric_samples.insert().values(id=str(uuid4()), device_id=device.id,
                    group_name=name, observed_at=result.metadata[name].observed_at, payload=metrics))
        return data


def compose(device, groups, previous):
    fast = groups.get("fast", {})
    fast_meta = fast.get("metadata", {})
    sampled_at = fast_meta.get("observed_at") or (previous or {}).get("observed_at") or now().isoformat()
    payload = {"observed_at": sampled_at, "source": fast_meta.get("source", "ssh"),
        "reachability": "reachable" if fast_meta.get("quality") in {"ok", "partial"} else "unknown",
        "error": None if fast_meta.get("quality") in {"ok", "partial"} else fast_meta.get("reason") or "fast_measurement_missing",
        "stale_after_seconds": fast_meta.get("stale_after_seconds", 120), "schema_version": 2,
        "groups": {name: row["metadata"] for name, row in groups.items()},
        "interfaces": fast.get("payload", {}).get("interfaces", []),
        "health": groups.get("health", {}).get("payload", {}).get("health", {}),
        "endpoints": groups.get("network", {}).get("payload", {}).get("endpoints", {}),
        "neighbors": groups.get("network", {}).get("payload", {}).get("neighbors", [])}
    # Normalize only genuinely new fast samples; a health read must not replace
    # a previously calculated rate with a zero-length counter interval.
    fresh = previous is None or sampled_at != previous.get("observed_at") or payload["source"] != previous.get("source")
    batch = Telemetry.model_validate(payload)
    data = normalize(batch, previous) if fresh else {
        **batch.model_dump(mode="json"), "interfaces": (previous or {}).get("interfaces", [])}
    data.setdefault("error", None)
    net = {s["interface_id"]: s for s in groups.get("network", {}).get("payload", {}).get("interfaces", [])}
    health = {s["interface_id"]: s for s in groups.get("health", {}).get("payload", {}).get("interfaces", [])}
    data["interfaces"] = [{**s, **net.get(s["interface_id"], {}), **health.get(s["interface_id"], {})} for s in data["interfaces"]]
    data["received_at"] = now().isoformat()
    data["physical_summary"] = physical_summary(device, data, data["reachability"] != "reachable")
    return data
