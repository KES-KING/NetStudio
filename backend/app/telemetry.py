"""One measurement projection for charts, list, panel and detail views."""
from datetime import datetime, timedelta, timezone
from ipaddress import ip_interface
from uuid import uuid4

import sqlalchemy as sa

from .auth import fail
from .contracts import Telemetry
from .database import now


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize(batch, previous):
    data = batch.model_dump(mode="json")
    previous_by_id = {i["interface_id"]: i for i in previous.get("interfaces", [])} if previous else {}
    for sample in data["interfaces"]:
        reason = None
        if sample["quality"] not in {"ok", "partial"}:
            sample["rx_bps"] = sample["tx_bps"] = None
            sample["rate_reason"] = sample["quality"]
            continue
        if sample["in_octets"] is not None and sample["out_octets"] is not None and sample["rx_bps"] is None and sample["tx_bps"] is None:
            prior = previous_by_id.get(sample["interface_id"])
            elapsed = (batch.observed_at - timestamp(previous["observed_at"])).total_seconds() if previous else 0
            if not sample["counter_epoch_known"] or (prior and prior.get("counter_epoch_known") is False):
                reason = "counter_epoch_unknown"
            elif not prior or prior.get("in_octets") is None or prior.get("out_octets") is None:
                reason = "baseline_required"
            elif prior.get("quality") not in {"ok", "partial"}:
                reason = "previous_sample_invalid"
            elif (sample.get("source") or batch.source) != (prior.get("source") or previous.get("source")):
                reason = "counter_source_changed"
            elif sample.get("counter_bits") != prior.get("counter_bits"):
                reason = "counter_width_changed"
            elif elapsed <= 0 or elapsed > max(batch.stale_after_seconds, previous["stale_after_seconds"]):
                reason = "invalid_or_missing_interval"
            elif sample["discontinuity"] != prior.get("discontinuity"):
                reason = "counter_discontinuity"
            elif sample["in_octets"] < prior["in_octets"] or sample["out_octets"] < prior["out_octets"]:
                reason = "counter_reset_or_wrap"
            else:
                sample["rx_bps"] = 8 * (sample["in_octets"] - prior["in_octets"]) / elapsed
                sample["tx_bps"] = 8 * (sample["out_octets"] - prior["out_octets"]) / elapsed
        sample["rate_reason"] = reason
    return data


def ingest(store, device, batch: Telemetry):
    with store.engine.begin() as conn:
        # Serialize against inventory changes and other collectors for this device.
        current = conn.execute(sa.select(store.devices.c.payload).where(store.devices.c.id == device.id).with_for_update()).scalar_one()
        from .contracts import ManagedDevice
        device = ManagedDevice.model_validate(current)
        ids = {i.id for i in device.interfaces}
        if (any(i.interface_id not in ids for i in batch.interfaces)
                or any(n.interface_id not in ids for n in batch.neighbors)
                or any(e.interface_id not in ids for e in batch.endpoints.entries)):
            fail("unknown_interface_id", 422)
        previous = conn.execute(sa.select(store.telemetry.c.payload).where(store.telemetry.c.device_id == device.id)
            .order_by(store.telemetry.c.observed_at.desc()).limit(1)).scalar_one_or_none()
        automated = conn.execute(sa.select(store.latest_telemetry.c.payload).where(store.latest_telemetry.c.device_id == device.id)).scalar_one_or_none()
        if automated and (not previous or timestamp(automated["observed_at"]) > timestamp(previous["observed_at"])):
            previous = automated
        if previous and batch.observed_at <= timestamp(previous["observed_at"]):
            fail("out_of_order_observation", 409)
        data = normalize(batch, previous)
        data["received_at"] = now().isoformat()
        data["physical_summary"] = physical_summary(device, data, bool(data.get("error")) or data["reachability"] != "reachable")
        conn.execute(store.telemetry.insert().values(id=str(uuid4()), device_id=device.id, observed_at=batch.observed_at,
            received_at=now(), payload=data))
    return data


