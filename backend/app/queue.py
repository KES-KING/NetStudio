"""PostgreSQL durable queue. Claim transactions never wait for network devices."""
from contextlib import contextmanager
from datetime import timedelta

import sqlalchemy as sa

from .database import now
from .driver_catalog import GROUPS
from .models import Job
from .ssh import ConnectionPolicyError
from .ssh_profiles import target_signature

LEASE_SECONDS = 30
MAX_RUNNING = 8


@contextmanager
def transaction(store):
    with store.engine.connect() as conn:
        if conn.dialect.name == "sqlite":
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            conn.begin()
            # Serializes only claim/slot accounting, never the actual work.
            conn.execute(sa.text("SELECT pg_advisory_xact_lock(730201905)"))
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def enqueue(store, device, kind, *, auth=None, groups=GROUPS, policy_version=None, candidate_id=None, conn=None):
    def write(connection):
        jobs, contexts = store.jobs_repository.jobs, store.job_contexts
        # Pre-0006 in-memory jobs have no durable authorization context. A fresh
        # authorized request replaces only this device/kind's stranded jobs;
        # never invent a user session for work left by the old API process.
        connection.execute(jobs.update().where(jobs.c.device_id == device.id, jobs.c.kind == kind,
            jobs.c.status.in_(("queued", "running")),
            ~sa.exists(sa.select(contexts.c.job_id).where(contexts.c.job_id == jobs.c.id))).values(
                status="cancelled", finished_at=now(), result_code="legacy_job_requires_retry",
                lease_owner=None, lease_expires_at=None))
        if kind != "ssh_discovery":
            pending = connection.execute(sa.select(jobs).where(jobs.c.device_id == device.id,
                jobs.c.kind == kind, jobs.c.status.in_(("queued", "running")))
                .order_by(jobs.c.created_at).limit(2)).mappings().all()
            for existing in pending:
                current = connection.execute(sa.select(contexts.c.groups).where(contexts.c.job_id == existing["id"])).scalar_one()
                if existing["status"] == "queued":
                    connection.execute(contexts.update().where(contexts.c.job_id == existing["id"])
                        .values(groups=sorted(set(current) | set(groups))))
                    return Job.model_validate(dict(existing))
                if kind != "inventory_read" or set(groups).issubset(current):
                    return Job.model_validate(dict(existing))
            # A running fast-only read cannot satisfy a new full manual read.
            # At most one coalesced follow-up waits behind it; never parallel IO.
        job = Job(kind=kind, device_id=device.id, requested_by=auth.user.user_id if auth else "system:collector",
                  priority=10 if auth else 100)
        connection.execute(jobs.insert().values(**job.model_dump()))
        connection.execute(contexts.insert().values(job_id=job.id, actor_kind="user" if auth else "system",
            session_hash=auth.session_hash if auth else None, connection_revision=device.connection_revision,
            target_signature=target_signature(device), groups=list(groups), policy_version=policy_version, candidate_id=candidate_id))
        return job
    if conn is not None:
        return write(conn)
    with transaction(store) as connection:
        return write(connection)


def claim(store, owner, at=None):
    at = at or now()
    jobs = store.jobs_repository.jobs
    with transaction(store) as conn:
        # Crashed/expired workers can no longer write, even if their socket wakes.
        expired = (jobs.c.status == "running") & (jobs.c.lease_expires_at < at)
        conn.execute(jobs.update().where(expired, jobs.c.attempt >= jobs.c.max_attempts)
            .values(status="failed", finished_at=at, error_code="worker_lease_exhausted", lease_owner=None))
        conn.execute(jobs.update().where(expired, jobs.c.attempt < jobs.c.max_attempts)
            .values(status="queued", lease_owner=None, lease_expires_at=None, next_run_at=at))
        running = list(conn.execute(sa.select(jobs.c.device_id).join(store.job_contexts,
            store.job_contexts.c.job_id == jobs.c.id).where(jobs.c.status == "running")).scalars())
        if len(running) >= MAX_RUNNING:
            return None
        query = sa.select(jobs).join(store.job_contexts, store.job_contexts.c.job_id == jobs.c.id).where(
            jobs.c.status == "queued", jobs.c.next_run_at <= at, jobs.c.device_id.not_in(running))
        row = conn.execute(query.order_by(jobs.c.priority, jobs.c.created_at).limit(1)
            .with_for_update(skip_locked=True, of=jobs)).mappings().first()
        if row is None:
            return None
        values = dict(status="running", lease_owner=owner, lease_expires_at=at + timedelta(seconds=LEASE_SECONDS),
                      heartbeat_at=at, started_at=at, attempt=row["attempt"] + 1)
        conn.execute(jobs.update().where(jobs.c.id == row["id"]).values(**values))
        return Job.model_validate({**dict(row), **values})


def owned(store, job, owner, conn, at=None):
    table = store.jobs_repository.jobs
    valid = conn.execute(sa.select(table.c.id).where(table.c.id == job.id, table.c.status == "running",
        table.c.lease_owner == owner, table.c.lease_expires_at > (at or now())).with_for_update()).first()
    if not valid:
        raise ConnectionPolicyError("worker_lease_lost")


def heartbeat(store, job, owner):
    table, at = store.jobs_repository.jobs, now()
    with store.engine.begin() as conn:
        result = conn.execute(table.update().where(table.c.id == job.id, table.c.status == "running",
            table.c.lease_owner == owner, table.c.lease_expires_at > at)
            .values(heartbeat_at=at, lease_expires_at=at + timedelta(seconds=LEASE_SECONDS)))
        return result.rowcount == 1


def finish(store, job, owner, *, status, result=None, error=None):
    with store.engine.begin() as conn:
        owned(store, job, owner, conn)
        conn.execute(store.jobs_repository.jobs.update().where(store.jobs_repository.jobs.c.id == job.id).values(
            status=status, result=result, error_code=error, finished_at=now(), lease_owner=None,
            lease_expires_at=None, result_code="collection_complete" if status == "succeeded" else status))
        store.record(job.requested_by, "job.finished", status, job.device_id, str(job.id),
            details={"job_id": str(job.id), "error_code": error}, conn=conn)
