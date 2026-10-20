import json
import sys
import threading
import time
from importlib import import_module
from io import BytesIO
from urllib.error import HTTPError

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app import updates
from app.database import Store, now
from app.updater import HostConfig, HostUpdater, Runner, UpdateFailure
from conftest import add_device, login

OLD, NEW = "a" * 40, "b" * 40


def commit(sha=NEW):
    return dict(sha=sha, title="QA commit", description="QA description", author="QA",
        committed_at=now().isoformat(), url=f"{updates.REPOSITORY_URL}/commit/{sha}")


def ready(store, **changes):
    with updates.locked(store) as (_, state):
        state.update(installed_revision=OLD, latest_revision=NEW, commits=[commit()],
            checked_at=now().isoformat(), agent_id="test-agent", agent_seen=time.time(), agent_ready=True, **changes)


def test_update_permissions_csrf_confirmation_and_coalescing(system):
    client, store, *_ = system
    assert client.get("/api/v1/system/updates").status_code == 401
    login(client, "viewer")
    assert client.get("/api/v1/system/updates").json()["can_manage"] is False
    assert client.post("/api/v1/system/updates/check").status_code == 403
    login(client)
    assert client.put("/api/v1/system/updates/policy", json={"automatic": True}).status_code == 422
    assert client.put("/api/v1/system/updates/policy", json={"automatic": True, "acknowledge_main_execution": True}).status_code == 409
    ready(store)
    request = {"revision": NEW, "acknowledge_restart": True}
    assert client.post("/api/v1/system/updates/install", json=request, headers={"x-csrf-token": "wrong"}).status_code == 403
    assert client.post("/api/v1/system/updates/install", json={**request, "revision": OLD}).status_code == 409
    first = client.post("/api/v1/system/updates/install", json=request)
    assert first.status_code == 202
    assert client.post("/api/v1/system/updates/install", json=request).json()["id"] == first.json()["id"]
    payload = client.get("/api/v1/system/updates").json()
    assert len(payload["runs"]) == 1 and "actor" not in payload["runs"][0]
    assert "agent_id" not in payload and "policy_actor" not in payload


def test_check_cooldown_etag_error_preservation_and_automatic_queue(system):
    _, store, *_ = system
    ready(store, automatic=True, policy_actor="admin")
    calls = []
    def fetch(etag):
        calls.append(etag)
        return [commit()], '"qa"', None, 600
    assert updates.check(store, fetch=fetch)
    state = updates.read(store)
    assert state["active_run"] and state["etag"] == '"qa"'
    assert not updates.check(store, requested=True, fetch=fetch)
    assert len(calls) == 1
    with updates.locked(store) as (conn, state):
        conn.execute(store.update_runs.update().values(status="failed"))
        state.update(active_run=None, next_check=0)
    assert updates.check(store, fetch=lambda _: (None, '"qa"', None, 600))
    assert updates.read(store)["active_run"] is None  # failed SHA never loops
    previous_commits = updates.read(store)["commits"]
    with updates.locked(store) as (_, state):
        state["next_check"] = 0
    updates.check(store, fetch=lambda _: (None, None, "github_unavailable", 600))
    state = updates.read(store)
    assert state["commits"] == previous_commits
    assert state["latest_revision"] == NEW and state["error_code"] == "github_unavailable"


def test_automatic_authority_revoked_and_lease_fencing(system):
    _, store, *_ = system
    ready(store, automatic=True, policy_actor="admin")
    with store.engine.begin() as conn:
        conn.execute(store.users.update().where(store.users.c.id == "admin").values(enabled=False))
    updates.check(store, fetch=lambda _: ([commit()], "", None, 600))
    assert updates.read(store)["active_run"] is None
    with updates.locked(store) as (_, state):
        state["next_check"] = 0
    def steal(_):
        with updates.locked(store) as (_, state):
            state.update(check_owner="new-owner", latest_revision=OLD)
        return [commit()], "", None, 600
    assert updates.check(store, fetch=steal) is False
    assert updates.read(store)["latest_revision"] == OLD