def physical_summary(device, telemetry, stale):
    sample_map = {i["interface_id"]: i for i in (telemetry or {}).get("interfaces", [])}
    if_types = {i.id: i.kind for i in device.interfaces}
    binding_map = {}
    for binding in device.bindings:
        if binding.binding_quality == "explicit":
            binding_map.setdefault(binding.physical_port_id, []).append(binding.interface_id)
    root_ports = [p for p in device.physical_ports if not p.parent_port_id and p.connector not in {"console", "management"}]
    states = {"up": 0, "down": 0, "disabled": 0, "unknown": 0}
    port_states = {}
    traffic_ids = set()
    for port in root_ports:
        children = [p for p in device.physical_ports if p.parent_port_id == port.id]
        ids = {i for p in (children or [port]) for i in binding_map.get(p.id, []) if if_types.get(i) == "ethernet"}
        samples = [sample_map.get(i) for i in ids]
        status = "unknown"
        if not stale and samples and all(s and s["quality"] == "ok" for s in samples):
            if any(s["oper_up"] is True and s["admin_up"] is True for s in samples):
                status = "up"
            elif all(s["admin_up"] is False for s in samples):
                status = "disabled"
            elif all(s["admin_up"] is not None and s["oper_up"] is not None for s in samples):
                status = "down"
        states[status] += 1
        port_states[port.id] = status
        traffic_ids.update(ids)
    # Exclude logical interfaces and parent/child double counts from traffic too.
    rates = [sample_map[i] for i in sorted(traffic_ids) if i in sample_map]
    def total(direction):
        values = [i[direction] for i in rates if i.get(direction) is not None and i["quality"] in {"ok", "partial"}]
        return sum(values) if values and not stale else None
    return {"counts": states, "total": len(root_ports), "port_states": port_states,
        "active_ratio": 100 * states["up"] / len(root_ports) if root_ports and not stale and states["unknown"] < len(root_ports) else None,
        "rx_bps": total("rx_bps"), "tx_bps": total("tx_bps"),
        "traffic_interface_ids": sorted(traffic_ids),
        "measured_interfaces": sum(1 for i in rates if i.get("rx_bps") is not None and i.get("tx_bps") is not None) if not stale else 0,
        "traffic_scope": "Fiziksel portlara bağlı ethernet arayüzlerinin gözlenen toplamı; benzersiz ağ trafiği değildir."}


def topology(device, data):
    nodes, links = {}, []
    for sample in (data or {}).get("interfaces", []):
        iface = next((i for i in device.interfaces if i.id == sample["interface_id"]), None)
        if not iface:
            continue
        interface_node = f"interface:{iface.id}"
        vrf_known = sample.get("vrf_known", True)
        vrf_scope = (sample.get("vrf") or "default") if vrf_known else f"unknown:{iface.id}"
        vrf_label = (sample.get("vrf") or "Varsayılan VRF") if vrf_known else "VRF bilinmiyor; yalnız bu arayüzün IP ilişkisi"
        for address in sample["addresses"]:
            cidr = ip_interface(address)
            subnet_id = f"subnet:{vrf_scope}:{cidr.network}"
            nodes[interface_node] = {"id": interface_node, "name": iface.name, "kind": "interface", "interface_id": iface.id,
                "detail": ", ".join(sample["addresses"]), "vrf": sample.get("vrf"), "vlan": sample.get("access_vlan")}
            nodes[subnet_id] = {"id": subnet_id, "name": str(cidr.network), "kind": "subnet", "detail": vrf_label}
            links.append({"source": interface_node, "target": subnet_id, "relation": "l3", "evidence": address})
    for neighbor in (data or {}).get("neighbors", []):
        iface = next((i for i in device.interfaces if i.id == neighbor["interface_id"]), None)
        if not iface:
            continue
        node_id, peer_id = f"interface:{iface.id}", f"neighbor:{neighbor['id']}"
        nodes.setdefault(node_id, {"id": node_id, "name": iface.name, "kind": "interface", "interface_id": iface.id, "detail": ""})
        nodes[peer_id] = {"id": peer_id, "name": neighbor["label"], "kind": "neighbor", "detail": neighbor["evidence"]}
        links.append({"source": node_id, "target": peer_id, "relation": neighbor["relation"], "evidence": neighbor["evidence"]})
    unique = {(e["source"], e["target"], e["relation"]): e for e in links}
    return {"nodes": list(nodes.values()), "links": list(unique.values()), "observed_at": (data or {}).get("observed_at"), "source": (data or {}).get("source")}


