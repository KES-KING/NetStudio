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
CHANNEL_ERRORS = PAUSE | {
    "snmp_authentication_failed", "snmp_context_mismatch", "snmp_timeout",
    "snmp_read_failed", "connection_timeout", "connection_failed",
    "controller_credentials_missing", "controller_authentication_failed",
    "controller_scope_insufficient", "controller_token_expired", "controller_timeout",
    "controller_tls_or_connection_failed", "controller_rate_limited",
}


def channel_ready(state, channel, at=None):
    """A paused channel is retried after its bounded backoff, not forever."""
    at = at or now()
    value = state.get("channels", {}).get(channel)
    if not value or isinstance(value, str):
        return True  # Legacy string pauses recover on the first S04 scheduler pass.
    retry_at = value.get("retry_at")
    return not retry_at or timestamp(retry_at) <= at


def _channel_state(state, outcomes, at):
    channels = {**state.get("channels", {})}
    for channel, error in outcomes.items():
        if not error:
            channels.pop(channel, None)
            continue
        previous = channels.get(channel)
        failures = (previous.get("failures", 0) if isinstance(previous, dict) else 0) + 1
        delay = min(1800, 30 * 2 ** min(failures - 1, 6))
        channels[channel] = {
            "reason": error if error in CHANNEL_ERRORS else "transport_failed",
            "failures": failures,
            "last_error_at": at.isoformat(),
            "retry_at": (at + timedelta(seconds=delay)).isoformat(),
        }
    state["channels"] = channels
    return state


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
            if not device or not row["settings"]["enabled"]:
                continue
            if row["paused_reason"]:
                if row["paused_reason"] in PAUSE:
                    migrated = _channel_state(row["state"], {"ssh": row["paused_reason"]}, at)
                    retry_at = migrated["channels"]["ssh"]["retry_at"]
                    conn.execute(store.polling.update().where(store.polling.c.device_id == device.id).values(
                        state=migrated, paused_reason=None, due_at=timestamp(retry_at), updated_at=at))
                continue
            if device.collector not in {"auto", *DRIVERS}:
                continue
            preference = row["settings"].get("preferred_source", "auto")
            from .worker import implemented_transports
            transports = implemented_transports(device)
            ssh_ready = "ssh" in transports and device.credential_configured and device.host_key_fingerprint and channel_ready(row["state"], "ssh", at)
            snmp_ready = "snmp" in transports and device.snmp_configured and channel_ready(row["state"], "snmp", at)
            api_ready = "api" in transports and device.api_configured and channel_ready(row["state"], "api", at)
            if ((preference == "ssh" and not ssh_ready)
                    or (preference == "snmp" and not snmp_ready)
                    or (preference == "api" and not api_ready)
                    or (preference == "auto" and not (ssh_ready or snmp_ready or api_ready))):
                retries = [value.get("retry_at") for value in row["state"].get("channels", {}).values()
                           if isinstance(value, dict) and value.get("retry_at")]
                if retries:
                    conn.execute(store.polling.update().where(store.polling.c.device_id == device.id)
                        .values(due_at=min(timestamp(value) for value in retries)))
                continue
            groups = [g for g in GROUPS if g not in row["state"].get("next", {})
                      or timestamp(row["state"]["next"][g]) <= at]
            if groups:
                enqueue(store, device, "inventory_read", groups=groups, policy_version=row["version"], conn=conn)
                conn.execute(store.polling.update().where(store.polling.c.device_id == device.id)
                    .values(due_at=at + timedelta(seconds=10)))


def completed(store, device, groups, duration, error=None, cpu=None, policy_version=None,
              channel_pause=None, channel_outcomes=None, reboot=False):
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
        channel_outcomes = dict(channel_outcomes or {})
        channel_failures = {value for value in channel_outcomes.values() if value}
        channel_scoped = bool(channel_failures) and (error in channel_failures or error == "collector_parse_failed")
        state = advance(row["settings"], row["state"], groups, duration,
                        None if channel_scoped else error, cpu, legacy, seed=device.id)
        if channel_scoped:
            state["last_error"] = error
        if channel_pause:
            channel_outcomes.setdefault("snmp", channel_pause)
        state = _channel_state(state, channel_outcomes, now())
        if reboot:
            state["next"]["inventory"] = now().isoformat()
        due = min(timestamp(t) for t in state["next"].values()) if state["next"] else now()
        # Transport authentication is channel-local.  A failed SSH credential
        # must not disable a healthy SNMP path and vice versa.
        global_pause = error if error in PAUSE and not channel_outcomes else None
        conn.execute(store.polling.update().where(store.polling.c.device_id == device.id).values(
            state=state, due_at=due, paused_reason=global_pause, updated_at=now()))
