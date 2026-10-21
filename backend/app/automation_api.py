"""Site-scoped automation settings and unauthenticated host-key discovery jobs."""
from datetime import timedelta
from uuid import uuid4

from fastapi import Query, Request
import sqlalchemy as sa

from .auth import fail
from .contracts import ManagedDevice, PollingSettings, SNMPCredentials
from .database import now
from .driver_catalog import DRIVERS, catalog as driver_catalog
from .history import history
from .queue import enqueue, transaction
from .scheduler import ensure_policy
from .security import Permission
from .ssh import target_allowed
from .ssh_profiles import catalog as ssh_catalog, target_signature
from .telemetry import projection


def changed(store, device_id, conn):
    payload = conn.execute(sa.select(store.devices.c.payload).where(store.devices.c.id == device_id).with_for_update()).scalar_one()
    device = ManagedDevice.model_validate(payload)
    store.save_device(device.model_copy(update={"connection_revision": device.connection_revision + 1,
        "resolved_collector": None, "driver_version": None}), conn)
    conn.execute(store.ssh_cache.delete().where(store.ssh_cache.c.device_id == device_id))
    conn.execute(store.polling.update().where(store.polling.c.device_id == device_id)
        .values(paused_reason=None, due_at=now(), state={}, updated_at=now()))