def test_github_fixed_target_safe_links_and_bounded_response(monkeypatch):
    class Response(BytesIO):
        headers = {"ETag": '"test"'}
    payload = [{"sha": NEW, "html_url": "javascript:ignored", "commit": {"message": "Title\nDetails",
        "author": {"name": "Author"}, "committer": {"date": "2026-10-20T12:00:00Z"}}}]
    requests = []
    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            assert timeout == 12
            return Response(json.dumps(payload).encode())
    monkeypatch.setattr(updates, "build_opener", lambda *_: Opener())
    result, etag, error, delay = updates.github_commits('"previous"')
    assert result[0]["url"] == f"https://github.com/KES-KING/NetStudio/commit/{NEW}"
    assert result[0]["title"] == "Title" and "Details" in result[0]["description"]
    assert requests[0].full_url == "https://api.github.com/repos/KES-KING/NetStudio/commits?sha=main&per_page=30"
    assert requests[0].get_header("If-none-match") == '"previous"'
    assert etag == '"test"' and error is None and delay == 600
    payload[0]["sha"] = "not-a-sha"
    assert updates.github_commits()[2] == "github_unavailable"


@pytest.mark.parametrize("code,expected,delay", [(304, None, 600), (429, "github_rate_limited", 900), (302, "github_unavailable", 600)])
def test_github_not_modified_rate_limit_redirect(monkeypatch, code, expected, delay):
    class Opener:
        def open(self, *_args, **_kwargs):
            raise HTTPError("https://api.github.com", code, "test", {"Retry-After": "900"}, None)
    monkeypatch.setattr(updates, "build_opener", lambda *_: Opener())
    result = updates.github_commits('"old"')
    assert result[0] is None and result[2:] == (expected, delay)


def test_notifications_are_scoped_sanitized_and_read_cursor_monotonic(system):
    client, store, *_ = system
    login(client)
    inside = add_device(client)
    outside = add_device(client, name="Offsite secret", site="other")
    store.record("admin", "job.finished", "failed", outside["id"], details={"reason": "hidden"})
    store.record("admin", "profile.updated", "succeeded", target_id="admin")
    store.record("viewer", "profile.updated", "succeeded", target_id="viewer")
    store.record("system:updates", "update.available", "available", target_id=NEW)
    login(client, "viewer")
    data = client.get("/api/v1/notifications").json()
    assert len(data["items"]) == 3
    assert {row["href"] for row in data["items"]} == {"/settings", "/settings/updates", f"/devices/{inside['id']}"}
    assert "Offsite" not in json.dumps(data) and "details" not in json.dumps(data)
    with store.engine.connect() as conn:
        hidden = conn.execute(sa.select(store.audit.c.id).where(store.audit.c.device_id == outside["id"])).scalars().first()
    assert client.post("/api/v1/notifications/read", json={"through_id": hidden}).status_code == 404
    assert client.post("/api/v1/notifications/read", json={"through_id": data["latest_id"]}).status_code == 200
    assert client.get("/api/v1/notifications").json()["unread_count"] == 0
    client.post("/api/v1/notifications/read", json={"through_id": data["items"][-1]["id"]})
    assert client.get("/api/v1/notifications").json()["unread_count"] == 0


def test_notifications_bound_history_and_maintenance_guards(system):
    client, store, *_ = system
    login(client)
    for _ in range(105):
        store.record("system:updates", "update.available", "available")
    data = client.get("/api/v1/notifications").json()
    assert len(data["items"]) == 30 and data["unread_count"] == 100
    with updates.locked(store) as (_, state):
        state.update(maintenance=True, agent_seen=0)
    assert client.post("/api/v1/devices", json={}).status_code == 503
    assert client.get("/api/v1/devices").status_code == 200
    assert client.put("/api/v1/system/updates/policy", json={"automatic": False}).status_code == 200
    assert client.post("/api/v1/session/logout").status_code == 200
    assert updates.maintenance(store)  # a dead agent never unpauses writes


def host(tmp_path, store):
    config = HostConfig(project="qa-project", docker_context="explicit-test", installation_dir=tmp_path,
        compose_files=[tmp_path / "compose.yml"], env_file=tmp_path / "env", state_dir=tmp_path / "private",
        database_url="postgresql+psycopg://qa:unused@127.0.0.1:19999/qa")
    return HostUpdater(config, store=store)


@pytest.mark.parametrize("fault,schema_changed,expected", [(None, False, "succeeded"), ("backup", False, "failed"),
    ("migration", False, "recovery_required"), ("deploy", True, "recovery_required"), ("deploy", False, "failed")])
