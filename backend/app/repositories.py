"""Persistence adapters for the durable job boundary.

The API can run without PostgreSQL for fixture development, but the same
orchestrator can be pointed at the migrated PostgreSQL ``jobs`` table through
``DATABASE_URL``. Device sessions never carry credentials in these records.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.pool import StaticPool

from .models import Device, Job


class JobRepository(Protocol):
    def insert(self, job: Job) -> Job: ...
    def get(self, job_id: UUID) -> Job | None: ...
    def update(self, job: Job) -> Job: ...
    def ensure_device(self, device: Device) -> None: ...
    def ping(self) -> bool: ...


class MemoryJobRepository:
    """Thread-safe repository used when no DATABASE_URL is configured."""

    def __init__(self) -> None:
        from threading import Lock

        self._jobs: dict[UUID, Job] = {}
        self._lock = Lock()

    def insert(self, job: Job) -> Job:
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: UUID) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job: Job) -> Job:
        with self._lock:
            if job.id not in self._jobs:
                raise KeyError(str(job.id))
            self._jobs[job.id] = job
        return job

    def ensure_device(self, device: Device) -> None:
        """The in-memory profile already reads devices from the fixture."""

    def ping(self) -> bool:
        return True


class SqlAlchemyJobRepository:
    """PostgreSQL repository for jobs created by Alembic ``0001_initial``.

    The adapter opens a short transaction per state transition. It does not
    hold a database lock while a device operation runs.
    """

    def __init__(self, database_url: str) -> None:
        engine_options = {"pool_pre_ping": True, "hide_parameters": True}
        if database_url.startswith("sqlite"):
            engine_options.update({"connect_args": {"check_same_thread": False}})
            # Only an in-memory DB needs a single shared connection. File-backed
            # tests/jobs must not commit/rollback each other's transactions.
            if sa.engine.make_url(database_url).database in {None, "", ":memory:"}:
                engine_options["poolclass"] = StaticPool
        self.engine = sa.create_engine(database_url, **engine_options)
        self.metadata = sa.MetaData()
        self.devices = sa.Table(
            "devices",
            self.metadata,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("management_address", sa.String(255), nullable=False),
            sa.Column("site", sa.String(160), nullable=False),
            sa.Column("vendor", sa.String(120), nullable=False),
            sa.Column("platform", sa.String(120), nullable=False),
            sa.Column("model", sa.String(160), nullable=False),
            sa.Column("serial", sa.String(160), nullable=False),
            sa.Column("read_only", sa.Boolean(), nullable=False),
            sa.Column("support_status", sa.String(40), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        self.jobs = sa.Table(
            "jobs",
            self.metadata,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("kind", sa.String(60), nullable=False),
            sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), nullable=False),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("requested_by", sa.String(160), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
            sa.Column("result", sa.JSON()),
            sa.Column("error_code", sa.String(120)),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("lease_owner", sa.String(160)),
            sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
            sa.Column("idempotency_key", sa.String(255)),
            sa.Column("payload_ref", sa.String(255)),
            sa.Column("result_code", sa.String(120)),
        )

    def insert(self, job: Job) -> Job:
        with self.engine.begin() as connection:
            connection.execute(self.jobs.insert().values(**_job_values(job)))
        return job

    def get(self, job_id: UUID) -> Job | None:
        with self.engine.connect() as connection:
            row = connection.execute(sa.select(self.jobs).where(self.jobs.c.id == job_id)).mappings().first()
        return _job_from_row(row) if row else None

    def update(self, job: Job) -> Job:
        with self.engine.begin() as connection:
            result = connection.execute(self.jobs.update().where(self.jobs.c.id == job.id).values(**_job_values(job)))
            if result.rowcount != 1:
                raise KeyError(str(job.id))
        return job

    def ensure_device(self, device: Device) -> None:
        """Idempotently register the built-in fixture required by job FKs."""
        values = {
            "id": device.id,
            "name": device.name,
            "management_address": device.management_address,
            "site": device.site,
            "vendor": device.vendor,
            "platform": device.platform,
            "model": device.model,
            "serial": device.serial,
            "read_only": device.read_only,
            "support_status": device.support_status,
        }
        with self.engine.begin() as connection:
            exists = connection.execute(sa.select(self.devices.c.id).where(self.devices.c.id == device.id)).first()
            if exists:
                connection.execute(self.devices.update().where(self.devices.c.id == device.id).values(**values))
            else:
                connection.execute(self.devices.insert().values(**values))

    def ping(self) -> bool:
        with self.engine.connect() as connection:
            return connection.execute(sa.text("SELECT 1")).scalar_one() == 1


def _job_values(job: Job) -> dict:
    return job.model_dump(mode="python")


def _job_from_row(row: sa.RowMapping) -> Job:
    return Job.model_validate(dict(row))


def create_job_repository() -> JobRepository:
    database_url = os.getenv("DATABASE_URL")
    return SqlAlchemyJobRepository(database_url) if database_url else MemoryJobRepository()
