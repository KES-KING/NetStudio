"""Durable-job orchestration shared by API and worker processes."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from .drivers import FixtureDriver
from .models import Device, Job
from .observations import FixtureCollector
from .repositories import JobRepository, create_job_repository


class JobStore:
    def __init__(self, repository: JobRepository | None = None) -> None:
        self.repository = repository or create_job_repository()

    def enqueue_connection_test(self, device: Device, requested_by: str) -> Job:
        job = Job(kind="connection_test", device_id=device.id, requested_by=requested_by)
        return self.repository.insert(job)

    def enqueue_inventory_read(self, device: Device, requested_by: str) -> Job:
        job = Job(kind="inventory_read", device_id=device.id, requested_by=requested_by)
        return self.repository.insert(job)

    def get(self, job_id: UUID) -> Job | None:
        return self.repository.get(job_id)

    def ensure_device(self, device: Device) -> None:
        self.repository.ensure_device(device)

    def is_ready(self) -> bool:
        return self.repository.ping()

    def run_fixture_job(self, job_id: UUID, device: Device) -> Job | None:
        job = self.repository.get(job_id)
        if job is None:
            return None
        started_at = datetime.now(timezone.utc)
        running = job.model_copy(update={"status": "running", "started_at": started_at, "attempt": job.attempt + 1, "heartbeat_at": started_at})
        self.repository.update(running)
        if running.kind == "inventory_read":
            snapshot = FixtureCollector().collect(device)
            result = running.model_copy(
                update={
                    "status": "succeeded",
                    "result": {"snapshot": snapshot.model_dump(mode="json")},
                    "result_code": "fixture_snapshot",
                }
            )
        else:
            result = FixtureDriver(device).run(running)
        result = result.model_copy(update={"finished_at": datetime.now(timezone.utc)})
        return self.repository.update(result)


job_store = JobStore()
