"""Site-scoped, URL-free controller registration and secret lifecycle API."""
from __future__ import annotations

from datetime import datetime, timezone
from ipaddress import ip_address, ip_network
import os
import re
from typing import Literal
from uuid import uuid4

from cryptography import x509
from fastapi import Request
from pydantic import Field, SecretStr, field_validator, model_validator
import sqlalchemy as sa

from .auth import fail
from .contracts import StrictModel
from .controller_transport import REQUIRED_SCOPES
from .database import now
from .driver_profiles import REGISTRY
from .security import Permission, has_permission


ControllerVendor = Literal["meraki", "unifi", "fortigate", "omada", "omada_pro"]

PROFILE_VENDORS = {
    "cisco_meraki_ms": {"meraki"},
    "fortinet_fortiswitch_fortilink": {"fortigate"},
    "ubiquiti_unifi_switch": {"unifi"},
    "ubiquiti_unifi_no_snmp": {"unifi"},
    "tplink_omada_managed": {"omada"},
    "tplink_omada_pro": {"omada_pro"},
}


def _address(value: str) -> str:
    address = ip_address(value)
    address = getattr(address, "ipv4_mapped", None) or address
    if address.is_unspecified or address.is_multicast or address.is_link_local or "%" in value:
        raise ValueError("invalid_controller_address")
    try:
        allowed = [ip_network(item.strip(), strict=False) for item in
                   os.getenv("NETSTUDIO_CONTROLLER_ALLOWED_CIDRS", "").split(",") if item.strip()]
    except ValueError as error:
        raise ValueError("invalid_controller_network_policy") from error
    # Optional installation-wide ceiling; loopback always requires explicit opt-in.
    if (allowed or address.is_loopback) and not any(address in network for network in allowed):
        raise ValueError("controller_address_not_allowed")
    return str(address)


class ControllerRegistration(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    vendor: ControllerVendor
    site: str = Field(min_length=1, max_length=160)
    endpoint_kind: Literal["cloud", "local"]
    address: str | None = Field(default=None, max_length=64)
    port: int | None = Field(default=None, ge=1, le=65535)
    cloud_region: Literal["global", "canada", "india", "china"] | None = None
    ca_pem: str | None = Field(default=None, max_length=32768)
    external_scope_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.:@/-]+$")
    external_site_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.:@/-]+$")
    enabled: bool = True

    @model_validator(mode="after")
    def endpoint_policy(self):
        if self.vendor == "meraki":
            if self.endpoint_kind != "cloud" or self.address or self.port or self.ca_pem:
                raise ValueError("meraki_fixed_cloud_endpoint_required")
            self.cloud_region = self.cloud_region or "global"
        else:
            if self.endpoint_kind != "local" or not self.address or not self.port:
                raise ValueError("local_controller_ip_and_port_required")
            self.address = _address(self.address)
            if self.cloud_region:
                raise ValueError("cloud_region_not_allowed")
        if self.ca_pem:
            if "PRIVATE KEY" in self.ca_pem:
                raise ValueError("controller_ca_private_key_forbidden")
            try:
                x509.load_pem_x509_certificate(self.ca_pem.encode())
            except ValueError as error:
                raise ValueError("invalid_controller_ca") from error
        return self


class ControllerCredential(StrictModel):
    auth_kind: Literal["bearer", "api_key", "access_token"]
    token: SecretStr = Field(min_length=16, max_length=16384)
    scopes: list[str] = Field(min_length=1, max_length=16)
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def scopes_are_bounded(cls, value):
        if len(set(value)) != len(value) or any(not re.fullmatch(r"[a-z][a-z0-9:-]{1,63}", item) for item in value):
            raise ValueError("invalid_controller_scopes")
        return value

    @field_validator("expires_at")
    @classmethod
    def expiry_has_timezone(cls, value):
        if value and value.tzinfo is None:
            raise ValueError("controller_token_expiry_timezone_required")
        return value


class ControllerBinding(StrictModel):
    controller_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    external_device_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.:@/-]+$")


def _view(row, secret=None, bindings=0):
    return {
        "id": row["id"], "name": row["name"], "vendor": row["vendor"],
        "site": row["site"], "endpoint_kind": row["endpoint_kind"],
        "address": row["address"], "port": row["port"],
        "cloud_region": row["cloud_region"],
        "custom_ca_configured": bool(row["ca_pem"]),
        "external_scope_id": row["external_scope_id"],
        "external_site_id": row["external_site_id"], "enabled": row["enabled"],
        "revision": row["revision"], "credential_configured": bool(secret),
        "credential": ({
            "auth_kind": secret["auth_kind"], "scopes": list(secret["scopes"]),
            "expires_at": secret["expires_at"],
        } if secret else None),
        "binding_count": bindings,
    }


