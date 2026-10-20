"""Bounded numeric history and five-minute time-weighted summaries.

Only the new automation tables have retention. Legacy device_telemetry and
inventory records are never deleted by this policy.
"""
from datetime import timedelta, timezone
import math

import sqlalchemy as sa

from .collection import upsert
from .database import now
from .telemetry import timestamp


def numeric(payload):
    values = {}
    for key in ("rx_bps", "tx_bps"):
        value = (payload.get("physical_summary") or {}).get(key)
        if value is not None:
            values[key] = value
    for key, value in payload.get("health", {}).items():
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            values[key] = value
    return values


def rollup(points, start):
    """Weight only measured intervals; unobserved time is missing, never zero."""
    end = start + timedelta(seconds=300)
    sums, coverage, low, high = {}, {}, {}, {}
    for index, (at, payload) in enumerate(points):
        until = points[index + 1][0] if index + 1 < len(points) else at
        until = min(until, at + timedelta(seconds=payload.get("stale_after_seconds", 120)), end)
        seconds = max(0, (until - max(at, start)).total_seconds())
        for name, value in numeric(payload).items():
            if seconds:
                sums[name] = sums.get(name, 0) + value * seconds
                coverage[name] = coverage.get(name, 0) + seconds
                low[name] = min(low.get(name, value), value)
                high[name] = max(high.get(name, value), value)
    return {name: {"mean": total / coverage[name], "min": low[name], "max": high[name],
                   "valid_seconds": coverage[name], "coverage_ratio": coverage[name] / 300}
            for name, total in sums.items() if coverage[name]}


def maintain(store, at=None):
    at = at or now()
    table, summaries = store.metric_samples, store.metric_rollups
    # One short batch per worker tick; database work is bounded by devices and
    # sample count, not by the age of a deployment.
    with store.engine.begin() as conn:
        pairs = conn.execute(sa.select(table.c.device_id, table.c.group_name).distinct().limit(200)).all()
        for device_id, group in pairs:
            last = conn.execute(sa.select(sa.func.max(summaries.c.bucket_at)).where(
                summaries.c.device_id == device_id, summaries.c.group_name == group)).scalar_one()
            earliest = conn.execute(sa.select(sa.func.min(table.c.observed_at)).where(
                table.c.device_id == device_id, table.c.group_name == group)).scalar_one()
            if not earliest:
                continue
            earliest = earliest.replace(tzinfo=timezone.utc)
            start = last.replace(tzinfo=timezone.utc) + timedelta(seconds=300) if last else earliest.replace(
                minute=earliest.minute // 5 * 5, second=0, microsecond=0)
            if start + timedelta(seconds=600) > at:
                continue
            # At most six buckets per device per tick; no catch-up explosion.
            end = min(start + timedelta(seconds=1800), at.replace(minute=at.minute // 5 * 5, second=0, microsecond=0) - timedelta(seconds=300))
            rows = conn.execute(sa.select(table.c.observed_at, table.c.payload).where(table.c.device_id == device_id,
                table.c.group_name == group, table.c.observed_at >= start - timedelta(seconds=3600),
                table.c.observed_at <= end + timedelta(seconds=3600)).order_by(table.c.observed_at).limit(2000)).all()
            points = [(t.replace(tzinfo=timezone.utc), p) for t, p in rows]
            while start < end:
                upsert(conn, summaries, (summaries.c.device_id == device_id) & (summaries.c.group_name == group) &
                    (summaries.c.bucket_at == start), dict(device_id=device_id, group_name=group, bucket_at=start,
                    payload=rollup(points, start)))
                start += timedelta(seconds=300)
        # Retain raw data if summary catch-up hasn't reached it yet.
        safe = sa.exists(sa.select(summaries.c.device_id).where(summaries.c.device_id == table.c.device_id,
            summaries.c.group_name == table.c.group_name, summaries.c.bucket_at >= table.c.observed_at))
        ids = sa.select(table.c.id).where(table.c.observed_at < at - timedelta(days=7), safe).limit(2000)
        conn.execute(table.delete().where(table.c.id.in_(ids)))
        old = sa.select(summaries.c.device_id, summaries.c.group_name, summaries.c.bucket_at).where(
            summaries.c.bucket_at < at - timedelta(days=90)).limit(2000)
        conn.execute(summaries.delete().where(sa.tuple_(summaries.c.device_id, summaries.c.group_name, summaries.c.bucket_at).in_(old)))
        conn.execute(store.host_candidates.delete().where(store.host_candidates.c.expires_at < at - timedelta(days=1)))
        conn.execute(store.worker_heartbeats.delete().where(store.worker_heartbeats.c.heartbeat_at < at - timedelta(days=1)))


def history(store, device_id, hours=1, resolution="auto"):
    summarized = resolution == "5m" or hours > 24
    table = store.metric_rollups if summarized else store.metric_samples
    time_column = table.c.bucket_at if summarized else table.c.observed_at
    with store.engine.connect() as conn:
        rows = conn.execute(sa.select(table).where(table.c.device_id == device_id,
            time_column >= now() - timedelta(hours=hours)).order_by(time_column.desc()).limit(2881)).mappings().all()
    return {"resolution": "5m" if summarized else "raw", "truncated": len(rows) > 2880,
        "points": [{"at": r["bucket_at" if summarized else "observed_at"], "group": r["group_name"],
                    "values": r["payload"] if summarized else numeric(r["payload"])} for r in reversed(rows[:2880])]}
