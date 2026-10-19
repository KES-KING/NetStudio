"""Account administration and self-service profiles. Secrets never enter public projections."""
from io import BytesIO
import time
from typing import Literal
from uuid import uuid4
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import Field, SecretStr, field_validator, model_validator
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from .auth import fail, hasher
from .auditing import decode_cursor, encode_cursor
from .contracts import StrictModel
from .database import now
from .security import Role

UserRole = Literal["viewer", "engineer", "superadmin"]
USERNAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,159}$"


class UserCreate(StrictModel):
    username: str = Field(min_length=1, max_length=160, pattern=USERNAME_PATTERN)
    display_name: str = Field(default="", max_length=100)
    role: UserRole = "viewer"
    sites: list[str] = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=12, max_length=1024)

    @field_validator("sites")
    @classmethod
    def valid_sites(cls, values):
        if any(not value.strip() or len(value) > 160 or any(ord(c) < 32 for c in value) for value in values):
            raise ValueError("invalid_site")
        return sorted(set(value.strip() for value in values))

    @field_validator("display_name")
    @classmethod
    def valid_display_name(cls, value):
        if any(ord(c) < 32 for c in value):
            raise ValueError("invalid_display_name")
        return value.strip()


class UserUpdate(StrictModel):
    username: str | None = Field(default=None, min_length=1, max_length=160, pattern=USERNAME_PATTERN)
    display_name: str | None = Field(default=None, max_length=100)
    role: UserRole | None = None
    sites: list[str] | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    password: SecretStr | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def validate_patch(self):
        for key in self.model_fields_set - {"password"}:
            if getattr(self, key) is None:
                raise ValueError("null_not_allowed")
        if self.sites is not None:
            self.sites = UserCreate.valid_sites(self.sites)
        if self.display_name is not None:
            self.display_name = UserCreate.valid_display_name(self.display_name)
        if self.password and 0 < len(self.password.get_secret_value()) < 12:
            raise ValueError("password_too_short")
        return self


class ProfileUpdate(StrictModel):
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def valid_name(cls, value):
        value = UserCreate.valid_display_name(value)
        if not value:
            raise ValueError("display_name_required")
        return value


class PasswordChange(StrictModel):
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(min_length=12, max_length=1024)


class UserDelete(StrictModel):
    confirmation_username: str = Field(min_length=1, max_length=160)


def public_user(row):
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"] or row["username"],
        "role": row["roles"][0], "sites": row["sites"], "enabled": row["enabled"],
        "created_at": row["created_at"], "updated_at": row["updated_at"], "avatar_version": row["avatar_version"]}


def audit_user(row):
    return {key: public_user(row)[key] for key in ("username", "display_name", "role", "sites", "enabled")}


def normalize_avatar(content, content_type):
    if len(content) > 2 * 1024 * 1024:
        fail("avatar_too_large", 413)
    expected = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}.get(content_type)
    if not expected:
        fail("avatar_invalid", 422)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content), formats=[expected]) as source:
                if max(source.size) > 2048 or getattr(source, "is_animated", False):
                    fail("avatar_dimensions_invalid", 422)
                source.verify()
            with Image.open(BytesIO(content), formats=[expected]) as source:
                source.load()
                pixels = ImageOps.exif_transpose(source).convert("RGBA")
                pixels.thumbnail((256, 256), Image.Resampling.LANCZOS)
                clean = Image.new("RGBA", pixels.size)
                clean.paste(pixels)
                output = BytesIO()
                clean.save(output, format="PNG")
                return output.getvalue(), clean.width, clean.height
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        fail("avatar_invalid", 422)


