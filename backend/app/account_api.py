"""Authenticated account endpoints; authorization is also rechecked inside write transactions."""
from datetime import datetime
from typing import Literal

from fastapi import Query, Request, Response
from pydantic import Field
import sqlalchemy as sa
from starlette.concurrency import run_in_threadpool

from .auth import COOKIE, fail
from .auditing import audit_page
from .contracts import StrictModel
from .security import Permission, has_permission
from .users import PasswordChange, ProfileUpdate, UserCreate, UserDelete, UserRole, UserUpdate, Users, normalize_avatar


class Activity(StrictModel):
    action: Literal["page.view", "inventory.filter", "port.select", "topology.select"]
    page: Literal["dashboard", "device", "jobs", "audit", "account", "topology"]
    device_id: str | None = Field(default=None, max_length=64)
    port_id: str | None = Field(default=None, max_length=100)
    node_id: str | None = Field(default=None, max_length=200)
    q: str = Field(default="", max_length=160)
    type: Literal["", "switch", "router", "firewall", "server", "other"] = ""
    status: Literal["", "reachable", "unreachable", "unknown"] = ""
    minutes: Literal[15, 60, 360, 1440] = 60


def install_account_routes(app, context):
    def administration(request, mutation=False):
        auth = context(request, mutation)
        if not has_permission(auth.user, Permission.USER_MANAGE, "*"):
            fail("forbidden", 403)
        return auth

    @app.get("/api/v1/profile")
    def profile(request: Request):
        auth = context(request)
        return Users(app.state.store).get(auth.user.user_id)

    @app.put("/api/v1/profile")
    def edit_profile(value: ProfileUpdate, request: Request):
        return Users(app.state.store).profile(context(request, True), value)

    @app.put("/api/v1/profile/password")
    async def change_password(value: PasswordChange, request: Request, response: Response):
        auth = context(request, True)
        await run_in_threadpool(Users(app.state.store).password, auth, value, app.state.auth)
        app.state.ssh.revoke(user_id=auth.user.user_id)
        response.delete_cookie(COOKIE, path="/api", secure=app.state.auth.production, httponly=True, samesite="strict")
        return {"status": "password_changed", "reauthenticate": True}

    @app.put("/api/v1/profile/avatar")
    async def upload_avatar(request: Request):
        auth = context(request, True)
        normalized = await run_in_threadpool(normalize_avatar, await request.body(), request.headers.get("content-type", "").split(";")[0])
        return await run_in_threadpool(Users(app.state.store).avatar, auth, normalized)

    @app.delete("/api/v1/profile/avatar")
    def remove_avatar(request: Request):
        return Users(app.state.store).avatar(context(request, True))

    @app.get("/api/v1/users/{user_id}/avatar")
    def avatar(user_id: str, request: Request):
        auth = context(request)
        if auth.user.user_id != user_id and not has_permission(auth.user, Permission.USER_MANAGE, "*"):
            fail("forbidden", 403)
        with app.state.store.engine.connect() as conn:
            png = conn.execute(sa.select(app.state.store.avatars.c.png).where(app.state.store.avatars.c.user_id == user_id)).scalar_one_or_none()
        if png is None:
            fail("avatar_not_found", 404)
        return Response(png, media_type="image/png", headers={"Content-Disposition": 'inline; filename="avatar.png"'})

    @app.get("/api/v1/users")
    def users(request: Request, q: str = Query("", max_length=160), role: UserRole | None = None,
              limit: int = Query(50, ge=1, le=100), cursor: str | None = Query(None, max_length=1024)):
        administration(request)
        return Users(app.state.store).list(q=q, role=role, limit=limit, cursor=cursor)

    @app.post("/api/v1/users", status_code=201)
    def create_user(value: UserCreate, request: Request):
        return Users(app.state.store).create(administration(request, True), value)

    @app.get("/api/v1/users/{user_id}")
    def user(user_id: str, request: Request):
        administration(request)
        return Users(app.state.store).get(user_id)

    @app.patch("/api/v1/users/{user_id}")
    async def edit_user(user_id: str, value: UserUpdate, request: Request):
        auth = administration(request, True)
        user, revoked = await run_in_threadpool(Users(app.state.store).update, auth, user_id, value)
        if revoked:
            app.state.ssh.revoke(user_id=user_id)
        return {**user, "reauthenticate": revoked and user_id == auth.user.user_id}

    @app.delete("/api/v1/users/{user_id}")
    async def delete_user(user_id: str, value: UserDelete, request: Request):
        auth = administration(request, True)
        await run_in_threadpool(Users(app.state.store).delete, auth, user_id, value.confirmation_username)
        app.state.ssh.revoke(user_id=user_id)
        return {"status": "user_deleted"}

    @app.get("/api/v1/audit")
    def audit(request: Request, limit: int = Query(50, ge=1, le=100), cursor: str | None = Query(None, max_length=1024),
              user_id: str | None = Query(None, max_length=160), actor: str | None = Query(None, max_length=160), event: str | None = Query(None, max_length=80),
              outcome: str | None = Query(None, max_length=100), target_id: str | None = Query(None, max_length=160),
              since: datetime | None = None, until: datetime | None = None):
        auth = administration(request)
        result = audit_page(app.state.store, limit=limit, cursor=cursor, user_id=user_id, actor=actor, event=event,
            outcome=outcome, target_id=target_id, since=since, until=until)
        app.state.store.record(auth.user.user_id, "audit.viewed", "succeeded", status_code=200,
            details={"scope": "superadmin", "filters": {"actor": actor or user_id, "event": event, "outcome": outcome, "target_id": target_id,
                "from": since.isoformat() if since else None, "to": until.isoformat() if until else None}})
        return result

    @app.post("/api/v1/activity", status_code=201)
    def activity(value: Activity, request: Request):
        auth = context(request, True)
        if value.page == "audit" and not has_permission(auth.user, Permission.AUDIT_READ, "*"):
            fail("forbidden", 403)
        if value.device_id:
            device = app.state.store.get_device(value.device_id)
            if not device or not has_permission(auth.user, Permission.INVENTORY_READ, device.site):
                fail("device_not_found_or_forbidden", 404)
            if value.port_id and value.port_id not in {port.id for port in device.physical_ports}:
                fail("port_not_found", 404)
        elif value.page == "device" or value.action in {"port.select", "topology.select"}:
            fail("validation_error", 422)
        app.state.store.record(auth.user.user_id, value.action, "succeeded", value.device_id,
            status_code=201, details={"source": "client-reported", "input": value.model_dump(exclude_none=True)})
        return {"status": "recorded"}
