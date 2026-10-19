"""Security boundaries for the API and workers.

Authentication and secret storage providers are intentionally injected later;
this module prevents domain code from inventing a default password or reading
credentials from a browser request.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field


class Role(StrEnum):
    VIEWER = "viewer"
    ENGINEER = "engineer"
    SUPERADMIN = "superadmin"


class Permission(StrEnum):
    INVENTORY_READ = "inventory.read"
    INVENTORY_MANAGE = "inventory.manage"
    CREDENTIAL_MANAGE = "credential.manage"
    TERMINAL_OPEN = "terminal.open"
    TELEMETRY_WRITE = "telemetry.write"
    AUDIT_READ = "audit.read"
    USER_MANAGE = "user.manage"
    JOB_CREATE = "job.create"
    CONFIG_PLAN = "config.plan"
    CONFIG_APPLY = "config.apply"
    BACKUP_EXPORT_RAW = "backup.export_raw"


class SessionUser(BaseModel):
    user_id: str
    username: str = ""
    display_name: str
    avatar_version: str | None = None
    roles: set[Role] = Field(default_factory=set)
    site_ids: set[str] = Field(default_factory=set)


class SecretStoreError(RuntimeError):
    pass


class MissingSecret(SecretStoreError):
    pass


class SecretStore(Protocol):
    """Secret manager contract; values never belong in API response models."""

    def get(self, key: str) -> str: ...
    def set(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...


class UnavailableSecretStore:
    """Fail-closed development implementation with no secret persistence."""

    def get(self, key: str) -> str:
        raise MissingSecret(f"secret provider is not configured: {key}")

    def set(self, key: str, value: str) -> None:
        raise SecretStoreError("secret provider is not configured")

    def delete(self, key: str) -> None:
        raise SecretStoreError("secret provider is not configured")


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {Permission.INVENTORY_READ},
    Role.ENGINEER: {Permission.INVENTORY_READ, Permission.INVENTORY_MANAGE, Permission.CREDENTIAL_MANAGE,
        Permission.TELEMETRY_WRITE, Permission.JOB_CREATE, Permission.CONFIG_PLAN, Permission.TERMINAL_OPEN},
    Role.SUPERADMIN: set(Permission),
}


def has_permission(user: SessionUser, permission: Permission, site_id: str) -> bool:
    if permission in {Permission.USER_MANAGE, Permission.AUDIT_READ}:
        return Role.SUPERADMIN in user.roles
    if site_id not in user.site_ids and "*" not in user.site_ids:
        return False
    return any(permission in ROLE_PERMISSIONS[role] for role in user.roles)
