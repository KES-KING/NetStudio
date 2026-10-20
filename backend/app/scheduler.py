"""Persistent per-device deadlines, jitter, backoff and collector load protection."""
from datetime import timedelta
from hashlib import sha256

import sqlalchemy as sa

from .contracts import PollingSettings
from .database import now
from .driver_catalog import DRIVERS, GROUPS
from .queue import enqueue, transaction
from .telemetry import timestamp

PAUSE = {"authentication_failed", "host_key_changed", "host_key_required", "host_key_not_trusted", "credentials_missing",
         "credential_decryption_failed"}


def ensure_policy(store, device, actor="system:collector", conn=None):
    def write(connection):
        if not connection.execute(sa.select(store.polling.c.device_id).where(store.polling.c.device_id == device.id)).first():
            stagger = int(sha256(device.id.encode()).hexdigest()[:8], 16) % 30
            connection.execute(store.polling.insert().values(device_id=device.id, settings=PollingSettings(
                enabled=device.collector != "external").model_dump(), state={}, version=1,
                due_at=now() + timedelta(seconds=stagger), updated_by=actor, updated_at=now()))
    if conn is not None:
        write(conn)
    else:
        with transaction(store) as connection:
            write(connection)


def effective(settings, state, group, legacy=False):
    target = settings[group + "_seconds"]
    minimum = 60 if group == "fast" and legacy else target
    return min(86400, max(target, minimum, state.get("duration_ema", 0) * 5,
                         target * state.get("load_factor", 1), state.get("backoff_seconds", 0)))


def advance(settings, state, groups, duration, error=None, cpu=None, legacy=False, at=None, seed=""):
    at = at or now()
    state = {**state, "next": {**state.get("next", {})}, "last_attempt_at": at.isoformat(), "last_error": error}
    state["duration_ema"] = max(duration, 0.8 * state.get("duration_ema", duration) + 0.2 * duration)
    if error:
        state["failures"] = state.get("failures", 0) + 1
        state["backoff_seconds"] = min(1800, 30 * 2 ** min(state["failures"], 6))
        state["healthy_reads"] = 0
    else:
        state.update(failures=0, backoff_seconds=0, last_success_at=at.isoformat())
        if cpu is not None:
            state["high_cpu_reads"] = state.get("high_cpu_reads", 0) + 1 if cpu > 80 else 0
            state["healthy_reads"] = state.get("healthy_reads", 0) + 1 if cpu <= 80 else 0
        if state.get("high_cpu_reads", 0) >= 2:
            state["load_factor"] = min(16, state.get("load_factor", 1) * 2)
            state["high_cpu_reads"] = 0
        elif state.get("healthy_reads", 0) >= 5:
            state["load_factor"] = max(1, state.get("load_factor", 1) / 2)
            state["healthy_reads"] = 0
    for group in groups:
        interval = effective(settings, state, group, legacy)
        jitter = (int(sha256(f"{seed}:{group}:{at.isoformat()}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF - .5) * .2
        # Never violate the minimum or measured 20% duty-cycle budget.
        delay = max(settings[group + "_seconds"], 60 if legacy and group == "fast" else 0,
                    state["duration_ema"] * 5, interval * (1 + jitter))
        state["next"][group] = (at + timedelta(seconds=delay)).isoformat()
    state["effective_intervals"] = {g: round(effective(settings, state, g, legacy), 1) for g in GROUPS}
    # On connection failures every channel group shares a bounded backoff.
    if error:
        floor = at + timedelta(seconds=state["backoff_seconds"])
        state["next"] = {g: max(timestamp(state["next"].get(g, floor.isoformat())), floor).isoformat() for g in GROUPS}
    return state


def schedule(store):
    at = now()
    devices = store.list_devices()
    for device in devices:
        ensure_policy(store, device)
    with transaction(store) as conn:
        rows = conn.execute(sa.select(store.polling).where(store.polling.c.due_at <= at)
            .order_by(store.polling.c.due_at).limit(100).with_for_update(skip_locked=True)).mappings().all()
        by_id = {d.id: d for d in devices}
        for row in rows:
            device = by_id.get(row["device_id"])
            if not device or not row["settings"]["enabled"] or row["paused_reason"]:
                continue
            if device.collector not in {"auto", *DRIVERS}:
                continue
            if not device.credential_configured or not device.host_key_fingerprint:
                continue
            groups = [g for g in GROUPS if g not in row["state"].get("next", {})
                      or timestamp(row["state"]["next"][g]) <= at]
            if groups:
                enqueue(store, device, "inventory_read", groups=groups, policy_version=row["version"], conn=conn)
                conn.execute(store.polling.update().where(store.polling.c.device_id == device.id)
                    .values(due_at=at + timedelta(seconds=10)))


def completed(store, device, groups, duration, error=None, cpu=None, policy_version=None, channel_pause=None, reboot=False):
    with transaction(store) as conn:
        row = conn.execute(sa.select(store.polling).where(store.polling.c.device_id == device.id).with_for_update()).mappings().first()
        if not row or (policy_version is not None and row["version"] != policy_version):
            return
        cached = conn.execute(sa.select(store.ssh_cache.c.profile).where(store.ssh_cache.c.device_id == device.id)).scalar_one_or_none()
        legacy = device.ssh_profile in {"huawei_legacy", "legacy_sha1", "legacy_cbc"} or cached not in {None, "standard"}
        fast = conn.execute(sa.select(store.collection_groups.c.metadata).where(
            store.collection_groups.c.device_id == device.id, store.collection_groups.c.group_name == "fast")).scalar_one_or_none()
        if fast and fast.get("source") == "snmp":
            legacy = False
        state = advance(row["settings"], row["state"], groups, duration, error, cpu, legacy, seed=device.id)
        if channel_pause:
            state["channels"] = {**state.get("channels", {}), "snmp": channel_pause}
        if reboot:
            state["next"]["inventory"] = now().isoformat()
        due = min(timestamp(t) for t in state["next"].values()) if state["next"] else now()
        conn.execute(store.polling.update().where(store.polling.c.device_id == device.id).values(
            state=state, due_at=due, paused_reason=error if error in PAUSE else None, updated_at=now()))