class Users:
    def __init__(self, store):
        self.store = store

    def _row(self, conn, identifier):
        row = conn.execute(sa.select(self.store.users).where(self.store.users.c.id == identifier)).mappings().first()
        if not row:
            fail("user_not_found", 404)
        return row

    def authorize(self, conn, auth, admin=False):
        user = self._row(conn, auth.user.user_id)
        valid = conn.execute(sa.select(self.store.sessions.c.token_hash).where(
            self.store.sessions.c.token_hash == auth.session_hash,
            self.store.sessions.c.user_id == user["id"], self.store.sessions.c.expires_at > time.time())).first()
        if not valid or not user["enabled"]:
            fail("session_expired", 401)
        if admin and Role.SUPERADMIN not in user["roles"]:
            fail("forbidden", 403)
        return user

    def get(self, identifier):
        with self.store.engine.connect() as conn:
            return public_user(self._row(conn, identifier))

    def list(self, *, q="", role=None, limit=50, cursor=None):
        table = self.store.users
        query = sa.select(table)
        if q:
            query = query.where(sa.or_(sa.func.lower(table.c.username).contains(q.lower(), autoescape=True),
                sa.func.lower(table.c.display_name).contains(q.lower(), autoescape=True)))
        if role:
            query = query.where(table.c.roles[0].as_string() == role)
        if cursor:
            username, identifier = decode_cursor(cursor)
            query = query.where(sa.or_(table.c.username > username,
                sa.and_(table.c.username == username, table.c.id > identifier)))
        with self.store.engine.connect() as conn:
            rows = list(conn.execute(query.order_by(table.c.username, table.c.id).limit(limit + 1)).mappings())
        more = len(rows) > limit
        rows = rows[:limit]
        return {"items": [public_user(row) for row in rows],
            "next_cursor": encode_cursor([rows[-1]["username"], rows[-1]["id"]]) if more else None}

    def create(self, auth, value):
        encoded = hasher.hash(value.password.get_secret_value())
        identifier = str(uuid4())
        try:
            with self.store.user_transaction() as conn:
                self.authorize(conn, auth, admin=True)
                conn.execute(self.store.users.insert().values(id=identifier, username=value.username,
                    display_name=value.display_name or value.username[:100], password_hash=encoded,
                    roles=[value.role], sites=value.sites, enabled=True, created_at=now(), updated_at=now()))
                row = self._row(conn, identifier)
                self.store.record(auth.user.user_id, "user.created", "succeeded", conn=conn,
                    target_type="user", target_id=identifier, details={"input": audit_user(row)}, status_code=201)
                return public_user(row)
        except IntegrityError:
            fail("username_taken", 409)

    def _protect(self, conn, auth, row, values, deleting=False):
        roles = values.get("roles", row["roles"])
        enabled = values.get("enabled", row["enabled"])
        losing_admin = deleting or not enabled or Role.SUPERADMIN not in roles
        if row["enabled"] and Role.SUPERADMIN in row["roles"] and losing_admin:
            active = conn.execute(sa.select(self.store.users.c.roles).where(self.store.users.c.enabled.is_(True))).scalars()
            if sum(Role.SUPERADMIN in roles for roles in active) <= 1:
                fail("last_superadmin", 409)
        if row["id"] == auth.user.user_id and (deleting or not enabled or Role.SUPERADMIN not in roles):
            fail("self_lockout", 409)

    def update(self, auth, identifier, value):
        values = value.model_dump(exclude_unset=True, exclude={"password", "role"})
        if value.role is not None:
            values["roles"] = [value.role]
        if value.password and value.password.get_secret_value():
            if identifier == auth.user.user_id:
                fail("self_password_use_profile", 409)
            values["password_hash"] = hasher.hash(value.password.get_secret_value())
        try:
            with self.store.user_transaction() as conn:
                self.authorize(conn, auth, admin=True)
                row = self._row(conn, identifier)
                self._protect(conn, auth, row, values)
                security_changed = any(key in values and values[key] != row[key] for key in ("password_hash", "roles", "sites", "enabled", "username"))
                if values:
                    conn.execute(self.store.users.update().where(self.store.users.c.id == identifier).values(**values, updated_at=now()))
                if security_changed:
                    conn.execute(self.store.sessions.delete().where(self.store.sessions.c.user_id == identifier))
                updated = self._row(conn, identifier)
                self.store.record(auth.user.user_id, "user.updated", "succeeded", conn=conn,
                    target_type="user", target_id=identifier, status_code=200, details={"before": audit_user(row),
                        "after": audit_user(updated), "password_changed": "password_hash" in values})
                return public_user(updated), security_changed
        except IntegrityError:
            fail("username_taken", 409)

    def delete(self, auth, identifier, confirmation):
        with self.store.user_transaction() as conn:
            self.authorize(conn, auth, admin=True)
            row = self._row(conn, identifier)
            if row["username"] != confirmation:
                fail("confirmation_mismatch", 409)
            self._protect(conn, auth, row, {}, deleting=True)
            conn.execute(self.store.sessions.delete().where(self.store.sessions.c.user_id == identifier))
            conn.execute(self.store.avatars.delete().where(self.store.avatars.c.user_id == identifier))
            conn.execute(self.store.users.delete().where(self.store.users.c.id == identifier))
            self.store.record(auth.user.user_id, "user.deleted", "succeeded", conn=conn,
                target_type="user", target_id=identifier, details={"before": audit_user(row)}, status_code=200)

    def profile(self, auth, value):
        with self.store.user_transaction() as conn:
            row = self.authorize(conn, auth)
            conn.execute(self.store.users.update().where(self.store.users.c.id == row["id"])
                .values(display_name=value.display_name, updated_at=now()))
            self.store.record(row["id"], "profile.updated", "succeeded", conn=conn, target_type="user", target_id=row["id"],
                details={"before": {"display_name": row["display_name"]}, "after": {"display_name": value.display_name}}, status_code=200)
            return public_user(self._row(conn, row["id"]))

    def password(self, auth, value, authenticator):
        previous_hash = authenticator.check_current_password(auth, value.current_password.get_secret_value())
        encoded = hasher.hash(value.new_password.get_secret_value())
        with self.store.user_transaction() as conn:
            row = self.authorize(conn, auth)
            if row["password_hash"] != previous_hash:
                fail("password_changed_retry", 409)
            conn.execute(self.store.users.update().where(self.store.users.c.id == row["id"])
                .values(password_hash=encoded, updated_at=now()))
            conn.execute(self.store.sessions.delete().where(self.store.sessions.c.user_id == row["id"]))
            self.store.record(row["id"], "password.changed", "succeeded", conn=conn,
                target_type="user", target_id=row["id"], details={"password_changed": True}, status_code=200)

    def avatar(self, auth, normalized=None):
        with self.store.user_transaction() as conn:
            row = self.authorize(conn, auth)
            conn.execute(self.store.avatars.delete().where(self.store.avatars.c.user_id == row["id"]))
            details = {"avatar_changed": True}
            if normalized:
                png, width, height = normalized
                conn.execute(self.store.avatars.insert().values(user_id=row["id"], png=png))
                details.update(bytes=len(png), width=width, height=height)
            conn.execute(self.store.users.update().where(self.store.users.c.id == row["id"])
                .values(avatar_version=str(uuid4()) if normalized else None, updated_at=now()))
            self.store.record(row["id"], "avatar.updated" if normalized else "avatar.deleted", "succeeded", conn=conn,
                target_type="user", target_id=row["id"], details=details, status_code=200)
            return public_user(self._row(conn, row["id"]))
