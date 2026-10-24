"""Durable inventory, authentication, credentials, measurements and audit records."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa

from .contracts import ManagedDevice
from .auditing import audit_request, safe_details, safe_text
from .repositories import SqlAlchemyJobRepository


def now():
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, url: str | None = None):
        url = url or os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is required. Run migrations before starting the API.")
        self.jobs_repository = SqlAlchemyJobRepository(url)
        self.engine = self.jobs_repository.engine
        self.meta = self.jobs_repository.metadata
        self.devices = self.jobs_repository.devices
        self.devices.append_column(sa.Column("payload", sa.JSON()))
        self.users = sa.Table("app_users", self.meta,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("username", sa.String(160), nullable=False, unique=True),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("display_name", sa.String(100), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.Column("avatar_version", sa.String(36)),
            sa.Column("roles", sa.JSON(), nullable=False),
            sa.Column("sites", sa.JSON(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        self.sessions = sa.Table("app_sessions", self.meta,
            sa.Column("token_hash", sa.String(64), primary_key=True),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("app_users.id"), nullable=False),
            sa.Column("csrf", sa.String(128), nullable=False),
            sa.Column("expires_at", sa.Float(), nullable=False))
        sa.Index("ix_app_sessions_user", self.sessions.c.user_id)
        self.avatars = sa.Table("user_avatars", self.meta,
            sa.Column("user_id", sa.String(64), sa.ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("png", sa.LargeBinary(), nullable=False))
        self.topology_boards = sa.Table("topology_boards", self.meta,
            sa.Column("user_id", sa.String(64), sa.ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
        self.secrets = sa.Table("device_secrets", self.meta,
            sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), primary_key=True),
            sa.Column("key_id", sa.String(80), nullable=False),
            sa.Column("nonce", sa.LargeBinary(), nullable=False),
            sa.Column("ciphertext", sa.LargeBinary(), nullable=False))
        self.host_keys = sa.Table("device_host_keys", self.meta,
            sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), primary_key=True),
            sa.Column("public_key", sa.Text(), nullable=False),
            sa.Column("fingerprint", sa.String(160), nullable=False))
        self.telemetry = sa.Table("device_telemetry", self.meta,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), nullable=False),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.UniqueConstraint("device_id", "observed_at", name="uq_device_telemetry_time"))
        sa.Index("ix_device_telemetry_time", self.telemetry.c.device_id, self.telemetry.c.observed_at)
        self.audit = sa.Table("audit_events", self.meta,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("user_id", sa.String(160), nullable=False),
            sa.Column("device_id", sa.String(64)),
            sa.Column("event", sa.String(80), nullable=False),
            sa.Column("outcome", sa.String(100), nullable=False),
            sa.Column("session_id", sa.String(64)),
            sa.Column("username", sa.String(160)),
            sa.Column("roles", sa.JSON()),
            sa.Column("target_type", sa.String(40)),
            sa.Column("target_id", sa.String(160)),
            sa.Column("request_id", sa.String(36)),
            sa.Column("method", sa.String(10)),
            sa.Column("route", sa.String(200)),
            sa.Column("remote_address", sa.String(100)),
            sa.Column("user_agent", sa.String(256)),
            sa.Column("status_code", sa.Integer()),
            sa.Column("duration_ms", sa.Integer()),
            sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
        sa.Index("ix_audit_events_time", self.audit.c.occurred_at)
        sa.Index("ix_audit_cursor", self.audit.c.occurred_at, self.audit.c.id)
        sa.Index("ix_audit_actor_time", self.audit.c.user_id, self.audit.c.occurred_at, self.audit.c.id)
        sa.Index("ix_audit_event_time", self.audit.c.event, self.audit.c.occurred_at, self.audit.c.id)
        sa.Index("ix_audit_target_time", self.audit.c.target_id, self.audit.c.occurred_at, self.audit.c.id)
        from .automation_schema_v1 import define_tables
        for name, table in define_tables(self.meta).items():
            setattr(self, name, table)
        from .system_schema_v1 import define_tables as system_tables
        for name, table in system_tables(self.meta).items():
            setattr(self, name, table)
        from .network_probe_schema_v1 import define_tables as network_probe_tables
        for name, table in network_probe_tables(self.meta).items():
            setattr(self, name, table)
        from .compatibility_schema_v1 import define_tables as compatibility_tables
        for name, table in compatibility_tables(self.meta).items():
            setattr(self, name, table)
        from .controller_schema_v1 import define_tables as controller_tables
        for name, table in controller_tables(self.meta).items():
            setattr(self, name, table)

    @contextmanager
    def user_transaction(self):
        """Serialize account changes and login finalization, including last-admin checks."""
        with self.engine.connect() as conn:
            if conn.dialect.name == "sqlite":
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                conn.begin()
                conn.execute(sa.text("SELECT pg_advisory_xact_lock(730201904)"))
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def record(self, user_id, event, outcome, device_id=None, session_id=None, *, details=None,
               target_type=None, target_id=None, conn=None, status_code=None, actor_name=None, actor_roles=None):
        current = audit_request.get()
        metadata = {}
        if current:
            current.recorded = True
            metadata = {key: getattr(current, key) for key in (
                "request_id", "username", "roles", "method", "route", "remote_address", "user_agent", "status_code", "duration_ms")}
            metadata["duration_ms"] = current.duration_ms if current.duration_ms is not None else round((time.monotonic() - current.started) * 1000)
            if current.user_id != user_id:
                metadata.pop("username", None)
                metadata.pop("roles", None)
        if actor_name:
            metadata["username"] = safe_text(actor_name, 160)
        if actor_roles is not None:
            metadata["roles"] = list(actor_roles)
        if status_code is not None:
            metadata["status_code"] = status_code
        values = dict(id=str(uuid4()), user_id=safe_text(user_id, 160), event=event,
            outcome=safe_text(outcome, 100), device_id=device_id, session_id=session_id, occurred_at=now(),
            target_type=target_type or ("device" if device_id else None), target_id=target_id or device_id,
            details=safe_details(details or {}), **metadata)
        def write(connection):
            if "username" not in values:
                actor = connection.execute(sa.select(self.users.c.username, self.users.c.roles).where(self.users.c.id == user_id)).mappings().first()
                if actor:
                    values.update(username=safe_text(actor["username"], 160), roles=actor["roles"])
            connection.execute(self.audit.insert().values(**values))
        if conn is not None:
            write(conn)
        else:
            with self.engine.begin() as connection:
                write(connection)

    def save_device(self, device: ManagedDevice, conn=None):
        values = {key: getattr(device, key) for key in (
            "id", "name", "management_address", "site", "vendor", "platform", "model", "serial", "read_only", "support_status")}
        values["payload"] = device.model_dump(mode="json", exclude={
            "credential_configured", "host_key_fingerprint", "snmp_configured", "api_configured",
            "configured_profile_id", "resolved_profile_id", "profile_revision",
            "management_mode", "profile_resolution_status",
        })
        def save(connection):
            if connection.execute(sa.select(self.devices.c.id).where(self.devices.c.id == device.id)).first():
                connection.execute(self.devices.update().where(self.devices.c.id == device.id).values(**values))
            else:
                connection.execute(self.devices.insert().values(**values))
        if conn is not None:
            save(conn)
        else:
            with self.engine.begin() as connection:
                save(connection)

    def list_devices(self):
        with self.engine.connect() as conn:
            rows = conn.execute(sa.select(
                self.devices.c.payload, self.driver_bindings.c.configured_profile_id,
                self.driver_bindings.c.resolved_profile_id,
                self.driver_bindings.c.profile_revision,
                self.driver_bindings.c.management_mode,
                self.driver_bindings.c.resolution_status,
            ).outerjoin(
                self.driver_bindings,
                self.driver_bindings.c.device_id == self.devices.c.id,
            ).where(self.devices.c.payload.is_not(None))).mappings().all()
            credentials = set(conn.execute(sa.select(self.secrets.c.device_id)).scalars())
            keys = dict(conn.execute(sa.select(self.host_keys.c.device_id, self.host_keys.c.fingerprint)).all())
            snmp = set(conn.execute(sa.select(self.protocol_secrets.c.device_id)
                .where(self.protocol_secrets.c.protocol == "snmp")).scalars())
            api = set(conn.execute(sa.select(self.device_controller_bindings.c.device_id)
                .join(self.api_controller_secrets,
                    self.api_controller_secrets.c.controller_id == self.device_controller_bindings.c.controller_id)
                .join(self.api_controllers,
                    self.api_controllers.c.id == self.device_controller_bindings.c.controller_id)
                .where(self.api_controllers.c.enabled.is_(True))).scalars())
        result = []
        for row in rows:
            payload = row["payload"]
            if payload.get("support_status") == "demo_fixture":
                continue
            result.append(ManagedDevice.model_validate(payload).model_copy(update={
                "credential_configured": payload["id"] in credentials,
                "host_key_fingerprint": keys.get(payload["id"]),
                "snmp_configured": payload["id"] in snmp,
                "api_configured": payload["id"] in api,
                "configured_profile_id": row["configured_profile_id"],
                "resolved_profile_id": row["resolved_profile_id"],
                "profile_revision": row["profile_revision"],
                "management_mode": row["management_mode"] or "unknown",
                "profile_resolution_status": row["resolution_status"] or "unresolved",
            }))
        return result

    def get_device(self, device_id):
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(
                self.devices.c.payload,
                self.secrets.c.device_id.label("credential_id"),
                self.host_keys.c.fingerprint,
                self.driver_bindings.c.configured_profile_id,
                self.driver_bindings.c.resolved_profile_id,
                self.driver_bindings.c.profile_revision,
                self.driver_bindings.c.management_mode,
                self.driver_bindings.c.resolution_status,
            )
                .outerjoin(self.secrets, self.secrets.c.device_id == self.devices.c.id)
                .outerjoin(self.host_keys, self.host_keys.c.device_id == self.devices.c.id)
                .outerjoin(self.driver_bindings, self.driver_bindings.c.device_id == self.devices.c.id)
                .where(self.devices.c.id == device_id)).mappings().first()
            snmp = conn.execute(sa.select(self.protocol_secrets.c.device_id).where(
                self.protocol_secrets.c.device_id == device_id, self.protocol_secrets.c.protocol == "snmp")).first()
            api = conn.execute(sa.select(self.device_controller_bindings.c.device_id)
                .join(self.api_controller_secrets,
                    self.api_controller_secrets.c.controller_id == self.device_controller_bindings.c.controller_id)
                .join(self.api_controllers,
                    self.api_controllers.c.id == self.device_controller_bindings.c.controller_id)
                .where(self.device_controller_bindings.c.device_id == device_id,
                    self.api_controllers.c.enabled.is_(True))).first()
        if not row or not row["payload"] or row["payload"].get("support_status") == "demo_fixture":
            return None
        return ManagedDevice.model_validate(row["payload"]).model_copy(update={
            "credential_configured": bool(row["credential_id"]),
            "host_key_fingerprint": row["fingerprint"], "snmp_configured": bool(snmp),
            "api_configured": bool(api),
            "configured_profile_id": row["configured_profile_id"],
            "resolved_profile_id": row["resolved_profile_id"],
            "profile_revision": row["profile_revision"],
            "management_mode": row["management_mode"] or "unknown",
            "profile_resolution_status": row["resolution_status"] or "unresolved",
        })

    def get_driver_binding(self, device_id, conn=None):
        def read(connection):
            row = connection.execute(sa.select(self.driver_bindings).where(
                self.driver_bindings.c.device_id == device_id
            )).mappings().first()
            return dict(row) if row else None
        if conn is not None:
            return read(conn)
        with self.engine.connect() as connection:
            return read(connection)

    @staticmethod
    def with_driver_binding(device, binding):
        if not binding:
            return device
        return device.model_copy(update={
            "configured_profile_id": binding["configured_profile_id"],
            "resolved_profile_id": binding["resolved_profile_id"],
            "profile_revision": binding["profile_revision"],
            "management_mode": binding["management_mode"] or "unknown",
            "profile_resolution_status": binding["resolution_status"] or "unresolved",
        })

    def save_driver_binding(self, values, conn):
        condition = self.driver_bindings.c.device_id == values["device_id"]
        if not conn.execute(self.driver_bindings.update().where(condition).values(**values)).rowcount:
            conn.execute(self.driver_bindings.insert().values(**values))

    def latest(self, device_id):
        with self.engine.connect() as conn:
            current = conn.execute(sa.select(self.latest_telemetry.c.payload)
                .where(self.latest_telemetry.c.device_id == device_id)).scalar_one_or_none()
            external = conn.execute(sa.select(self.telemetry.c.payload).where(self.telemetry.c.device_id == device_id)
                .order_by(self.telemetry.c.observed_at.desc()).limit(1)).scalar_one_or_none()
            candidates = [value for value in (current, external) if value]
            return max(candidates, key=lambda value: datetime.fromisoformat(value["observed_at"].replace("Z", "+00:00"))) if candidates else None
