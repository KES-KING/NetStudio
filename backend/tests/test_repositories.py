from datetime import datetime, timezone

from sqlalchemy import create_engine

from app.fixtures import build_fixture
from app.models import Job
from app.repositories import MemoryJobRepository, SqlAlchemyJobRepository


def test_memory_repository_round_trips_queue_metadata():
    repository = MemoryJobRepository()
    repository.ensure_device(build_fixture())
    assert repository.ping() is True
    job = Job(kind="inventory_read", device_id="dev-demo-01", requested_by="u-1")
    repository.insert(job)
    updated = job.model_copy(update={"status": "running", "attempt": 1, "heartbeat_at": datetime.now(timezone.utc)})
    repository.update(updated)
    assert repository.get(job.id).attempt == 1


def test_sqlalchemy_repository_round_trips_against_sqlite_contract():
    repository = SqlAlchemyJobRepository("sqlite+pysqlite:///:memory:")
    repository.metadata.create_all(repository.engine)
    repository.ensure_device(build_fixture())
    assert repository.ping() is True
    job = Job(kind="connection_test", device_id="dev-demo-01", requested_by="u-1")
    repository.insert(job)
    loaded = repository.get(job.id)
    assert loaded is not None
    assert loaded.kind == "connection_test"
    assert loaded.next_run_at is not None


def test_file_sqlite_does_not_share_a_connection_between_concurrent_jobs(tmp_path):
    repository = SqlAlchemyJobRepository(f"sqlite+pysqlite:///{tmp_path / 'jobs.db'}")
    with repository.engine.connect() as first, repository.engine.connect() as second:
        assert first.connection.driver_connection is not second.connection.driver_connection
    repository.engine.dispose()