def test_host_install_order_and_failure_recovery(system, tmp_path, monkeypatch, fault, schema_changed, expected):
    _, store, *_ = system
    updater = host(tmp_path, store)
    ready(store)
    with updates.locked(store) as (conn, state):
        state["agent_id"] = updater.owner
        identifier = updates.enqueue_update(store, conn, state, "admin")
    run = updater.claim()
    steps = []
    fake = {name: {"Image": "sha256:old", "Mounts": [{"Type": "volume", "Name": name, "Destination": "/data"}]}
        for name in ("api", "web", "collector-worker", "postgres")}
    monkeypatch.setattr(updater, "project", lambda: fake)
    revisions = iter([OLD, NEW])
    monkeypatch.setattr(updater, "revisions", lambda _: next(revisions))
    monkeypatch.setattr(updater, "compose_fingerprint", lambda: "constant")
    monkeypatch.setattr(updater, "stage", lambda *_: tmp_path)
    monkeypatch.setattr(updater, "override", lambda _, name, _images: [name])
    monkeypatch.setattr(updater, "wait_quiet", lambda: steps.append("drain"))
    def backup(*_):
        steps.append("backup")
        if fault == "backup":
            raise UpdateFailure("backup_failed")
    monkeypatch.setattr(updater, "backup", backup)
    schemas = iter([("0007",), ("0008",) if schema_changed else ("0007",)])
    monkeypatch.setattr(updater, "schema_revision", lambda: next(schemas))
    def command(args, **_):
        step = "migration" if "migrate" in args else "rollback" if args[0] == "previous-compose.json" else "deploy"
        steps.append(step)
        if step == fault:
            raise UpdateFailure("installation_failed")
    monkeypatch.setattr(updater, "command", command)
    updater.perform(run)
    with store.engine.connect() as conn:
        status = conn.execute(sa.select(store.update_runs.c.status).where(store.update_runs.c.id == identifier)).scalar_one()
    assert status == expected
    assert steps[:2] == ["drain", "backup"]
    assert ("rollback" in steps) == (fault == "deploy" and not schema_changed)
    assert updates.maintenance(store) == (expected == "recovery_required")
    assert updates.read(store)["installed_revision"] == (NEW if expected == "succeeded" else OLD)


def test_host_revoked_actor_and_ownership_fence(system, tmp_path):
    _, store, *_ = system
    updater = host(tmp_path, store)
    ready(store)
    with updates.locked(store) as (conn, state):
        state["agent_id"] = updater.owner
        identifier = updates.enqueue_update(store, conn, state, "admin")
        conn.execute(store.users.update().where(store.users.c.id == "admin").values(enabled=False))
    assert updater.claim() is None
    with store.engine.connect() as conn:
        assert conn.execute(sa.select(store.update_runs.c.status).where(store.update_runs.c.id == identifier)).scalar_one() == "cancelled"
    with updates.locked(store) as (_, state):
        state.update(agent_id="other", active_run="new", maintenance=True)
    updater.finish({"id": identifier}, "failed")
    assert updater.lost.is_set() and updates.read(store)["active_run"] == "new" and updates.maintenance(store)


def test_disabling_schedule_does_not_interrupt_an_already_drained_migration(system, tmp_path):
    _, store, *_ = system
    updater = host(tmp_path, store)
    ready(store, automatic=True)
    with updates.locked(store) as (conn, state):
        state["agent_id"] = updater.owner
        updates.enqueue_update(store, conn, state, "admin", automatic=True)
    run = updater.claim()
    updater.phase(run, "draining")
    with updates.locked(store) as (_, state):
        state["automatic"] = False
    updater.phase(run, "migrating")
    updater.phase(run, "deploying")
    with store.engine.begin() as conn:
        conn.execute(store.users.update().where(store.users.c.id == "admin").values(enabled=False))
    with pytest.raises(UpdateFailure, match="update_actor_revoked"):
        updater.phase(run, "verifying")


@pytest.mark.parametrize("fault,expected", [(None, None), ("remote", "local_docker_context_required"),
    ("project", "project_identity_mismatch"), ("port", "database_project_mismatch"),
    ("unknown", "update_revision_unknown")])
