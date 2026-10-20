import asyncio
from collections import Counter
import json
import time

from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from .auth import COOKIE, fail
from .contracts import StrictModel
from .security import Permission, has_permission
from . import notifications, updates


class UpdatePolicy(StrictModel):
    automatic: bool
    acknowledge_main_execution: bool = False


class UpdateRequest(StrictModel):
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    acknowledge_restart: bool


class ReadReceipt(StrictModel):
    through_id: str = Field(min_length=1, max_length=64)


def install(app, context):
    streams = Counter()

    def manager(request):
        auth = context(request, True)
        if not has_permission(auth.user, Permission.SYSTEM_UPDATE, "*"):
            fail("forbidden", 403)
        return auth

    @app.get("/api/v1/system/updates")
    def status(request: Request):
        auth = context(request)
        return updates.public_state(app.state.store, manager=has_permission(auth.user, Permission.SYSTEM_UPDATE, "*"))

    @app.post("/api/v1/system/updates/check")
    async def check(request: Request):
        manager(request)
        await run_in_threadpool(updates.check, app.state.store, requested=True)
        return updates.public_state(app.state.store, manager=True)

    @app.put("/api/v1/system/updates/policy")
    def policy(value: UpdatePolicy, request: Request):
        auth = manager(request)
        with updates.locked(app.state.store) as (conn, state):
            if not updates.allowed_actor(app.state.store, conn, auth.user.user_id):
                fail("forbidden", 403)
            if value.automatic:
                if not value.acknowledge_main_execution:
                    fail("update_confirmation_required", 422)
                if not updates.agent_online(state):
                    fail("update_agent_unavailable", 409)
                if not state["installed_revision"] or state["recovery_required"]:
                    fail("update_revision_unknown" if not state["installed_revision"] else "update_recovery_required", 409)
            state.update(automatic=value.automatic, policy_actor=auth.user.user_id)
            app.state.store.record(auth.user.user_id, "update.policy", "succeeded", conn=conn,
                details={"enabled": value.automatic}, target_type="system")
            if value.automatic and updates.available(state) and not state["error_code"]:
                updates.enqueue_update(app.state.store, conn, state, auth.user.user_id, automatic=True)
        return updates.public_state(app.state.store, manager=True)

    @app.post("/api/v1/system/updates/install", status_code=202)
    def install_update(value: UpdateRequest, request: Request):
        auth = manager(request)
        with updates.locked(app.state.store) as (conn, state):
            if not value.acknowledge_restart:
                fail("update_confirmation_required", 422)
            if value.revision != state["latest_revision"]:
                fail("update_revision_changed", 409)
            identifier = updates.enqueue_update(app.state.store, conn, state, auth.user.user_id)
        return {"id": identifier, "status": "queued"}

    @app.get("/api/v1/notifications")
    def notification_list(request: Request):
        return notifications.snapshot(app.state.store, context(request).user)

    @app.post("/api/v1/notifications/read")
    def notification_read(value: ReadReceipt, request: Request):
        auth = context(request, True)
        notifications.acknowledge(app.state.store, auth.user, value.through_id)
        return {"status": "read"}

    @app.get("/api/v1/notifications/stream")
    async def events(request: Request):
        auth = context(request)
        if streams[auth.user.user_id] >= 3 or sum(streams.values()) >= 100:
            fail("notification_stream_limit", 429)
        streams[auth.user.user_id] += 1
        async def stream():
            previous = None
            try:
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline and not await request.is_disconnected():
                    try:
                        current = await run_in_threadpool(app.state.auth.validate, request.cookies.get(COOKIE))
                    except Exception:
                        yield "event: revoked\ndata: {}\n\n"
                        return
                    data = await run_in_threadpool(notifications.snapshot, app.state.store, current.user)
                    state = await run_in_threadpool(updates.read, app.state.store)
                    data["update_available"] = updates.available(state)
                    data["maintenance"] = state["maintenance"] or state["recovery_required"]
                    payload = json.dumps(data, ensure_ascii=False)
                    if payload != previous:
                        yield f"event: notifications\ndata: {payload}\n\n"
                        previous = payload
                    else:
                        yield ": heartbeat\n\n"
                    await asyncio.sleep(3)
            finally:
                streams[auth.user.user_id] -= 1
                if not streams[auth.user.user_id]:
                    del streams[auth.user.user_id]
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})
