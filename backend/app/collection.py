"""Atomic last-good group projections. Network IO never occurs in transactions."""
from dataclasses import dataclass, field
from copy import deepcopy
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
    capability_evidence: list[tuple[str, GroupObservation]] = field(default_factory=list)
    inventory_complete: bool = False
    reboot_detected: bool = False
    observed_profile_id: str | None = None
    identity_evidence: dict | None = None
    identity_conflicts: list[str] = field(default_factory=list)


def metadata(group, driver, *, quality="ok", reason=None, complete=True, source="ssh", diagnostics=None, fields=None):
    at = now()
    fields = fields or {}
    current = {name for name, status in fields.items() if status in {"ok", "partial"}}
    return GroupObservation(quality=quality, attempted_at=at, observed_at=at if quality in {"ok", "partial"} else None,
        source=source, driver=driver, parser_version=VERSION, reason=reason, complete=complete,
        stale_after_seconds={"fast": 120, "health": 480, "network": 1200, "inventory": 14400}[group],
        diagnostics=diagnostics or {}, fields=fields,
        field_sources={name: source for name in current},
        field_observed_at={name: at for name in current})


SOURCE_PRIORITY = {
    "fast": {"manual": 0, "ssh": 1, "netconf": 2, "api": 3, "snmp": 4},
    "network": {"manual": 0, "ssh": 1, "netconf": 2, "api": 3, "snmp": 4},
    "health": {"manual": 0, "snmp": 1, "ssh": 2, "netconf": 3, "api": 4},
    "inventory": {"manual": 0, "snmp": 1, "ssh": 2, "netconf": 3, "api": 4},
}


def _merge_keyed_rows(current, proposed):
    """Merge typed rows without treating an omitted row as deletion."""
    rows = deepcopy(current or [])
    positions = {}
    for position, row in enumerate(rows):
        if isinstance(row, dict):
            key = row.get("id") or row.get("interface_id") or row.get("index") or row.get("entity_index")
            if key is not None:
                positions[key] = position
    for row in proposed or []:
        if not isinstance(row, dict):
            if row not in rows:
                rows.append(deepcopy(row))
            continue
        key = row.get("id") or row.get("interface_id") or row.get("index") or row.get("entity_index")
        if key is None or key not in positions:
            rows.append(deepcopy(row))
            if key is not None:
                positions[key] = len(rows) - 1
            continue
        target = rows[positions[key]]
        for name, value in row.items():
            if value is not None:
                target[name] = deepcopy(value)
    return rows