def test_host_binds_explicit_existing_project_database_and_image_identity(system, tmp_path, monkeypatch, fault, expected):
    updater = host(tmp_path, system[1])
    def command(args, **_):
        assert args[:3] == ["docker", "--context", "explicit-test"]
        if "context" in args:
            return json.dumps([{"Endpoints": {"docker": {"Host": "tcp://remote:2375" if fault == "remote" else "unix:///test-only.sock"}}}]).encode()
        service = args[-1]
        if "compose" in args:
            assert "--project-name" in args and "qa-project" in args and "--env-file" in args
            return service.encode()
        assert "inspect" in args
        return json.dumps([{"Config": {"Labels": {"com.docker.compose.project": "wrong" if fault == "project" else "qa-project",
            "com.docker.compose.service": service, "org.opencontainers.image.revision": "unknown" if fault == "unknown" else OLD},
            "Env": ["POSTGRES_DB=qa", "POSTGRES_USER=qa", "DATABASE_URL=postgresql+psycopg://qa:unused@postgres:5432/qa"]},
            "State": {"Running": True, "Health": {"Status": "healthy"}},
            "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "12345" if fault == "port" else "19999"}]}}}]).encode()
    monkeypatch.setattr(updater, "command", command)
    if expected:
        with pytest.raises(UpdateFailure, match=expected):
            updater.revisions(updater.project())
    else:
        assert updater.revisions(updater.project()) == OLD


def test_stage_rejects_deployment_changes_before_build(system, tmp_path, monkeypatch):
    updater = host(tmp_path, system[1])
    updater.config.state_dir.mkdir(mode=0o700)
    commands = []
    def command(args, **_):
        commands.append(args)
        return b"deploy/routes.conf\n" if "diff" in args else b""
    monkeypatch.setattr(updater, "command", command)
    with pytest.raises(UpdateFailure, match="deployment_contract_changed"):
        updater.stage({"revision": NEW}, OLD)
    assert commands[0][-2] == "https://github.com/KES-KING/NetStudio.git"
    assert all("build" not in args and "up" not in args for args in commands)


def test_host_config_rejects_broad_remote_or_unbound_targets(tmp_path, system):
    updater = host(tmp_path, system[1])
    updater.config.installation_dir = tmp_path
    updater.config.compose_files = [tmp_path / "missing"]
    with pytest.raises(UpdateFailure, match="invalid_host_config"):
        updater.config.validate_paths()
    updater.config.state_dir = tmp_path.__class__("/")
    with pytest.raises(UpdateFailure, match="invalid_host_config"):
        updater.config.validate_paths()


def test_host_runner_does_not_inherit_compose_overrides(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "wrong-project")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "wrong-project")
    monkeypatch.setenv("DOCKER_HOST", "tcp://wrong-host:2375")
    value = Runner(threading.Event()).run([sys.executable, "-c",
        "import os,json; print(json.dumps([os.getenv(k) for k in ['POSTGRES_DB','COMPOSE_PROJECT_NAME','DOCKER_HOST']]))"])
    assert json.loads(value) == [None, None, None]


def test_host_backup_validates_dump_keyring_and_preserves_private_inputs(system, tmp_path, monkeypatch):
    _, store, _, keyfile = system
    updater = host(tmp_path, store)
    updater.pg_user, updater.pg_database = "qa", "qa"
    updater.config.env_file.write_text("QA_ONLY=1")
    updater.config.compose_files[0].write_text("services: {}")
    steps = []
    def command(args, output=None, stdin=None, **_):
        if "pg_dump" in args:
            steps.append("dump"); output.write(b"PGDMP-test")
        elif "python" in args:
            steps.append("keyring"); output.write(keyfile.read_bytes())
        elif "pg_restore" in args:
            assert "--list" in args and stdin.read() == b"PGDMP-test"
            steps.append("validate")
    monkeypatch.setattr(updater, "command", command)
    directory = tmp_path / "release"
    directory.mkdir(mode=0o700)
    updater.backup(directory, {"postgres": {"Id": "test-pg", "Image": "old-pg"}, "api": {"Id": "test-api", "Image": "old-api"}})
    assert steps == ["dump", "keyring", "validate"]
    for name in ("database.dump", "keyring.json"):
        assert (directory / name).stat().st_mode & 0o777 == 0o600
    assert (directory / "deployment-input-0").read_text() == "QA_ONLY=1"
    with pytest.raises(FileExistsError):
        updater.backup(directory, {"postgres": {"Id": "test-pg"}, "api": {"Id": "test-api"}})


def test_0007_additive_migration_preserves_user_hash_and_audit(tmp_path):
    store = Store(f"sqlite+pysqlite:///{tmp_path / 'migration.db'}")
    names = import_module("app.system_schema_v1").define_tables(sa.MetaData())
    new = {getattr(store, name) for name in names}
    store.meta.create_all(store.engine, tables=[table for table in store.meta.sorted_tables if table not in new])
    with store.engine.begin() as conn:
        conn.execute(store.users.insert().values(id="preserved", username="existing", password_hash="untouched", roles=["superadmin"], sites=["*"], enabled=True))
        with Operations.context(MigrationContext.configure(conn)):
            import_module("migrations.versions.0007_settings_updates").upgrade()
        assert conn.execute(sa.select(store.users.c.password_hash)).scalar_one() == "untouched"
        assert conn.execute(sa.select(sa.func.count()).select_from(store.system_update)).scalar_one() == 0
    store.engine.dispose()
