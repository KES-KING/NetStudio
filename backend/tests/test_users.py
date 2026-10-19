from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json

from PIL import Image, PngImagePlugin
import pytest
import sqlalchemy as sa
from fastapi import HTTPException

from app.auditing import safe_details
from app.auth import hasher
from app.users import Users, UserUpdate
from conftest import ORIGIN, PASSWORD, add_device, login


def create_user(client, **changes):
    value = {"username": "created-user", "display_name": "Test user", "role": "viewer", "sites": ["lab"], "password": "created-test-password", **changes}
    response = client.post("/api/v1/users", json=value)
    assert response.status_code == 201, response.text
    return response.json()


def records(store):
    with store.engine.connect() as conn:
        return [dict(row) for row in conn.execute(sa.select(store.audit)).mappings()]


@pytest.mark.parametrize("username", ["viewer", "operator"])
def test_only_superadmin_can_manage_users_or_read_audit(system, username):
    client, _, _, _ = system
    session = login(client, username)
    assert session["roles"] == ["viewer" if username == "viewer" else "engineer"]
    assert "audit.read" not in session["permissions"] and "user.manage" not in session["permissions"]
    assert client.get("/api/v1/users").status_code == 403
    assert client.get("/api/v1/users/admin").status_code == 403
    assert client.get("/api/v1/audit").status_code == 403
    assert client.post("/api/v1/users", json={"username": "blocked", "password": PASSWORD, "sites": ["lab"]}).status_code == 403
    assert client.patch("/api/v1/users/admin", json={"enabled": False}).status_code == 403
    assert client.request("DELETE", "/api/v1/users/admin", json={"confirmation_username": "admin"}).status_code == 403
    assert client.put("/api/v1/profile", json={"display_name": "Escalation", "role": "superadmin"}).status_code == 422
    assert client.put("/api/v1/profile", json={"display_name": "My profile"}).status_code == 200
    assert client.get("/api/v1/session/me").json()["display_name"] == "My profile"


def test_create_edit_delete_preserves_detailed_history_and_never_returns_hashes(system):
    client, store, _, _ = system
    login(client)
    user = create_user(client)
    assert not {"password", "password_hash", "csrf", "avatar"} & user.keys()
    response = client.patch(f"/api/v1/users/{user['id']}", json={"display_name": "Updated name", "role": "engineer", "sites": ["branch"], "password": ""})
    assert response.status_code == 200 and response.json()["role"] == "engineer"
    with store.engine.connect() as conn:
        encoded = conn.execute(sa.select(store.users.c.password_hash).where(store.users.c.id == user["id"])).scalar_one()
    assert hasher.verify(encoded, "created-test-password")
    assert client.request("DELETE", f"/api/v1/users/{user['id']}", json={"confirmation_username": "wrong"}).status_code == 409
    assert client.request("DELETE", f"/api/v1/users/{user['id']}", json={"confirmation_username": user["username"]}).status_code == 200
    assert client.get(f"/api/v1/users/{user['id']}").status_code == 404
    events = records(store)
    change = next(e for e in events if e["event"] == "user.updated")
    assert change["username"] == "admin" and change["roles"] == ["superadmin"]
    assert change["details"]["before"]["display_name"] == "Test user"
    assert change["details"]["after"]["display_name"] == "Updated name"
    assert change["request_id"] and change["route"] == "/api/v1/users/{user_id}"
    assert change["method"] == "PATCH" and change["status_code"] == 200
    assert change["duration_ms"] >= 0 and change["remote_address"]
    assert any(e["event"] == "user.deleted" and e["target_id"] == user["id"] for e in events)
    serialized = json.dumps(events, default=str)
    assert "created-test-password" not in serialized and "$argon2" not in serialized


def test_duplicates_invalid_roles_csrf_and_last_superadmin(system):
    client, _, _, _ = system
    login(client)
    create_user(client)
    assert client.post("/api/v1/users", json={"username": "created-user", "password": PASSWORD, "sites": ["lab"]}).status_code == 409
    for role in ["admin", "operator", "invalid"]:
        assert client.post("/api/v1/users", json={"username": "new", "role": role, "password": PASSWORD, "sites": ["lab"]}).status_code == 422
    assert client.patch("/api/v1/users/viewer", json={"role": "engineer"}, headers={"x-csrf-token": "bad"}).status_code == 403
    assert client.patch("/api/v1/users/admin", json={"role": "viewer"}).json()["detail"]["code"] == "last_superadmin"
    assert client.patch("/api/v1/users/admin", json={"enabled": False}).status_code == 409
    assert client.request("DELETE", "/api/v1/users/admin", json={"confirmation_username": "admin"}).status_code == 409
    create_user(client, username="second-admin", role="superadmin")
    assert client.request("DELETE", "/api/v1/users/admin", json={"confirmation_username": "admin"}).json()["detail"]["code"] == "self_lockout"