def install(app, context, device_for):
    @app.get("/api/v1/driver-catalog")
    def drivers(request: Request):
        context(request)
        return driver_catalog()

    @app.get("/api/v1/ssh-profiles")
    def profiles(request: Request):
        context(request)
        return ssh_catalog()

    @app.post("/api/v1/devices/{device_id}/host-key-discoveries", status_code=202)
    def discover(device_id: str, request: Request):
        auth, device = device_for(request, device_id, Permission.CREDENTIAL_MANAGE, True)
        target_allowed(app.state.store, device)
        store, at = app.state.store, now()
        with transaction(store) as conn:
            recent = conn.execute(sa.select(store.host_candidates.c.id).where(store.host_candidates.c.device_id == device.id,
                store.host_candidates.c.created_at > at - timedelta(minutes=1))).first()
            if recent:
                fail("host_discovery_rate_limited", 429)
            identifier = str(uuid4())
            conn.execute(store.host_candidates.insert().values(id=identifier, device_id=device.id,
                user_id=auth.user.user_id, connection_revision=device.connection_revision, target_signature=target_signature(device),
                created_at=at, expires_at=at + timedelta(minutes=10), consumed=False))
            job = enqueue(store, device, "ssh_discovery", auth=auth, groups=[], candidate_id=identifier, conn=conn)
            store.record(auth.user.user_id, "host_key.discovery", "queued", device.id,
                details={"job_id": str(job.id)}, conn=conn)
        return {"job_id": job.id, "candidate_id": identifier}

    @app.get("/api/v1/devices/{device_id}/host-key-candidates/{candidate_id}")
    def candidate(device_id: str, candidate_id: str, request: Request):
        auth, device = device_for(request, device_id, Permission.CREDENTIAL_MANAGE)
        table = app.state.store.host_candidates
        with app.state.store.engine.connect() as conn:
            row = conn.execute(sa.select(table).where(table.c.id == candidate_id, table.c.device_id == device.id,
                table.c.user_id == auth.user.user_id, table.c.consumed.is_(False), table.c.expires_at > now())).mappings().first()
        if not row or row["target_signature"] != target_signature(device):
            fail("host_candidate_expired_or_changed", 409)
        return {key: row[key] for key in ("id", "public_key", "fingerprint", "profile", "expires_at")} | {
            "previous_fingerprint": device.host_key_fingerprint, "ready": bool(row["public_key"])}

    @app.get("/api/v1/devices/{device_id}/polling")
    def polling(device_id: str, request: Request):
        _, device = device_for(request, device_id)
        store = app.state.store
        ensure_policy(store, device)
        with store.engine.connect() as conn:
            row = dict(conn.execute(sa.select(store.polling).where(store.polling.c.device_id == device.id)).mappings().one())
            workers = conn.execute(sa.select(sa.func.count()).select_from(store.worker_heartbeats)
                .where(store.worker_heartbeats.c.heartbeat_at > now() - timedelta(seconds=30))).scalar_one()
            row["groups"] = dict(conn.execute(sa.select(store.collection_groups.c.group_name, store.collection_groups.c.metadata)
                .where(store.collection_groups.c.device_id == device.id)).all())
            row["negotiated"] = conn.execute(sa.select(store.ssh_cache.c.negotiated)
                .where(store.ssh_cache.c.device_id == device.id)).scalar_one_or_none()
        row["worker_available"] = workers > 0
        row["generated_at"] = now().isoformat()
        row["readiness"] = ("external" if device.collector == "external" else
            "collector_platform_unsupported" if device.collector not in {"auto", *DRIVERS} else
            "credentials_missing" if not device.credential_configured else
            "host_key_not_trusted" if not device.host_key_fingerprint else "ready")
        return row

    @app.put("/api/v1/devices/{device_id}/polling")
    def set_polling(device_id: str, value: PollingSettings, request: Request):
        auth, device = device_for(request, device_id, Permission.JOB_CREATE, True)
        store = app.state.store
        with transaction(store) as conn:
            ensure_policy(store, device, auth.user.user_id, conn)
            conn.execute(store.polling.update().where(store.polling.c.device_id == device.id).values(
                settings=value.model_dump(), state={}, paused_reason=None, version=store.polling.c.version + 1,
                due_at=now(), updated_at=now(), updated_by=auth.user.user_id))
            store.record(auth.user.user_id, "polling.updated", "succeeded", device.id,
                details={"settings": value.model_dump()}, conn=conn)
        return polling(device_id, request)

    @app.put("/api/v1/devices/{device_id}/snmp-credentials")
    def snmp_credentials(device_id: str, value: SNMPCredentials, request: Request):
        auth, device = device_for(request, device_id, Permission.CREDENTIAL_MANAGE, True)
        values = value.model_dump(exclude={"legacy_auth_confirmed", "auth_password", "privacy_password"})
        secret = {**values, "auth_password": value.auth_password.get_secret_value(),
                  "privacy_password": value.privacy_password.get_secret_value()}
        with app.state.store.engine.begin() as conn:
            app.state.vault.save_protocol(device.id, "snmp", secret, values, conn)
            changed(app.state.store, device.id, conn)
            app.state.store.record(auth.user.user_id, "snmp.credentials.updated", "succeeded", device.id,
                details={"auth_protocol": value.auth_protocol, "privacy_protocol": value.privacy_protocol}, conn=conn)
        app.state.ssh.revoke(device_id=device.id)
        secret.clear()
        return {"snmp_configured": True}

    @app.delete("/api/v1/devices/{device_id}/snmp-credentials")
    def delete_snmp(device_id: str, request: Request):
        auth, device = device_for(request, device_id, Permission.CREDENTIAL_MANAGE, True)
        with app.state.store.engine.begin() as conn:
            conn.execute(app.state.store.protocol_secrets.delete().where(
                app.state.store.protocol_secrets.c.device_id == device.id, app.state.store.protocol_secrets.c.protocol == "snmp"))
            changed(app.state.store, device.id, conn)
            app.state.store.record(auth.user.user_id, "snmp.credentials.deleted", "succeeded", device.id, conn=conn)
        return {"snmp_configured": False}

    @app.get("/api/v1/devices/{device_id}/metrics")
    def metrics(device_id: str, request: Request, hours: int = Query(1, ge=1, le=2160),
                resolution: str = Query("auto", pattern="^(auto|raw|5m)$")):
        device_for(request, device_id)
        return history(app.state.store, device_id, hours, resolution)

    @app.get("/api/v1/devices/{device_id}/overview")
    def device_overview(device_id: str, request: Request):
        auth, device = device_for(request, device_id)
        from .topology import authorized_devices
        from .endpoint_resolution import latest_payloads, resolve_endpoints
        devices = {key: value for key, value in authorized_devices(app.state.store, auth.user).items() if value.site == device.site}
        payloads = latest_payloads(app.state.store, devices)
        data = payloads.get(device.id)
        resolved = resolve_endpoints(devices, payloads, store=app.state.store)[device.id]
        result = projection(device, data, endpoints=resolved)
        points = history(app.state.store, device.id)["points"]
        last_good = (data or {}).get("groups", {}).get("fast", {}).get("observed_at")
        if data and not data.get("groups") and data.get("reachability") == "reachable" and not data.get("error"):
            last_good = data["observed_at"]
        result.update(traffic=[{"at": p["at"], "rx_bps": p["values"].get("rx_bps"), "tx_bps": p["values"].get("tx_bps"),
                               "measured_interfaces": 0} for p in points if p["group"] == "fast"],
                      last_success_at=last_good, history_truncated=False)
        if not points:
            from .telemetry import overview
            history_result = overview(app.state.store, [device], 60)["devices"][0]
            for key in ("traffic", "last_success_at", "history_truncated"):
                result[key] = history_result[key]
        return result
