"""Opaque, revocable server sessions and Argon2id login credentials."""
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import hmac
import os
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException
import sqlalchemy as sa

from .security import SessionUser
from .auditing import audit_request, identify, safe_text

COOKIE = "stocc_session"
hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
_dummy_hash = hasher.hash(secrets.token_urlsafe(32))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def fail(code, status=400):
    raise HTTPException(status_code=status, detail={"code": code})


@dataclass
class AuthContext:
    user: SessionUser
    session_hash: str
    csrf: str


class Auth:
    def __init__(self, store):
        self.store = store
        self.attempts = OrderedDict()
        self.production = os.getenv("STOCC_ENV", "development") == "production"
        self.origins = {s.strip().rstrip("/") for s in os.getenv("STOCC_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if s.strip()}
        if self.production and any(not s.startswith("https://") for s in self.origins):
            raise RuntimeError("Production origins must use HTTPS")

    def origin(self, connection):
        if connection.headers.get("origin") not in self.origins:
            fail("origin_denied", 403)

    def validate(self, token):
        if not token or len(token) > 128:
            fail("authentication_required", 401)
        return self.validate_hash(digest(token))

    def validate_hash(self, token_hash):
        """Validate an internal queued-job session reference, never a bearer token."""
        with self.store.engine.connect() as conn:
            row = conn.execute(sa.select(self.store.sessions, self.store.users.c.username,
                self.store.users.c.display_name, self.store.users.c.avatar_version,
                self.store.users.c.roles, self.store.users.c.sites, self.store.users.c.enabled)
                .join(self.store.users, self.store.users.c.id == self.store.sessions.c.user_id)
                .where(self.store.sessions.c.token_hash == token_hash)).mappings().first()
        if not row or row["expires_at"] <= time.time() or not row["enabled"]:
            fail("session_expired", 401)
        return AuthContext(SessionUser(user_id=row["user_id"], username=row["username"],
            display_name=row["display_name"] or row["username"], avatar_version=row["avatar_version"],
            roles=set(row["roles"]), site_ids=set(row["sites"])), row["token_hash"], row["csrf"])

    def request(self, request, mutation=False):
        context = self.validate(request.cookies.get(COOKIE))
        identify(context.user)
        if mutation:
            self.origin(request)
            if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), context.csrf):
                fail("csrf_failed", 403)
        return context

    def login(self, username, password, remote):
        if current := audit_request.get():
            current.username = safe_text(username, 160)
        stamp = time.monotonic()
        key = (remote, username.lower())
        # In-memory limiter is deliberately scoped to the single API process.
        address_key = (remote, "<all>")
        address_history = [v for v in self.attempts.get(address_key, []) if stamp - v < 300]
        if len(address_history) >= 40:
            fail("login_rate_limited", 429)
        self.attempts[address_key] = [*address_history, stamp]
        history = [v for v in self.attempts.get(key, []) if stamp - v < 300]
        if len(history) >= 8:
            fail("login_rate_limited", 429)
        self.attempts[key] = [*history, stamp]
        self.attempts.move_to_end(key)
        while len(self.attempts) > 10000:
            self.attempts.popitem(last=False)
        with self.store.engine.connect() as conn:
            user = conn.execute(sa.select(self.store.users).where(self.store.users.c.username == username)).mappings().first()
        try:
            hasher.verify(user["password_hash"] if user else _dummy_hash, password)
            valid = bool(user and user["enabled"])
        except VerificationError:
            valid = False
        if not valid:
            fail("invalid_credentials", 401)
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with self.store.user_transaction() as conn:
            current_user = conn.execute(sa.select(self.store.users).where(self.store.users.c.id == user["id"])).mappings().first()
            if not current_user or not current_user["enabled"] or current_user["password_hash"] != user["password_hash"]:
                fail("invalid_credentials", 401)
            user = current_user
            conn.execute(self.store.sessions.delete().where(self.store.sessions.c.expires_at <= time.time()))
            conn.execute(self.store.sessions.insert().values(token_hash=digest(token), user_id=user["id"],
                csrf=csrf, expires_at=time.time() + 8 * 3600))
            if hasher.check_needs_rehash(user["password_hash"]):
                conn.execute(self.store.users.update().where(self.store.users.c.id == user["id"]).values(password_hash=hasher.hash(password)))
            identify(SessionUser(user_id=user["id"], username=user["username"], display_name=user["display_name"] or user["username"],
                roles=set(user["roles"]), site_ids=set(user["sites"])))
            self.store.record(user["id"], "login", "succeeded", details={"input": {"username": username}}, conn=conn, status_code=200)
        self.attempts.pop(key, None)
        return token, self.validate(token)

    def check_current_password(self, context, password):
        key = ("reauth", context.user.user_id)
        stamp = time.monotonic()
        history = [v for v in self.attempts.get(key, []) if stamp - v < 300]
        if len(history) >= 8:
            fail("login_rate_limited", 429)
        self.attempts[key] = [*history, stamp]
        with self.store.engine.connect() as conn:
            encoded = conn.execute(sa.select(self.store.users.c.password_hash)
                .where(self.store.users.c.id == context.user.user_id)).scalar_one_or_none()
        try:
            hasher.verify(encoded or _dummy_hash, password)
        except VerificationError:
            fail("current_password_invalid", 403)
        self.attempts.pop(key, None)
        return encoded

    def logout(self, context):
        with self.store.engine.begin() as conn:
            conn.execute(self.store.sessions.delete().where(self.store.sessions.c.token_hash == context.session_hash))
        self.store.record(context.user.user_id, "logout", "succeeded")


def session_response(context):
    from .security import ROLE_PERMISSIONS
    return {**context.user.model_dump(mode="json"), "csrf_token": context.csrf,
        "permissions": sorted({p.value for r in context.user.roles for p in ROLE_PERMISSIONS[r]})}