@pytest.mark.parametrize("update", [{"role": "viewer"}, {"enabled": False}, {"password": "new-password-for-test"}, {"sites": ["new-site"]}, {"username": "renamed-user"}])
def test_security_changes_revoke_sessions_and_ssh_tickets(system, update):
    client, store, app, _ = system
    login(client, "operator")
    cookie = client.cookies.get("stocc_session")
    from app.ssh import TerminalSession
    from app.auth import digest
    ticket = TerminalSession("test-ticket", "operator", "test-device", digest(cookie))
    app.state.ssh.sessions[ticket.id] = ticket
    login(client)
    assert client.patch("/api/v1/users/operator", json=update).status_code == 200
    assert ticket.id not in app.state.ssh.sessions
    with pytest.raises(HTTPException):
        app.state.auth.validate(cookie)
    assert any(e["event"] == "ssh.ended" for e in records(store))


def test_current_password_required_and_all_sessions_revoked(system):
    client, store, app, _ = system
    login(client, "viewer")
    first = client.cookies.get("stocc_session")
    login(client, "viewer")
    assert client.put("/api/v1/profile/password", json={"current_password": "wrong-password", "new_password": "replacement-password"}).status_code == 403
    response = client.put("/api/v1/profile/password", json={"current_password": PASSWORD, "new_password": "replacement-password"})
    assert response.status_code == 200 and response.json()["reauthenticate"]
    assert client.get("/api/v1/session/me").status_code == 401
    with pytest.raises(HTTPException):
        app.state.auth.validate(first)
    assert client.post("/api/v1/session/login", json={"username": "viewer", "password": PASSWORD}, headers={"origin": ORIGIN}).status_code == 401
    assert client.post("/api/v1/session/login", json={"username": "viewer", "password": "replacement-password"}, headers={"origin": ORIGIN}).status_code == 200
    serialized = json.dumps(records(store), default=str)
    for secret in [PASSWORD, "replacement-password", "wrong-password", first]:
        assert secret not in serialized


def avatar_bytes(size=(32, 32)):
    image = Image.new("RGBA", size, (60, 90, 110, 180))
    output = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private-note", "do-not-store-image-metadata")
    image.save(output, format="PNG", pnginfo=metadata)
    return output.getvalue()


def test_avatar_authenticated_sanitized_and_removable(system):
    client, store, _, _ = system
    login(client, "viewer")
    response = client.put("/api/v1/profile/avatar", content=avatar_bytes((400, 300)), headers={"content-type": "image/png"})
    assert response.status_code == 200 and response.json()["avatar_version"]
    response = client.get("/api/v1/users/viewer/avatar")
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store" and response.headers["x-content-type-options"] == "nosniff"
    image = Image.open(BytesIO(response.content))
    assert image.size == (256, 192) and not image.info
    assert b"do-not-store-image-metadata" not in response.content
    assert client.get("/api/v1/session/me").json()["avatar_version"]
    assert client.get("/api/v1/users/admin/avatar").status_code == 403
    assert client.delete("/api/v1/profile/avatar").status_code == 200
    assert client.get("/api/v1/users/viewer/avatar").status_code == 404
    assert "do-not-store-image-metadata" not in json.dumps(records(store), default=str)


@pytest.mark.parametrize("content,media,code", [(b'<svg onload="alert(1)"/>', "image/svg+xml", 422),
    (b"not an image", "image/png", 422), (b"a" * (2 * 1024 * 1024 + 1), "image/png", 413)])
def test_avatar_rejects_active_invalid_or_oversized_payloads(system, content, media, code):
    client, _, _, _ = system
    login(client)
    assert client.put("/api/v1/profile/avatar", content=content, headers={"content-type": media}).status_code == code


def test_avatar_pixel_limit_and_type_mismatch(system):
    client, _, _, _ = system
    login(client)
    assert client.put("/api/v1/profile/avatar", content=avatar_bytes((2049, 1)), headers={"content-type": "image/png"}).status_code == 422
    assert client.put("/api/v1/profile/avatar", content=avatar_bytes(), headers={"content-type": "image/jpeg"}).status_code == 422


def test_audit_filters_cursor_and_no_sensitive_body_capture(system):
    client, store, _, _ = system
    login(client)
    for index in range(4):
        create_user(client, username=f"cursor-{index}")
    page = client.get("/api/v1/audit?event=user.created&limit=2").json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    second = client.get("/api/v1/audit", params={"event": "user.created", "limit": 2, "cursor": page["next_cursor"]}).json()
    assert len(second["items"]) == 2 and second["next_cursor"] is None
    assert {e["id"] for e in page["items"]}.isdisjoint(e["id"] for e in second["items"])
    assert client.get("/api/v1/audit?cursor=invalid").status_code == 422
    assert client.get("/api/v1/audit?since=2026-10-20T00:00:00Z&until=2026-10-19T00:00:00Z").status_code == 422
    device = add_device(client, credentials={"username": "ssh", "password": "raw-device-secret"})
    assert client.put(f"/api/v1/devices/{device['id']}/credentials", json={"username": "ssh", "method": "private_key", "private_key": "raw-private-key", "passphrase": "raw-passphrase"}).status_code == 200
    assert client.post("/api/v1/users", json={"username": "bad", "password": "short-private-secret", "sites": [], "token": "do-not-echo"}).status_code == 422
    serialized = json.dumps(records(store), default=str)
    for secret in ["raw-device-secret", "raw-private-key", "raw-passphrase", "short-private-secret", "do-not-echo"]:
        assert secret not in serialized
    assert safe_details({"input": {"password": "secret", "credentials": {"password": "secret"}, "name": "password=secret"}}) == {"input": {"name": "[REDACTED]"}}


