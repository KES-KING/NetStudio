"""Durable inventory, authentication, credentials, measurements and audit records."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa

from .contracts import ManagedDevice
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
            sa.Column("roles", sa.JSON(), nullable=False),
            sa.Column("sites", sa.JSON(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        self.sessions = sa.Table("app_sessions", self.meta,
            sa.Column("token_hash", sa.String(64), primary_key=True),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("app_users.id"), nullable=False),
            sa.Column("csrf", sa.String(128), nullable=False),
            sa.Column("expires_at", sa.Float(), nullable=False))
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
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
        sa.Index("ix_audit_events_time", self.audit.c.occurred_at)

    def record(self, user_id, event, outcome, device_id=None, session_id=None):
        with self.engine.begin() as conn:
            conn.execute(self.audit.insert().values(id=str(uuid4()), user_id=user_id, event=event,
                outcome=outcome, device_id=device_id, session_id=session_id, occurred_at=now()))

    def save_device(self, device: ManagedDevice, conn=None):
        values = {key: getattr(device, key) for key in (
            "id", "name", "management_address", "site", "vendor", "platform", "model", "serial", "read_only", "support_status")}
        values["payload"] = device.model_dump(mode="json", exclude={"credential_configured", "host_key_fingerprint"})
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
            rows = conn.execute(sa.select(self.devices.c.payload).where(self.devices.c.payload.is_not(None))).scalars().all()
            credentials = set(conn.execute(sa.select(self.secrets.c.device_id)).scalars())
            keys = dict(conn.execute(sa.select(self.host_keys.c.device_id, self.host_keys.c.fingerprint)).all())
        return [ManagedDevice.model_validate(row).model_copy(update={
            "credential_configured": row["id"] in credentials, "host_key_fingerprint": keys.get(row["id"])
        }) for row in rows if row.get("support_status") != "demo_fixture"]

    def get_device(self, device_id):
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(self.devices.c.payload, self.secrets.c.device_id.label("credential_id"), self.host_keys.c.fingerprint)
                .outerjoin(self.secrets, self.secrets.c.device_id == self.devices.c.id)
                .outerjoin(self.host_keys, self.host_keys.c.device_id == self.devices.c.id)
                .where(self.devices.c.id == device_id)).mappings().first()
        if not row or not row["payload"] or row["payload"].get("support_status") == "demo_fixture":
            return None
        return ManagedDevice.model_validate(row["payload"]).model_copy(update={"credential_configured": bool(row["credential_id"]), "host_key_fingerprint": row["fingerprint"]})

    def latest(self, device_id):
        with self.engine.connect() as conn:
            return conn.execute(sa.select(self.telemetry.c.payload).where(self.telemetry.c.device_id == device_id)
                .order_by(self.telemetry.c.observed_at.desc()).limit(1)).scalar_one_or_none()