def _merge_dict(current, proposed):
    result = deepcopy(current or {})
    for key, value in (proposed or {}).items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_dict(result[key], value)
        elif isinstance(value, list) and isinstance(result.get(key), list):
            result[key] = _merge_keyed_rows(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def merge_group_payload(group, current, proposed, fields, *, replace=False):
    """Field-aware merge used both across transports and against last-good."""
    if replace:
        return deepcopy(proposed)
    current, proposed = current or {}, proposed or {}
    result = deepcopy(current)
    ok = {name for name, status in fields.items() if status in {"ok", "partial"}}
    if group == "fast" and ok:
        result["interfaces"] = _merge_keyed_rows(current.get("interfaces"), proposed.get("interfaces"))
        for key in ("snmp_epoch", "snmp_uptime_ticks", "if_index_map"):
            if key in proposed:
                result[key] = deepcopy(proposed[key])
    elif group == "network":
        if ok & {"addresses", "vrf", "vlan", "lag", "dom"}:
            result["interfaces"] = _merge_keyed_rows(current.get("interfaces"), proposed.get("interfaces"))
        if fields.get("lldp") == "ok" and "neighbors" in proposed:
            result["neighbors"] = deepcopy(proposed["neighbors"])
        if ok & {"fdb", "arp", "ndp"} and proposed.get("endpoints", {}).get("status") in {"ok", "partial"}:
            result["endpoints"] = deepcopy(proposed["endpoints"])
        if fields.get("vlan") == "ok":
            for key in ("bridge_ports", "vlans"):
                if key in proposed:
                    result[key] = deepcopy(proposed[key])
    elif group == "health" and ok:
        result["health"] = _merge_dict(current.get("health"), proposed.get("health"))
        result["interfaces"] = _merge_keyed_rows(current.get("interfaces"), proposed.get("interfaces"))
        if "sensors" in proposed:
            result["sensors"] = _merge_keyed_rows(current.get("sensors"), proposed["sensors"])
    elif group == "inventory" and ok:
        result = _merge_dict(current, proposed)
    return result


def merge_read_results(*results: ReadResult) -> ReadResult:
    """Merge concurrent transport evidence by capability-specific priority."""
    available = [result for result in results if result is not None]
    if not available:
        raise ValueError("collection_result_missing")
    merged = ReadResult(available[0].device)
    merged.inventory_complete = any(result.inventory_complete for result in available)
    merged.reboot_detected = any(result.reboot_detected for result in available)
    identity_results = [
        result for result in available
        if result.observed_profile_id and result.identity_evidence
    ]
    if identity_results:
        # Structured SSH identity is profile-specific. Generic SNMP system
        # identity stays corroborating evidence until vendor mappings exist.
        identity = next((result for result in identity_results if any(
            details.source == "ssh" for details in result.metadata.values()
        )), identity_results[-1])
        merged.observed_profile_id = identity.observed_profile_id
        merged.identity_evidence = deepcopy(identity.identity_evidence)
        observed_profiles = {result.observed_profile_id for result in identity_results}
        if len(observed_profiles) > 1:
            merged.identity_conflicts.append("transport_identity_mismatch")
    merged.identity_conflicts.extend(
        conflict for result in available for conflict in result.identity_conflicts
        if conflict not in merged.identity_conflicts
    )
    for group in {name for result in available for name in result.metadata}:
        candidates = [(result, result.metadata[group]) for result in available if group in result.metadata]
        merged.capability_evidence.extend((group, details) for _, details in candidates)
        candidates.sort(key=lambda pair: SOURCE_PRIORITY[group].get(pair[1].source, -1))
        payload, chosen = {}, candidates[-1][1]
        fields, sources, clocks, diagnostics = {}, {}, {}, {}
        field_evidence: dict[str, list[tuple[str, object]]] = {}
        complete = False
        observed = None
        for result, details in candidates:
            proposed = result.payloads.get(group, {})
            for name, status in details.fields.items():
                if status not in {"ok", "partial"}:
                    continue
                if group in {"fast", "network"}:
                    value = sorted(
                        (str(row.get("interface_id")), row.get(name))
                        for row in proposed.get("interfaces", [])
                        if isinstance(row, dict) and row.get(name) is not None
                    )
                    if not value and name in {"fdb", "arp", "ndp"}:
                        value = proposed.get("endpoints")
                    elif not value and name in {"lldp", "cdp"}:
                        value = proposed.get("neighbors")
                elif group == "health":
                    value = proposed.get("health", {}).get(name)
                else:
                    value = proposed.get(name)
                if value not in (None, [], {}, ""):
                    field_evidence.setdefault(name, []).append((details.source, value))
            payload = merge_group_payload(group, payload, proposed, details.fields,
                                          replace=details.complete and not payload)
            for name, status in details.fields.items():
                if status in {"ok", "partial"} or name not in fields:
                    fields[name] = status
            sources.update(details.field_sources)
            clocks.update(details.field_observed_at)
            diagnostics.update({
                (f"{details.source}:{key}" if len(candidates) > 1 else key): value
                for key, value in details.diagnostics.items()
            })
            if len(candidates) > 1 and details.quality not in {"ok", "partial"} and details.reason:
                diagnostics[details.source] = details.reason
            complete = complete or details.complete
            if details.observed_at and (observed is None or details.observed_at > observed):
                observed = details.observed_at
        for name, evidence in field_evidence.items():
            serialized = {json.dumps(value, sort_keys=True, default=str) for _, value in evidence}
            if len(evidence) > 1 and len(serialized) > 1:
                diagnostics[f"conflict:{name}"] = ",".join(source for source, _ in evidence)
        quality = "ok" if complete and not diagnostics else "partial" if payload else chosen.quality
        merged.payloads[group] = payload
        merged.metadata[group] = chosen.model_copy(update={
            "quality": quality, "complete": complete,
            "reason": None if quality == "ok" else chosen.reason or "transport_evidence_partial",
            "diagnostics": diagnostics, "fields": fields,
            "field_sources": sources, "field_observed_at": clocks,
            "observed_at": observed,
            "driver": "evidence_merge" if len(candidates) > 1 else chosen.driver,
        })
    # SSH/structured inventory remains authoritative for device-level identity
    # until a later sprint has vendor-specific SNMP identity acceptance.
    for result in available:
        if any(meta.source == "ssh" for meta in result.metadata.values()):
            merged.device = result.device
    return merged


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
        binding = record_collected_resolution(
            store, result.device, conn,
            observed_profile_id=result.observed_profile_id,
            identity_evidence=result.identity_evidence,
            identity_conflicts=result.identity_conflicts,
            force_revalidation=result.reboot_detected,
        )
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
        evidence = result.capability_evidence or list(result.metadata.items())
        for capability_id, evidence_meta in evidence:
            save_capability_observation(store, binding, capability_id, evidence_meta, conn)
        for name, meta in result.metadata.items():
            prior = groups.get(name, {})
            details = meta.model_dump(mode="json")
            good = meta.quality == "ok" and meta.complete
            if good or not prior.get("payload"):
                payload = deepcopy(result.payloads.get(name, {}))
            else:
                # A partial mapper may refresh explicit capabilities, but an
                # omitted/failed field is never deletion evidence.
                payload = merge_group_payload(
                    name, prior["payload"], result.payloads.get(name, {}), meta.fields
                )
                details["observed_at"] = prior["metadata"].get("observed_at")
                # Metadata describes the retained values, not the failed
                # replacement channel. Keep the attempt provenance separately.
                for key in ("source", "driver", "parser_version"):
                    details["attempted_" + key] = details[key]
                    details[key] = prior["metadata"].get(key, details[key])
                successful = {
                    field for field, status in meta.fields.items()
                    if status in {"ok", "partial"}
                }
                details["fields"] = {
                    **prior["metadata"].get("fields", {}),
                    **{field: meta.fields[field] for field in successful},
                }
                details["field_sources"] = {
                    **prior["metadata"].get("field_sources", {}),
                    **{field: meta.field_sources[field] for field in successful
                       if field in meta.field_sources},
                }
                details["field_observed_at"] = {
                    **prior["metadata"].get("field_observed_at", {}),
                    **{field: meta.field_observed_at[field].isoformat() for field in successful
                       if field in meta.field_observed_at},
                }
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
                    neighbors = result.payloads.get(name, {}).get("neighbors", [])
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