def test_user_pagination_and_client_activity_is_explicitly_untrusted(system):
    client, _, _, _ = system
    login(client)
    page = client.get("/api/v1/users?limit=2").json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    second = client.get("/api/v1/users", params={"limit": 2, "cursor": page["next_cursor"]}).json()
    assert {u["id"] for u in page["items"]}.isdisjoint(u["id"] for u in second["items"])
    assert client.get("/api/v1/users?role=engineer").json()["items"][0]["role"] == "engineer"
    assert client.post("/api/v1/activity", json={"action": "inventory.filter", "page": "dashboard", "q": "my-switch", "minutes": 60}).status_code == 201
    event = client.get("/api/v1/audit?event=inventory.filter").json()["items"][0]
    assert event["details"]["source"] == "client-reported" and event["details"]["input"]["q"] == "my-switch"
    login(client, "viewer")
    assert client.post("/api/v1/activity", json={"action": "page.view", "page": "audit"}).status_code == 403


def test_concurrent_admin_changes_cannot_remove_all_administrators(system):
    client, store, app, _ = system
    login(client)
    first = app.state.auth.validate(client.cookies.get("stocc_session"))
    second = create_user(client, username="second", role="superadmin", password=PASSWORD)
    login(client, "second")
    other = app.state.auth.validate(client.cookies.get("stocc_session"))
    # Independent connections are necessary to model competing transactions.
    url = str(store.engine.url)
    store.engine.dispose()
    store.engine = sa.create_engine(url, poolclass=sa.pool.NullPool)
    ready = Barrier(2)
    def change(auth, target):
        ready.wait(timeout=5)
        try:
            Users(store).update(auth, target, UserUpdate(role="viewer"))
            return 200
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = [pool.submit(change, first, second["id"]), pool.submit(change, other, "admin")]
        assert sorted(attempt.result(timeout=10) for attempt in attempts) == [200, 401]
    with store.engine.connect() as conn:
        active = conn.execute(sa.select(store.users.c.roles).where(store.users.c.enabled.is_(True))).scalars()
        assert sum("superadmin" in roles for roles in active) == 1


def test_audit_write_failure_rolls_back_user_creation(system, monkeypatch):
    client, store, _, _ = system
    login(client)
    def unavailable(*args, **kwargs):
        raise RuntimeError("audit storage unavailable")
    monkeypatch.setattr(store, "record", unavailable)
    with pytest.raises(RuntimeError, match="audit storage unavailable"):
        client.post("/api/v1/users", json={"username": "rollback-user", "password": PASSWORD, "sites": ["lab"]})
    with store.engine.connect() as conn:
        assert conn.execute(sa.select(store.users.c.id).where(store.users.c.username == "rollback-user")).first() is None


def test_self_password_cannot_bypass_current_password_and_login_failure_is_unverified(system):
    client, store, _, _ = system
    login(client)
    assert client.patch("/api/v1/users/admin", json={"password": "not-allowed-password"}).json()["detail"]["code"] == "self_password_use_profile"
    assert client.post("/api/v1/session/login", json={"username": "viewer", "password": "bad"}).status_code == 401
    denied = [event for event in records(store) if event["event"] == "login" and event["outcome"] == "denied"]
    assert denied[-1]["user_id"] == "anonymous" and denied[-1]["details"]["input"]["username"] == "viewer"


def test_unhandled_failure_is_audited_without_exception_text_or_body(system, monkeypatch):
    client, store, _, _ = system
    login(client, "viewer")
    def unavailable(*args, **kwargs):
        raise RuntimeError("test-internal-error-with-sensitive-diagnostic")
    monkeypatch.setattr(Users, "profile", unavailable)
    with pytest.raises(RuntimeError):
        client.put("/api/v1/profile", json={"display_name": "uncommitted-name"})
    event = [event for event in records(store) if event["event"] == "request.failed"][-1]
    assert event["user_id"] == "viewer" and event["status_code"] == 500
    assert event["details"] == {"error_code": "internal_error"}
    assert "sensitive-diagnostic" not in json.dumps(records(store), default=str)
    assert "uncommitted-name" not in json.dumps(records(store), default=str)