def install(app, context, device_for):
    def controller_for(request, controller_id, permission=Permission.INVENTORY_READ, mutation=False):
        store = app.state.store
        auth = context(request, mutation)
        with store.engine.connect() as conn:
            row = conn.execute(sa.select(store.api_controllers).where(
                store.api_controllers.c.id == controller_id)).mappings().first()
        if not row or not has_permission(auth.user, permission, row["site"]):
            fail("controller_not_found_or_forbidden", 404)
        return auth, dict(row)

    @app.get("/api/v1/controllers")
    def controllers(request: Request):
        store = app.state.store
        auth = context(request)
        with store.engine.connect() as conn:
            rows = conn.execute(sa.select(store.api_controllers).order_by(
                store.api_controllers.c.site, store.api_controllers.c.name)).mappings().all()
            secrets = {row["controller_id"]: row for row in conn.execute(
                sa.select(store.api_controller_secrets)).mappings()}
            counts = dict(conn.execute(sa.select(
                store.device_controller_bindings.c.controller_id, sa.func.count()
            ).group_by(store.device_controller_bindings.c.controller_id)).all())
        return [_view(row, secrets.get(row["id"]), counts.get(row["id"], 0))
                for row in rows if has_permission(auth.user, Permission.INVENTORY_READ, row["site"])]

    @app.post("/api/v1/controllers", status_code=201)
    def create_controller(value: ControllerRegistration, request: Request):
        store = app.state.store
        auth = context(request, True)
        if not has_permission(auth.user, Permission.CREDENTIAL_MANAGE, value.site):
            fail("forbidden", 403)
        identifier = str(uuid4())
        values = value.model_dump()
        try:
            with store.engine.begin() as conn:
                conn.execute(store.api_controllers.insert().values(
                    id=identifier, revision=1, created_at=now(), updated_at=now(),
                    updated_by=auth.user.user_id, **values,
                ))
                store.record(auth.user.user_id, "controller.created", "succeeded",
                    target_type="controller", target_id=identifier,
                    details={"vendor": value.vendor, "site": value.site,
                             "endpoint_kind": value.endpoint_kind}, conn=conn)
        except sa.exc.IntegrityError:
            fail("controller_name_conflict", 409)
        return next(item for item in controllers(request) if item["id"] == identifier)

    @app.put("/api/v1/controllers/{controller_id}")
    def update_controller(controller_id: str, value: ControllerRegistration, request: Request):
        store = app.state.store
        auth, current = controller_for(request, controller_id, Permission.CREDENTIAL_MANAGE, True)
        if not has_permission(auth.user, Permission.CREDENTIAL_MANAGE, value.site):
            fail("forbidden", 403)
        with store.engine.begin() as conn:
            bindings = conn.execute(sa.select(store.device_controller_bindings.c.device_id).where(
                store.device_controller_bindings.c.controller_id == controller_id)).scalars().all()
            immutable = ("vendor", "site", "external_scope_id", "external_site_id")
            if bindings and any(current[key] != getattr(value, key) for key in immutable):
                fail("bound_controller_identity_immutable", 409)
            conn.execute(store.api_controllers.update().where(
                store.api_controllers.c.id == controller_id).values(
                    **value.model_dump(), revision=current["revision"] + 1,
                    updated_at=now(), updated_by=auth.user.user_id,
                ))
            from .automation_api import changed
            for device_id in bindings:
                changed(store, device_id, conn)
            store.record(auth.user.user_id, "controller.updated", "succeeded",
                target_type="controller", target_id=controller_id,
                details={"vendor": value.vendor, "site": value.site,
                         "endpoint_kind": value.endpoint_kind}, conn=conn)
        return next(item for item in controllers(request) if item["id"] == controller_id)

    @app.put("/api/v1/controllers/{controller_id}/credentials")
    def controller_credentials(controller_id: str, value: ControllerCredential, request: Request):
        store = app.state.store
        auth, controller = controller_for(request, controller_id, Permission.CREDENTIAL_MANAGE, True)
        if value.expires_at and value.expires_at <= datetime.now(timezone.utc):
            fail("controller_token_expired", 422)
        expected_auth = {
            "unifi": "api_key", "omada": "access_token", "omada_pro": "access_token",
        }.get(controller["vendor"], "bearer")
        if value.auth_kind != expected_auth:
            fail("controller_auth_kind_invalid", 422)
        required = REQUIRED_SCOPES[controller["vendor"]]
        if not set(value.scopes) <= required:
            fail("controller_scope_not_read_only", 422)
        if not required <= set(value.scopes):
            fail("controller_scope_insufficient", 422)
        secret = {"token": value.token.get_secret_value()}
        with store.engine.begin() as conn:
            app.state.vault.save_controller(
                controller_id, secret, auth_kind=value.auth_kind,
                scopes=value.scopes, expires_at=value.expires_at, conn=conn,
            )
            affected = conn.execute(sa.select(store.device_controller_bindings.c.device_id).where(
                store.device_controller_bindings.c.controller_id == controller_id)).scalars().all()
            from .automation_api import changed
            for device_id in affected:
                changed(store, device_id, conn)
            store.record(auth.user.user_id, "controller.credentials.updated", "succeeded",
                target_type="controller", target_id=controller_id,
                details={"auth_kind": value.auth_kind, "scopes": value.scopes,
                         "expires_at": value.expires_at.isoformat() if value.expires_at else None}, conn=conn)
        secret.clear()
        return {"credential_configured": True}

    @app.delete("/api/v1/controllers/{controller_id}/credentials")
    def delete_controller_credentials(controller_id: str, request: Request):
        store = app.state.store
        auth, _ = controller_for(request, controller_id, Permission.CREDENTIAL_MANAGE, True)
        with store.engine.begin() as conn:
            affected = conn.execute(sa.select(store.device_controller_bindings.c.device_id).where(
                store.device_controller_bindings.c.controller_id == controller_id)).scalars().all()
            conn.execute(store.api_controller_secrets.delete().where(
                store.api_controller_secrets.c.controller_id == controller_id))
            from .automation_api import changed
            for device_id in affected:
                changed(store, device_id, conn)
            store.record(auth.user.user_id, "controller.credentials.revoked", "succeeded",
                target_type="controller", target_id=controller_id, conn=conn)
        return {"credential_configured": False}

    @app.delete("/api/v1/controllers/{controller_id}")
    def delete_controller(controller_id: str, request: Request):
        store = app.state.store
        auth, _ = controller_for(request, controller_id, Permission.CREDENTIAL_MANAGE, True)
        with store.engine.begin() as conn:
            if conn.execute(sa.select(store.device_controller_bindings.c.device_id).where(
                store.device_controller_bindings.c.controller_id == controller_id)).first():
                fail("controller_has_device_bindings", 409)
            # Do not depend on per-engine foreign-key cascade settings for
            # credential erasure (notably SQLite test/development databases).
            conn.execute(store.api_controller_secrets.delete().where(
                store.api_controller_secrets.c.controller_id == controller_id))
            conn.execute(store.api_controllers.delete().where(store.api_controllers.c.id == controller_id))
            store.record(auth.user.user_id, "controller.deleted", "succeeded",
                target_type="controller", target_id=controller_id, conn=conn)
        return {"deleted": True}

    @app.get("/api/v1/devices/{device_id}/controller-binding")
    def get_binding(device_id: str, request: Request):
        store = app.state.store
        _, device = device_for(request, device_id)
        with store.engine.connect() as conn:
            row = conn.execute(sa.select(store.device_controller_bindings).where(
                store.device_controller_bindings.c.device_id == device.id)).mappings().first()
        return dict(row) if row else None

    @app.put("/api/v1/devices/{device_id}/controller-binding")
    def bind_controller(device_id: str, value: ControllerBinding, request: Request):
        store = app.state.store
        auth, device = device_for(request, device_id, Permission.CREDENTIAL_MANAGE, True)
        _, controller = controller_for(request, value.controller_id, Permission.CREDENTIAL_MANAGE, True)
        if controller["site"] != device.site:
            fail("controller_device_site_mismatch", 409)
        profile_id = device.configured_profile_id or device.resolved_profile_id
        profile = REGISTRY.profile(profile_id) if profile_id else None
        if not profile or controller["vendor"] not in PROFILE_VENDORS.get(profile.id, set()):
            fail("controller_profile_vendor_mismatch", 409)
        values = {
            "device_id": device.id, "controller_id": value.controller_id,
            "controller_vendor": controller["vendor"], "site": controller["site"],
            "external_device_id": value.external_device_id,
            "external_site_id": controller["external_site_id"],
            "updated_at": now(), "updated_by": auth.user.user_id,
        }
        try:
            with store.engine.begin() as conn:
                current = conn.execute(sa.select(store.device_controller_bindings).where(
                    store.device_controller_bindings.c.device_id == device.id).with_for_update()).mappings().first()
                values["binding_revision"] = (current["binding_revision"] + 1) if current else 1
                if current:
                    conn.execute(store.device_controller_bindings.update().where(
                        store.device_controller_bindings.c.device_id == device.id).values(**values))
                else:
                    conn.execute(store.device_controller_bindings.insert().values(**values))
                from .automation_api import changed
                changed(store, device.id, conn)
                store.record(auth.user.user_id, "controller.device.bound", "succeeded", device.id,
                    details={"controller_id": value.controller_id,
                             "external_device_id": value.external_device_id}, conn=conn)
        except sa.exc.IntegrityError:
            fail("controller_external_device_already_bound", 409)
        return get_binding(device_id, request)

    @app.delete("/api/v1/devices/{device_id}/controller-binding")
    def unbind_controller(device_id: str, request: Request):
        store = app.state.store
        auth, device = device_for(request, device_id, Permission.CREDENTIAL_MANAGE, True)
        with store.engine.begin() as conn:
            conn.execute(store.device_controller_bindings.delete().where(
                store.device_controller_bindings.c.device_id == device.id))
            from .automation_api import changed
            changed(store, device.id, conn)
            store.record(auth.user.user_id, "controller.device.unbound", "succeeded", device.id, conn=conn)
        return {"api_configured": False}
