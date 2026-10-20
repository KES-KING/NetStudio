from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hmac
import os
import time
from uuid import UUID, uuid4

import asyncssh
from fastapi import FastAPI, HTTPException, Query, Request, Response, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field, SecretStr
import sqlalchemy as sa

from .auth import Auth, COOKIE, fail, session_response
from .account_api import install_account_routes
from .auditing import AuditRequest, audit_request, safe_text
from .contracts import ConnectionSettings, Credentials, DeviceCreate, Inventory, ManagedDevice, StrictModel, Telemetry
from .automation_api import changed, install as install_automation
from .queue import enqueue
from .scheduler import ensure_policy
from .ssh_profiles import options_for, attempt_profiles, target_signature
from .database import Store, now
from .security import Permission, SecretStoreError, has_permission
from .ssh import ConnectionPolicyError, SSHBroker
from .telemetry import ingest, overview
from .topology import install_topology_routes
from .vault import CredentialVault, credential_values


class Login(StrictModel):
    username: str = Field(min_length=1, max_length=160)
    password: SecretStr = Field(min_length=1, max_length=1024)


class HostKey(StrictModel):
    public_key: str | None = Field(default=None, min_length=20, max_length=16384)
    fingerprint: str | None = Field(default=None, min_length=20, max_length=160)
    candidate_id: str | None = Field(default=None, max_length=36)
    replace_existing: bool = False