def projection(device, data, at=None):
    at = at or now()
    stale = bool(data and (at - timestamp(data["observed_at"])).total_seconds() > data["stale_after_seconds"])
    availability = "unknown" if stale or not data else data["reachability"]
    state = "no_data" if not data else "stale" if stale else "error" if data.get("error") else "unreachable" if availability == "unreachable" else "current"
    health = (data or {}).get("groups", {}).get("health")
    health_stale = bool(health and (health.get("observed_at") is None or
        (at - timestamp(health["observed_at"])).total_seconds() > health["stale_after_seconds"] or health["quality"] not in {"ok", "partial"}))
    return {"device": device.model_dump(mode="json"), "telemetry": data, "data_state": state,
        "reachability": availability, "health_status": "unknown" if state != "current" or health_stale else data["health"]["status"],
        "ports": physical_summary(device, data, state != "current" or availability != "reachable"), "topology": topology(device, data)}


def overview(store, devices, minutes):
    cutoff = now() - timedelta(minutes=minutes)
    ids = [d.id for d in devices]
    histories = {d.id: [] for d in devices}
    latest = {}
    successes = {}
    if ids:
        with store.engine.connect() as conn:
            ranked = sa.select(store.telemetry.c.device_id, store.telemetry.c.payload,
                sa.func.row_number().over(partition_by=store.telemetry.c.device_id, order_by=store.telemetry.c.observed_at.desc()).label("rank")).subquery()
            latest = dict(conn.execute(sa.select(ranked.c.device_id, ranked.c.payload).where(ranked.c.device_id.in_(ids), ranked.c.rank == 1)).all())
            successes = dict(conn.execute(sa.select(store.telemetry.c.device_id, sa.func.max(store.telemetry.c.observed_at))
                .where(store.telemetry.c.device_id.in_(ids), store.telemetry.c.payload["reachability"].as_string() == "reachable",
                    store.telemetry.c.payload["error"].as_string().is_(None)).group_by(store.telemetry.c.device_id)).all())
            window = sa.select(store.telemetry.c.device_id, store.telemetry.c.payload, store.telemetry.c.observed_at,
                sa.func.row_number().over(partition_by=store.telemetry.c.device_id, order_by=store.telemetry.c.observed_at.desc()).label("rank"))
            window = window.where(store.telemetry.c.device_id.in_(ids), store.telemetry.c.observed_at >= cutoff).subquery()
            rows = conn.execute(sa.select(window.c.device_id, window.c.payload).where(window.c.rank <= 2881).order_by(window.c.observed_at)).all()
        for device_id, payload in rows:
            histories[device_id].append(payload)
        with store.engine.connect() as conn:
            automated = conn.execute(sa.select(store.latest_telemetry.c.device_id, store.latest_telemetry.c.payload)
                .where(store.latest_telemetry.c.device_id.in_(ids))).all()
        for device_id, payload in automated:
            if device_id not in latest or timestamp(payload["observed_at"]) >= timestamp(latest[device_id]["observed_at"]):
                latest[device_id] = payload
                fast = payload.get("groups", {}).get("fast", {})
                if fast.get("observed_at"):
                    successes[device_id] = timestamp(fast["observed_at"])
    result = []
    for device in devices:
        row = projection(device, latest.get(device.id))
        series = []
        history = histories[device.id]
        row["history_truncated"] = len(history) > 2880
        previous = None
        for data in history[-2880:]:
            if previous and (timestamp(data["observed_at"]) - timestamp(previous["observed_at"])).total_seconds() > previous["stale_after_seconds"]:
                series.append({"at": (timestamp(previous["observed_at"]) + timedelta(seconds=previous["stale_after_seconds"])).isoformat(), "rx_bps": None, "tx_bps": None, "measured_interfaces": 0})
            summary = data.get("physical_summary") or physical_summary(device, data, bool(data.get("error")) or data["reachability"] != "reachable")
            series.append({"at": data["observed_at"], "rx_bps": summary["rx_bps"], "tx_bps": summary["tx_bps"],
                "measured_interfaces": summary["measured_interfaces"]})
            previous = data
        row["traffic"] = series
        success = successes.get(device.id)
        row["last_success_at"] = success.replace(tzinfo=timezone.utc).isoformat() if success else None
        result.append(row)
    return {"devices": result, "generated_at": now().isoformat(), "range_minutes": minutes}
