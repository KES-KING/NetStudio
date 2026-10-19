from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hmac
import os
from uuid import UUID, uuid4

import asyncssh
from fastapi import FastAPI, HTTPException, Query, Request, Response, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field, SecretStr
import sqlalchemy as sa

from .auth import Auth, COOKIE, fail, session_response
from .collector import collect_linux
from .contracts import Credentials, DeviceCreate, Inventory, ManagedDevice, StrictModel, Telemetry
from .database import Store, now
from .models import Job
from .security import Permission, SecretStoreError, has_permission
from .ssh import ConnectionPolicyError, SSHBroker, connect, error_code
from .telemetry import ingest, overview
from .vault import CredentialVault, credential_values


class Login(StrictModel):
    username: str = Field(min_length=1, max_length=160)
    password: SecretStr = Field(min_length=1, max_length=1024)


class HostKey(StrictModel):
    public_key: str = Field(min_length=20, max_length=16384)
    fingerprint: str = Field(min_length=20, max_length=160)
    replace_existing: bool = False


def create_app(store=None, key_file=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = store or Store()
        app.state.auth = Auth(app.state.store)
        app.state.vault = CredentialVault(app.state.store, key_file)
        app.state.ssh = SSHBroker(app.state.store, app.state.vault, app.state.auth)
        app.state.jobs = set()
        jobs_table = app.state.store.jobs_repository.jobs
        with app.state.store.engine.begin() as conn:
            conn.execute(jobs_table.update().where(jobs_table.c.status.in_(["queued", "running"]))
                .values(status="failed", error_code="server_interrupted", finished_at=now()))
        async def cleanup():
            while True:
                await asyncio.sleep(5)
                app.state.ssh.expire_pending()
        cleaner = asyncio.create_task(cleanup())
        try:
            yield
        finally:
            cleaner.cancel()
            for session in list(app.state.ssh.sessions.values()):
                app.state.ssh.stop(session, "server_shutdown")
            for task in app.state.jobs:
                task.cancel()
            await asyncio.gather(cleaner, *app.state.jobs, return_exceptions=True)

    app = FastAPI(title="Stocc NetStudio API", version="0.2.0", lifespan=lifespan)

    @app.middleware("http")
    async def boundaries(request, call_next):
        if os.getenv("STOCC_ENV") == "production" and request.url.path.startswith("/api/") and request.url.scheme != "https":
            return JSONResponse({"detail": {"code": "https_required"}}, status_code=400)
        try:
            length = int(request.headers.get("content-length", "0") or "0")
        except ValueError:
            return JSONResponse({"detail": {"code": "invalid_content_length"}}, status_code=400)
        if length > 4_000_000:
            return JSONResponse({"detail": {"code": "request_too_large"}}, status_code=413)
        if request.method in {"POST", "PUT", "PATCH"}:
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

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, error):
        # Pydantic's default response includes submitted input, including secrets.
        return JSONResponse({"detail": {"code": "validation_error", "fields": [
            {"location": list(e["loc"]), "type": e["type"]} for e in error.errors()]}}, status_code=422)

    @app.exception_handler(SecretStoreError)
    @app.exception_handler(ConnectionPolicyError)
    async def policy_error(_, error):
        return JSONResponse({"detail": {"code": str(error)}}, status_code=409)

    def context(request, mutation=False):
        return app.state.auth.request(request, mutation)

    def device_for(request, device_id, permission=Permission.INVENTORY_READ, mutation=False):
        auth = context(request, mutation)
        device = app.state.store.get_device(device_id)
        if not device or not has_permission(auth.user, permission, device.site):
            fail("device_not_found_or_forbidden", 404)
        return auth, device

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": "stocc-netstudio-api"}

    @app.get("/readyz")
    def readyz():
        try:
            with app.state.store.engine.connect() as conn:
                conn.execute(sa.select(app.state.store.users.c.id).limit(1))
                conn.execute(sa.select(app.state.store.devices.c.payload).limit(1))
        except Exception:
            fail("persistence_unavailable", 503)
        return {"status": "ready", "service": "stocc-netstudio-api"}

    @app.post("/api/v1/session/login")
    def login(value: Login, request: Request, response: Response):
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

    @app.get("/api/v1/devices/{device_id}")
    def device(request: Request, device_id: str):
        return device_for(request, device_id)[1]

    @app.post("/api/v1/devices", status_code=201)
    def add_device(value: DeviceCreate, request: Request):
        auth = context(request, True)
        if not has_permission(auth.user, Permission.INVENTORY_MANAGE, value.site):
            fail("forbidden", 403)
        device_id = str(uuid4())
        device = ManagedDevice(id=device_id, name=value.name, management_address=value.management_address, site=value.site,
            vendor=value.vendor, platform=value.collector, model=value.model, serial="", os_version="", support_status="generic_readonly",
            components=[], physical_ports=[], interfaces=[], bindings=[], device_type=value.device_type, ssh_port=value.ssh_port,
            collector=value.collector)
        credentials = None
        if value.credentials:
            try:
                credentials = credential_values(value.credentials)
            except ValueError:
                fail("credential_secret_required", 422)
        with app.state.store.engine.begin() as conn:
            app.state.store.save_device(device, conn)
            if credentials:
                app.state.vault.save(device.id, credentials, conn)
        app.state.store.record(auth.user.user_id, "device.created", "succeeded", device.id)
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
        app.state.store.record(auth.user.user_id, "inventory.updated", "succeeded", device.id)
        return app.state.store.get_device(device.id)

    @app.put("/api/v1/devices/{device_id}/credentials")
    def update_credentials(device_id: str, value: Credentials, request: Request):
        auth, device = device_for(request, device_id, Permission.CREDENTIAL_MANAGE, True)
        selected = value.password if value.method == "password" else value.private_key
        if not selected or not selected.get_secret_value():
            if not device.credential_configured:
                fail("credential_secret_required", 422)
            return {"credential_configured": True, "unchanged": True}
        credentials = credential_values(value)
        with app.state.store.engine.begin() as conn:
            app.state.vault.save(device.id, credentials, conn)
        app.state.ssh.revoke(device_id=device.id)
        app.state.store.record(auth.user.user_id, "credentials.updated", "succeeded", device.id)
        return {"credential_configured": True, "unchanged": False}

    @app.delete("/api/v1/devices/{device_id}/credentials")
    def delete_credentials(device_id: str, request: Request):
        auth, device = device_for(request, device_id, Permission.CREDENTIAL_MANAGE, True)
        with app.state.store.engine.begin() as conn:
            conn.execute(app.state.store.secrets.delete().where(app.state.store.secrets.c.device_id == device.id))
        app.state.ssh.revoke(device_id=device.id)
        app.state.store.record(auth.user.user_id, "credentials.deleted", "succeeded", device.id)
        return {"credential_configured": False}

    @app.put("/api/v1/devices/{device_id}/host-key")
    def trust_host(device_id: str, value: HostKey, request: Request):
        auth, device = device_for(request, device_id, Permission.CREDENTIAL_MANAGE, True)
        try:
            key = asyncssh.import_public_key(value.public_key)
            fingerprint = key.get_fingerprint("sha256")
        except (ValueError, asyncssh.KeyImportError):
            fail("invalid_host_key", 422)
        if not hmac.compare_digest(value.fingerprint.strip(), fingerprint):
            fail("host_fingerprint_mismatch", 422)
        if device.host_key_fingerprint and not value.replace_existing:
            fail("host_key_replacement_requires_confirmation", 409)
        with app.state.store.engine.begin() as conn:
            conn.execute(app.state.store.host_keys.delete().where(app.state.store.host_keys.c.device_id == device.id))
            conn.execute(app.state.store.host_keys.insert().values(device_id=device.id, public_key=key.export_public_key().decode(), fingerprint=fingerprint))
        app.state.ssh.revoke(device_id=device.id)
        app.state.store.record(auth.user.user_id, "host_key.trusted", "replaced" if device.host_key_fingerprint else "created", device.id)
        return {"fingerprint": fingerprint}

    @app.post("/api/v1/devices/{device_id}/observations", status_code=201)
    def observation(device_id: str, value: Telemetry, request: Request):
        auth, device = device_for(request, device_id, Permission.TELEMETRY_WRITE, True)
        result = ingest(app.state.store, device, value)
        app.state.store.record(auth.user.user_id, "telemetry.received", value.source, device.id)
        return result

    @app.get("/api/v1/devices/{device_id}/observations/latest")
    def latest(device_id: str, request: Request):
        device_for(request, device_id)
        result = app.state.store.latest(device_id)
        if not result:
            fail("observation_not_found", 404)
        return result

    async def perform_job(job, device, token):
        repository = app.state.store.jobs_repository
        job = job.model_copy(update={"status": "running", "started_at": now(), "attempt": 1})
        repository.update(job)
        try:
            auth = app.state.auth.validate(token)
            if not has_permission(auth.user, Permission.JOB_CREATE, device.site):
                fail("forbidden", 403)
            if job.kind == "inventory_read":
                device, batch = await collect_linux(app.state.store, app.state.vault, device)
                ingest(app.state.store, device, batch)
                result = {"interface_count": len(batch.interfaces), "source": "ssh"}
            else:
                async with connect(app.state.store, app.state.vault, device):
                    result = {"reachable": True, "source": "ssh"}
            job = job.model_copy(update={"status": "succeeded", "result": result, "result_code": "ssh_verified"})
        except asyncio.CancelledError:
            job = job.model_copy(update={"status": "failed", "error_code": "server_shutdown"})
            raise
        except Exception as error:
            code = "session_revoked" if isinstance(error, HTTPException) else error_code(error)
            job = job.model_copy(update={"status": "failed", "error_code": code})
        finally:
            repository.update(job.model_copy(update={"finished_at": now()}))
            app.state.store.record(job.requested_by, "job.finished", job.status, device.id, str(job.id))

    async def queue_job(request, device_id, kind):
        auth, device = device_for(request, device_id, Permission.JOB_CREATE, True)
        if kind == "inventory_read" and device.collector != "linux_ssh":
            fail("external_collector_required", 409)
        if len(app.state.jobs) >= 4:
            fail("collector_busy", 429)
        job = Job(kind=kind, device_id=device.id, requested_by=auth.user.user_id)
        app.state.store.jobs_repository.insert(job)
        task = asyncio.create_task(perform_job(job, device, request.cookies[COOKIE]))
        app.state.jobs.add(task)
        task.add_done_callback(app.state.jobs.discard)
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

    @app.get("/api/v1/audit")
    def audit(request: Request):
        auth = context(request)
        if not has_permission(auth.user, Permission.AUDIT_READ, "*"):
            fail("forbidden", 403)
        with app.state.store.engine.connect() as conn:
            return [dict(row) for row in conn.execute(sa.select(app.state.store.audit).order_by(app.state.store.audit.c.occurred_at.desc()).limit(200)).mappings()]

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