def create_app(store=None, key_file=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = store or Store()
        app.state.auth = Auth(app.state.store)
        app.state.vault = CredentialVault(app.state.store, key_file)
        app.state.ssh = SSHBroker(app.state.store, app.state.vault, app.state.auth)
        app.state.jobs = set()
        # Production jobs belong to a separate durable worker. The embedded
        # mode exists for isolated tests and explicit single-process development.
        worker = worker_task = None
        if os.getenv("STOCC_EMBEDDED_WORKER") == "1":
            from .worker import Worker
            worker = Worker(app.state.store, app.state.vault, app.state.auth,
                scheduling=os.getenv("STOCC_SCHEDULER_ENABLED", "1") == "1")
            worker_task = asyncio.create_task(worker.run())
        async def cleanup():
            while True:
                await asyncio.sleep(5)
                app.state.ssh.expire_pending()
        cleaner = asyncio.create_task(cleanup())
        try:
            yield
        finally:
            if worker:
                worker.stopping.set()
                await worker_task
            cleaner.cancel()
            for session in list(app.state.ssh.sessions.values()):
                app.state.ssh.stop(session, "server_shutdown")
            for task in app.state.jobs:
                task.cancel()
            await asyncio.gather(cleaner, *app.state.jobs, return_exceptions=True)

    app = FastAPI(title="Stocc NetStudio API", version="0.2.0", lifespan=lifespan)

    async def bounded_response(request, call_next):
        if os.getenv("STOCC_ENV") == "production" and request.url.path.startswith("/api/") and request.url.scheme != "https":
            return JSONResponse({"detail": {"code": "https_required"}}, status_code=400)
        try:
            length = int(request.headers.get("content-length", "0") or "0")
        except ValueError:
            return JSONResponse({"detail": {"code": "invalid_content_length"}}, status_code=400)
        if length > 4_000_000:
            return JSONResponse({"detail": {"code": "request_too_large"}}, status_code=413)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 4_000_000:
                    return JSONResponse({"detail": {"code": "request_too_large"}}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.middleware("http")
    async def boundaries(request, call_next):
        audit = AuditRequest(method=request.method, remote_address=safe_text(request.client.host if request.client else "", 100),
            user_agent=safe_text(request.headers.get("user-agent", ""), 256))
        token = audit_request.set(audit)
        try:
            response = await bounded_response(request, call_next)
            route = request.scope.get("route")
            audit.route = getattr(route, "path", "unmatched")
            audit.status_code = response.status_code
            audit.duration_ms = round((time.monotonic() - audit.started) * 1000)
            probe = audit.route == "/api/v1/session/me" and response.status_code == 401
            if request.url.path.startswith("/api/") and not probe:
                if response.status_code >= 400:
                    if audit.user_id == "anonymous" and audit.route != "/api/v1/session/login":
                        try:
                            from .auditing import identify
                            identify(app.state.auth.validate(request.cookies.get(COOKIE)).user)
                        except HTTPException:
                            pass
                    app.state.store.record(audit.user_id, "login" if audit.route == "/api/v1/session/login" else "request.denied" if response.status_code in {401, 403} else "request.failed",
                        "denied" if response.status_code in {401, 403} else "failed",
                        target_type="user" if "user_id" in request.path_params else "device" if "device_id" in request.path_params else None,
                        target_id=safe_text(request.path_params.get("user_id", request.path_params.get("device_id", "")), 160) or None,
                        details={"error_code": audit.error_code or f"http_{response.status_code}",
                            "input": {"username": audit.username} if audit.route == "/api/v1/session/login" else {}})
                elif request.method not in {"GET", "HEAD", "OPTIONS"} and not audit.recorded:
                    app.state.store.record(audit.user_id, "request.completed", "succeeded")
            response.headers["X-Request-ID"] = audit.request_id
            return response
        except Exception:
            # Preserve the original failure, including an unavailable audit store.
            # Never serialize exception text or the submitted request body.
            audit.route = getattr(request.scope.get("route"), "path", "unmatched")
            audit.status_code = 500
            audit.duration_ms = round((time.monotonic() - audit.started) * 1000)
            if request.url.path.startswith("/api/"):
                try:
                    app.state.store.record(audit.user_id, "request.failed", "failed", details={"error_code": "internal_error"})
                except Exception:
                    pass
            raise
        finally:
            audit_request.reset(token)

    @app.exception_handler(HTTPException)
    async def http_error(_, error):
        if current := audit_request.get():
            current.error_code = error.detail.get("code", "http_error") if isinstance(error.detail, dict) else "http_error"
        return JSONResponse({"detail": error.detail}, status_code=error.status_code, headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, error):
        if current := audit_request.get():
            current.error_code = "validation_error"
        # Pydantic's default response includes submitted input, including secrets.
        return JSONResponse({"detail": {"code": "validation_error", "fields": [
            {"location": list(e["loc"]), "type": e["type"]} for e in error.errors()]}}, status_code=422)

    @app.exception_handler(SecretStoreError)
    @app.exception_handler(ConnectionPolicyError)
    async def policy_error(_, error):
        if current := audit_request.get():
            current.error_code = str(error)
        return JSONResponse({"detail": {"code": str(error)}}, status_code=409)

    def context(request, mutation=False):
        if current := audit_request.get():
            route = request.scope.get("route")
            current.route = getattr(route, "path", "unmatched")
            current.status_code = getattr(route, "status_code", None) or 200
        return app.state.auth.request(request, mutation)

    install_account_routes(app, context)
    install_topology_routes(app, context)

    def device_for(request, device_id, permission=Permission.INVENTORY_READ, mutation=False):
        auth = context(request, mutation)
        device = app.state.store.get_device(device_id)
        if not device or not has_permission(auth.user, permission, device.site):
            fail("device_not_found_or_forbidden", 404)
        return auth, device

    install_automation(app, context, device_for)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": "stocc-netstudio-api"}

    @app.get("/readyz")
    def readyz():
        try:
            with app.state.store.engine.connect() as conn:
                conn.execute(sa.select(app.state.store.users.c.display_name).limit(1))
                conn.execute(sa.select(app.state.store.audit.c.request_id).limit(1))
                conn.execute(sa.select(app.state.store.devices.c.payload).limit(1))
                conn.execute(sa.select(app.state.store.topology_boards.c.version).limit(1))
                conn.execute(sa.select(app.state.store.polling.c.version).limit(1))
        except Exception:
            fail("persistence_unavailable", 503)
        return {"status": "ready", "service": "stocc-netstudio-api"}

    @app.post("/api/v1/session/login")
    def login(value: Login, request: Request, response: Response):
        if current := audit_request.get():
            current.route = "/api/v1/session/login"
        app.state.auth.origin(request)
        token, auth = app.state.auth.login(value.username, value.password.get_secret_value(), request.client.host)
        response.set_cookie(COOKIE, token, httponly=True, secure=app.state.auth.production, samesite="strict", max_age=8 * 3600, path="/api")
        return session_response(auth)

    @app.get("/api/v1/session/me")
    def me(request: Request):
        return session_response(context(request))

    @app.post("/api/v1/session/logout")
    async def logout(request: Request, response: Response):
        auth = context(request, True)
        app.state.auth.logout(auth)
        app.state.ssh.revoke(auth_hash=auth.session_hash)
        response.delete_cookie(COOKIE, path="/api", secure=app.state.auth.production, httponly=True, samesite="strict")
        return {"status": "signed_out"}

    @app.get("/api/v1/devices")
    def devices(request: Request):
        auth = context(request)
        return [d for d in app.state.store.list_devices() if has_permission(auth.user, Permission.INVENTORY_READ, d.site)]

    @app.get("/api/v1/overview")
    def dashboard(request: Request, minutes: int = Query(60, ge=5, le=1440)):
        return overview(app.state.store, devices(request), minutes)

    @app.get("/api/v1/overview/summary")
    def dashboard_summary(request: Request):
        from .dashboard import summaries
        return summaries(app.state.store, devices(request))

    @app.get("/api/v1/overview/traffic")
    def dashboard_traffic(request: Request, minutes: int = Query(60, ge=5, le=1440)):
        from .dashboard import traffic
        return traffic(app.state.store, devices(request), minutes)

    @app.get("/api/v1/devices/{device_id}")
    def device(request: Request, device_id: str):
        return device_for(request, device_id)[1]

    @app.post("/api/v1/devices", status_code=201)
    def add_device(value: DeviceCreate, request: Request):
        auth = context(request, True)
        if not has_permission(auth.user, Permission.INVENTORY_MANAGE, value.site):
            fail("forbidden", 403)
        if value.ssh_profile == "huawei_legacy" and not value.legacy_ssh_confirmed:
            fail("legacy_ssh_confirmation_required", 422)
        device_id = str(uuid4())
        device = ManagedDevice(id=device_id, name=value.name, management_address=value.management_address, site=value.site,
            vendor=value.vendor, platform=value.collector, model=value.model, serial="", os_version="", support_status="generic_readonly",
            components=[], physical_ports=[], interfaces=[], bindings=[], device_type=value.device_type, ssh_port=value.ssh_port,
            collector=value.collector, ssh_profile=value.ssh_profile, allow_legacy_ssh=value.allow_legacy_ssh,
            ssh_algorithms=value.ssh_algorithms)
        try:
            options_for(attempt_profiles(device)[0], device)
        except ValueError as error:
            fail(str(error), 422)
        credentials = None
        if value.credentials:
            try:
                credentials = credential_values(value.credentials)
            except ValueError:
                fail("credential_secret_required", 422)
        with app.state.store.engine.begin() as conn:
            app.state.store.save_device(device, conn)
            ensure_policy(app.state.store, device, auth.user.user_id, conn)
            if credentials:
                app.state.vault.save(device.id, credentials, conn)
        app.state.store.record(auth.user.user_id, "device.created", "succeeded", device.id,
            details={"input": value.model_dump(mode="json", exclude={"credentials"}), "credential_configured": credentials is not None})
        return app.state.store.get_device(device.id)

    @app.put("/api/v1/devices/{device_id}/connection-settings")
    def update_connection_settings(device_id: str, value: ConnectionSettings, request: Request):
        auth, device = device_for(request, device_id, Permission.CREDENTIAL_MANAGE, True)
        if not has_permission(auth.user, Permission.INVENTORY_MANAGE, device.site):
            fail("forbidden", 403)
        with app.state.store.engine.begin() as conn:
            current = conn.execute(sa.select(app.state.store.devices.c.payload).where(app.state.store.devices.c.id == device.id).with_for_update()).scalar_one()
            device = ManagedDevice.model_validate(current)
            if value.ssh_profile == "huawei_legacy" and device.ssh_profile != "huawei_legacy" and not value.legacy_ssh_confirmed:
                fail("legacy_ssh_confirmation_required", 422)
            before = device.model_dump(mode="json", include={"collector", "ssh_profile", "allow_legacy_ssh", "ssh_algorithms"})
            after = value.model_dump(mode="json", exclude={"legacy_ssh_confirmed"})
            updated = ManagedDevice.model_validate({**device.model_dump(), **after})
            try:
                options_for(attempt_profiles(updated)[0], updated)
            except ValueError as error:
                fail(str(error), 422)
            app.state.store.save_device(updated, conn)
            changed(app.state.store, device.id, conn)
        if before != after:
            app.state.ssh.revoke(device_id=device.id)
        app.state.store.record(auth.user.user_id, "device.connection.updated", "succeeded", device.id,
            details={"before": before, "after": after, "legacy_ssh_confirmed": value.legacy_ssh_confirmed})
        return app.state.store.get_device(device.id)

    @app.put("/api/v1/devices/{device_id}/inventory")
    def save_inventory(device_id: str, value: Inventory, request: Request):
        auth, device = device_for(request, device_id, Permission.INVENTORY_MANAGE, True)
        with app.state.store.engine.begin() as conn:
            current = conn.execute(sa.select(app.state.store.devices.c.payload).where(app.state.store.devices.c.id == device.id).with_for_update()).scalar_one()
            device = ManagedDevice.model_validate(current)
            if device.inventory_observed_at and value.observed_at <= device.inventory_observed_at:
                fail("out_of_order_inventory", 409)
            update = value.model_dump(exclude={"source", "observed_at"})
            updated = ManagedDevice.model_validate({**device.model_dump(), **update,
                "inventory_source": value.source, "inventory_observed_at": value.observed_at})
            app.state.store.save_device(updated, conn)
        app.state.store.record(auth.user.user_id, "inventory.updated", "succeeded", device.id, details={"source": value.source,
            "observed_at": value.observed_at.isoformat(), "physical_port_count": len(value.physical_ports),
            "interface_count": len(value.interfaces), "binding_count": len(value.bindings)})
        return app.state.store.get_device(device.id)

    @app.put("/api/v1/devices/{device_id}/credentials")
    def update_credentials(device_id: str, value: Credentials, request: Request):
        auth, device = device_for(request, device_id, Permission.CREDENTIAL_MANAGE, True)
        selected = value.password if value.method == "password" else value.private_key
        if not selected or not selected.get_secret_value():
            if not device.credential_configured:
                fail("credential_secret_required", 422)
            app.state.store.record(auth.user.user_id, "credentials.updated", "unchanged", device.id)
            return {"credential_configured": True, "unchanged": True}
        credentials = credential_values(value)
        with app.state.store.engine.begin() as conn:
            app.state.vault.save(device.id, credentials, conn)
            changed(app.state.store, device.id, conn)
        app.state.ssh.revoke(device_id=device.id)
        app.state.store.record(auth.user.user_id, "credentials.updated", "succeeded", device.id,
            details={"authentication_method": value.method, "credential_configured": True})
        return {"credential_configured": True, "unchanged": False}

    @app.delete("/api/v1/devices/{device_id}/credentials")
    def delete_credentials(device_id: str, request: Request):
        auth, device = device_for(request, device_id, Permission.CREDENTIAL_MANAGE, True)
        with app.state.store.engine.begin() as conn:
            conn.execute(app.state.store.secrets.delete().where(app.state.store.secrets.c.device_id == device.id))
            changed(app.state.store, device.id, conn)
        app.state.ssh.revoke(device_id=device.id)
        app.state.store.record(auth.user.user_id, "credentials.deleted", "succeeded", device.id)
        return {"credential_configured": False}

    @app.put("/api/v1/devices/{device_id}/host-key")
    def trust_host(device_id: str, value: HostKey, request: Request):
        auth, device = device_for(request, device_id, Permission.CREDENTIAL_MANAGE, True)
        with app.state.store.engine.begin() as conn:
            store = app.state.store
            payload = conn.execute(sa.select(store.devices.c.payload).where(store.devices.c.id == device.id).with_for_update()).scalar_one()
            prior = conn.execute(sa.select(store.host_keys.c.fingerprint).where(store.host_keys.c.device_id == device.id)).scalar_one_or_none()
            device = ManagedDevice.model_validate({**payload, "host_key_fingerprint": prior})
            public_key, expected = value.public_key, value.fingerprint
            if value.candidate_id:
                row = conn.execute(sa.select(store.host_candidates).where(store.host_candidates.c.id == value.candidate_id,
                    store.host_candidates.c.device_id == device.id, store.host_candidates.c.user_id == auth.user.user_id,
                    store.host_candidates.c.expires_at > now(), store.host_candidates.c.consumed.is_(False)).with_for_update()).mappings().first()
                if not row or not row["public_key"] or row["target_signature"] != target_signature(device):
                    fail("host_candidate_expired_or_changed", 409)
                public_key, expected = row["public_key"], row["fingerprint"]
            try:
                key = asyncssh.import_public_key(public_key or "")
                fingerprint = key.get_fingerprint("sha256")
            except (ValueError, asyncssh.KeyImportError):
                fail("invalid_host_key", 422)
            if not hmac.compare_digest((expected or "").strip(), fingerprint):
                fail("host_fingerprint_mismatch", 422)
            if prior and not value.replace_existing:
                fail("host_key_replacement_requires_confirmation", 409)
            conn.execute(app.state.store.host_keys.delete().where(app.state.store.host_keys.c.device_id == device.id))
            conn.execute(app.state.store.host_keys.insert().values(device_id=device.id, public_key=key.export_public_key().decode(), fingerprint=fingerprint))
            if value.candidate_id:
                conn.execute(store.host_candidates.update().where(store.host_candidates.c.id == value.candidate_id).values(consumed=True))
            changed(store, device.id, conn)
        app.state.ssh.revoke(device_id=device.id)
        app.state.store.record(auth.user.user_id, "host_key.trusted", "replaced" if device.host_key_fingerprint else "created", device.id)
        return {"fingerprint": fingerprint}

    @app.post("/api/v1/devices/{device_id}/observations", status_code=201)
    def observation(device_id: str, value: Telemetry, request: Request):
        auth, device = device_for(request, device_id, Permission.TELEMETRY_WRITE, True)
        result = ingest(app.state.store, device, value)
        app.state.store.record(auth.user.user_id, "telemetry.received", "succeeded", device.id,
            details={"source": value.source, "observed_at": value.observed_at.isoformat(), "interface_count": len(value.interfaces)})
        return result

    @app.get("/api/v1/devices/{device_id}/observations/latest")
    def latest(device_id: str, request: Request):
        device_for(request, device_id)
        result = app.state.store.latest(device_id)
        if not result:
            fail("observation_not_found", 404)
        return result

    async def queue_job(request, device_id, kind):
        auth, device = device_for(request, device_id, Permission.JOB_CREATE, True)
        if kind == "inventory_read" and device.collector == "external":
            fail("external_collector_required", 409)
        job = enqueue(app.state.store, device, kind, auth=auth)
        app.state.store.record(auth.user.user_id, "job.created", "succeeded", device.id, str(job.id), details={"action": kind, "job_id": str(job.id)})
        return job

    @app.post("/api/v1/devices/{device_id}/polls", status_code=202)
    async def poll(device_id: str, request: Request):
        return await queue_job(request, device_id, "inventory_read")

    @app.post("/api/v1/devices/{device_id}/connection-tests", status_code=202)
    async def test_connection(device_id: str, request: Request):
        return await queue_job(request, device_id, "connection_test")

    @app.get("/api/v1/jobs")
    def jobs(request: Request):
        ids = [d.id for d in devices(request)]
        table = app.state.store.jobs_repository.jobs
        with app.state.store.engine.connect() as conn:
            return [dict(row) for row in conn.execute(sa.select(table).where(table.c.device_id.in_(ids)).order_by(table.c.created_at.desc()).limit(100)).mappings()]

    @app.get("/api/v1/jobs/{job_id}")
    def job(job_id: UUID, request: Request):
        context(request)
        result = app.state.store.jobs_repository.get(job_id)
        if not result:
            fail("job_not_found", 404)
        device_for(request, result.device_id)
        return result

    @app.post("/api/v1/devices/{device_id}/ssh-sessions", status_code=201)
    async def start_terminal(device_id: str, request: Request):
        auth, device = device_for(request, device_id, Permission.TERMINAL_OPEN, True)
        session = app.state.ssh.create(auth, device)
        return {"id": session.id, "websocket_path": f"/api/v1/ssh-sessions/{session.id}/ws", "expires_in": 30}

    @app.delete("/api/v1/ssh-sessions/{session_id}")
    async def stop_terminal(session_id: str, request: Request):
        auth = context(request, True)
        session = app.state.ssh.sessions.get(session_id)
        if session and session.auth_hash != auth.session_hash:
            fail("forbidden", 403)
        if session:
            app.state.ssh.stop(session)
        return {"status": "session_ended"}

    @app.websocket("/api/v1/ssh-sessions/{session_id}/ws")
    async def terminal(ws: WebSocket, session_id: str):
        if app.state.auth.production and ws.url.scheme != "wss":
            await ws.close(code=1008)
            return
        await app.state.ssh.run(ws, session_id)

    return app
