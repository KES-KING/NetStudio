"""Separate lightweight current projections from bounded numeric chart history."""
from datetime import timedelta

import sqlalchemy as sa

from .database import now
from .telemetry import projection, timestamp


def summaries(store, devices):
    rows = []
    for device in devices:
        data = store.latest(device.id)
        row = projection(device, data)
        if row["telemetry"]:
            row["telemetry"] = {k: v for k, v in row["telemetry"].items() if k not in {"endpoints", "neighbors"}}
        row["topology"] = {"nodes": [], "links": [], "source": None, "observed_at": None}
        last_good = (data or {}).get("groups", {}).get("fast", {}).get("observed_at")
        if data and not data.get("groups") and data.get("reachability") == "reachable" and not data.get("error"):
            last_good = data["observed_at"]
        row.update(traffic=[], history_truncated=False, last_success_at=last_good)
        rows.append(row)
    return {"devices": rows, "generated_at": now().isoformat(), "range_minutes": 60}


def traffic(store, devices, minutes):
    ids = [d.id for d in devices]
    cutoff = now() - timedelta(minutes=minutes)
    histories = {d.id: [] for d in devices}
    # Select only small numerical summaries in SQL, not full endpoint or
    # interface tables. Cap each device's time window independently.
    with store.engine.connect() as conn:
        for table, extra in ((store.telemetry, []), (store.metric_samples, [store.metric_samples.c.group_name == "fast"])):
            window = sa.select(table.c.device_id, table.c.observed_at,
                table.c.payload["physical_summary"].label("summary"),
                table.c.payload["stale_after_seconds"].label("stale_after_seconds"),
                sa.func.row_number().over(partition_by=table.c.device_id,
                    order_by=table.c.observed_at.desc()).label("rank")).where(
                        table.c.device_id.in_(ids), table.c.observed_at >= cutoff, *extra).subquery()
            rows = conn.execute(sa.select(window).where(window.c.rank <= 600).order_by(window.c.observed_at)).mappings()
            for row in rows:
                summary = row["summary"] or {}
                histories[row["device_id"]].append({"at": row["observed_at"].isoformat(),
                    "rx_bps": summary.get("rx_bps"), "tx_bps": summary.get("tx_bps"),
                    "measured_interfaces": summary.get("measured_interfaces", 0),
                    "stale_after_seconds": row["stale_after_seconds"] or 120})
    for device_id, points in histories.items():
        ordered, series = sorted(points, key=lambda p: p["at"])[-600:], []
        for point in ordered:
            if series:
                previous = series[-1]
                until = timestamp(previous["at"]) + timedelta(seconds=previous.get("stale_after_seconds", 120))
                if timestamp(point["at"]) > until:
                    series.append({"at": until.isoformat(), "rx_bps": None, "tx_bps": None, "measured_interfaces": 0})
            series.append(point)
        histories[device_id] = series
    return histories
