"""Isolated deployment updater for a single verified NetStudio project.

The default Compose installation runs this code in its own container with the
Engine API delegated only to that container.  API/web/worker processes never
receive Docker access.  A private host configuration remains supported for
custom installations and recovery.
"""
import argparse
from datetime import timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import threading
import time
from uuid import uuid4
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
import sqlalchemy as sa

from .database import Store, now
from . import updates


class UpdateFailure(RuntimeError):
    pass


IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


class HostConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,62}$")
    docker_context: str = Field(min_length=1, max_length=120)
    installation_dir: Path
    compose_files: list[Path] = Field(min_length=1, max_length=5)
    env_file: Path
    state_dir: Path
    database_url: str
    drain_timeout: int = Field(default=900, ge=15, le=3600)
    runtime: Literal["host", "container"] = "host"
    bootstrap_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")

    def validate_paths(self):
        for path in [self.installation_dir, self.env_file, self.state_dir, *self.compose_files]:
            if not path.is_absolute() or path == Path("/"):
                raise UpdateFailure("invalid_host_config")
        for path in self.compose_files:
            if not path.is_file() or not path.resolve().is_relative_to(self.installation_dir.resolve()):
                raise UpdateFailure("invalid_host_config")
        if not self.env_file.is_file() or not (
            self.env_file.resolve().is_relative_to(self.installation_dir.resolve())
            or self.runtime == "container" and self.env_file.resolve().is_relative_to(self.state_dir.resolve())
        ):
            raise UpdateFailure("invalid_host_config")
        url = sa.engine.make_url(self.database_url)
        allowed_database = (
            url.get_backend_name() == "postgresql" and url.port
            and (url.host in {"127.0.0.1", "localhost"} if self.runtime == "host" else url.host == "postgres" and url.port == 5432)
        )
        if not allowed_database:
            raise UpdateFailure("database_must_be_explicit_loopback")
        if self.state_dir.is_symlink() or (self.state_dir.exists() and (self.state_dir.stat().st_uid != os.getuid() or self.state_dir.stat().st_mode & 0o077)):
            raise UpdateFailure("private_state_directory_required")
        self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)


class Runner:
    def __init__(self, lost):
        self.lost = lost

    def run(self, args, *, cwd=None, output=None, stdin=None, timeout=1800):
        # No shell, no command from HTTP, no raw command output in API/audit.
        with tempfile.TemporaryFile() as capture:
            target = output if output is not None else capture
            # Compose interpolation must come only from the operator's env_file,
            # not unrelated variables inherited from a shell/service manager.
            env = {key: value for key, value in os.environ.items()
                if key in {"PATH", "HOME", "DOCKER_CONFIG", "XDG_RUNTIME_DIR", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR"}}
            env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")
            process = subprocess.Popen(args, cwd=cwd, env=env, stdin=stdin or subprocess.DEVNULL,
                stdout=target, stderr=subprocess.DEVNULL, start_new_session=True)
            deadline = time.monotonic() + timeout
            try:
                while process.poll() is None:
                    if self.lost.is_set() or time.monotonic() >= deadline:
                        raise UpdateFailure("agent_interrupted" if self.lost.is_set() else "installation_failed")
                    time.sleep(.25)
                if process.returncode != 0:
                    raise UpdateFailure("installation_failed")
                if output is not None:
                    output.flush(); os.fsync(output.fileno())
                    return b""
                capture.seek(0)
                value = capture.read(4_000_001)
                if len(value) > 4_000_000:
                    raise UpdateFailure("command_output_limit")
                return value
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL); process.wait()


class HostUpdater:
    def __init__(self, config, store=None, runner=None):
        self.config = config
        self.store = store or Store(config.database_url)
        self.owner = str(uuid4())
        self.lost = threading.Event()
        self.stop = threading.Event()
        self.runner = runner or Runner(self.lost)
        self.docker = ["docker", "--context", config.docker_context]
        self.compose = [*self.docker, "compose", "--project-name", config.project,
            "--project-directory", str(config.installation_dir), "--env-file", str(config.env_file)]
        for path in config.compose_files:
            self.compose += ["-f", str(path)]
        self.containers = {}
        self.manifest = None

    def command(self, args, **kwargs):
        return self.runner.run(args, **kwargs)

    def inspect(self, identifier):
        return json.loads(self.command([*self.docker, "inspect", identifier]))[0]

    def project(self):
        endpoint = json.loads(self.command([*self.docker, "context", "inspect", self.config.docker_context]))[0]["Endpoints"]["docker"]["Host"]
        if not endpoint.startswith("unix://"):
            raise UpdateFailure("local_docker_context_required")
        # A different project/DB is an error, not a request to create a new one.
        current = {}
        for service in ("api", "web", "collector-worker", "postgres"):
            ids = self.command([*self.compose, "ps", "--all", "--quiet", service]).decode().split()
            if len(ids) != 1:
                raise UpdateFailure("existing_project_required")
            value = self.inspect(ids[0])
            labels = value["Config"]["Labels"]
            if labels.get("com.docker.compose.project") != self.config.project or labels.get("com.docker.compose.service") != service:
                raise UpdateFailure("project_identity_mismatch")
            if not value["State"]["Running"] or value["State"].get("Health", {}).get("Status") != "healthy":
                raise UpdateFailure("project_not_healthy")
            current[service] = value
        url = sa.engine.make_url(self.config.database_url)
        pg_env = dict(item.split("=", 1) for item in current["postgres"]["Config"]["Env"] if "=" in item)
        ports = current["postgres"]["NetworkSettings"]["Ports"].get("5432/tcp") or []
        database_bound = (
            any(p["HostIp"] == "127.0.0.1" and int(p["HostPort"]) == url.port for p in ports)
            if self.config.runtime == "host" else url.host == "postgres" and url.port == 5432
        )
        if not database_bound or pg_env.get("POSTGRES_DB") != url.database or pg_env.get("POSTGRES_USER") != url.username:
            raise UpdateFailure("database_project_mismatch")
        for service in ("api", "collector-worker"):
            env = dict(item.split("=", 1) for item in current[service]["Config"]["Env"] if "=" in item)
            bound = sa.engine.make_url(env.get("DATABASE_URL", ""))
            if bound.host != "postgres" or bound.database != url.database or bound.username != url.username:
                raise UpdateFailure("database_project_mismatch")
        self.pg_user = pg_env.get("POSTGRES_USER", "postgres")
        self.pg_database = url.database
        self.containers = current
        return current

    def revisions(self, containers):
        values = []
        for service in ("api", "web", "collector-worker"):
            value = containers[service]["Config"]["Labels"].get("org.opencontainers.image.revision", "")
            values.append(value)
        exact = set(values)
        if len(exact) == 1 and updates.SHA.fullmatch(values[0]):
            return values[0]
        # A fresh zero-configuration Compose build cannot interpolate Git HEAD
        # into an OCI label.  The dedicated updater may bind that first build
        # to the separately verified clean public checkout.  Every candidate
        # image built by the updater still carries and must pass an exact label.
        if exact == {"unknown"} and self.config.runtime == "container" and self.config.bootstrap_revision:
            return self.bound_bootstrap_revision(containers)
        if len(exact) != 1:
            raise UpdateFailure("runtime_revision_mismatch")
        raise UpdateFailure("update_revision_unknown")

    def bound_bootstrap_revision(self, containers):
        """Bind an unlabeled first build to immutable image IDs exactly once.

        A later Git pull changes the verified source mount without changing the
        running images.  Persisting this binding prevents a restarted updater
        from claiming that the newer source revision is already installed.
        """
        images = {service: containers[service].get("Image", "")
            for service in ("api", "web", "collector-worker")}
        if not all(IMAGE_ID.fullmatch(value) for value in images.values()) or images["api"] != images["collector-worker"]:
            raise UpdateFailure("runtime_revision_mismatch")
        path = self.config.state_dir / "bootstrap-runtime.json"
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if path.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 16_384:
                raise UpdateFailure("private_state_directory_required")
            try:
                binding = json.loads(path.read_text())
            except (OSError, ValueError):
                raise UpdateFailure("bootstrap_binding_invalid") from None
            revision = binding.get("revision") if isinstance(binding, dict) else None
            bound_images = binding.get("images") if isinstance(binding, dict) else None
            if bound_images == images:
                if not isinstance(revision, str) or not updates.SHA.fullmatch(revision):
                    raise UpdateFailure("bootstrap_binding_invalid")
                return revision
        descriptor, temporary = tempfile.mkstemp(prefix=".bootstrap-runtime.", dir=self.config.state_dir)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w") as output:
                json.dump({"revision": self.config.bootstrap_revision, "images": images}, output, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return self.config.bootstrap_revision

    def register(self):
        revision = self.revisions(self.project())
        with updates.locked(self.store) as (conn, state):
            if updates.agent_online(state) and state["agent_id"] != self.owner:
                raise UpdateFailure("agent_already_running")
            if state["active_run"]:
                row = conn.execute(sa.select(self.store.update_runs).where(self.store.update_runs.c.id == state["active_run"])).mappings().one()
                if row["status"] != "queued":
                    state.update(recovery_required=True, maintenance=True, automatic=False)
                    conn.execute(self.store.update_runs.update().where(self.store.update_runs.c.id == row["id"]).values(
                        status="recovery_required", error_code="agent_interrupted", updated_at=now()))
            state.update(agent_id=self.owner, agent_seen=time.time(), agent_ready=True)
            if not state["recovery_required"]:
                state["installed_revision"] = revision

    def heartbeat(self):
        while not self.stop.wait(10):
            try:
                with updates.locked(self.store) as (_, state):
                    if state["agent_id"] != self.owner:
                        self.lost.set(); return
                    state["agent_seen"] = time.time()
            except Exception:
                self.lost.set(); return

    def phase(self, run, phase):
        with updates.locked(self.store) as (conn, state):
            if state["agent_id"] != self.owner or state["active_run"] != run["id"] or self.lost.is_set():
                raise UpdateFailure("agent_interrupted")
            # Turning the schedule off cancels queued/preflight work, not an
            # already-drained migration. Revoked account authority still fences
            # every phase, including deployment.
            if not updates.allowed_actor(self.store, conn, run["actor"]) or (
                phase == "draining" and run["automatic"] and not state["automatic"]
            ):
                raise UpdateFailure("update_actor_revoked")
            conn.execute(self.store.update_runs.update().where(self.store.update_runs.c.id == run["id"])
                .values(status=phase, updated_at=now()))
            if phase == "draining":
                state["maintenance"] = True

    def claim(self):
        with updates.locked(self.store) as (conn, state):
            if state["agent_id"] != self.owner or state["recovery_required"] or not state["active_run"]:
                return None
            row = conn.execute(sa.select(self.store.update_runs).where(self.store.update_runs.c.id == state["active_run"],
                self.store.update_runs.c.status == "queued")).mappings().first()
            if row is None:
                return None
            run = dict(row)
            if not updates.allowed_actor(self.store, conn, run["actor"]) or (run["automatic"] and not state["automatic"]):
                conn.execute(self.store.update_runs.update().where(self.store.update_runs.c.id == run["id"])
                    .values(status="cancelled", error_code="update_actor_revoked", updated_at=now()))
                state["active_run"] = None
                return None
            conn.execute(self.store.update_runs.update().where(self.store.update_runs.c.id == run["id"]).values(status="building", updated_at=now()))
            self.store.record(run["actor"], "update.started", "running", target_type="update", target_id=run["id"], conn=conn)
            return run

    def stage(self, run, installed):
        revision = run["revision"]
        if not updates.SHA.fullmatch(revision) or not updates.SHA.fullmatch(installed):
            raise UpdateFailure("update_revision_unknown")
        directory = Path(tempfile.mkdtemp(prefix="release-", dir=self.config.state_dir))
        source = directory / "source"
        self.command(["git", "clone", "--no-checkout", "--filter=blob:none", "--single-branch", "--branch", "main",
            f"{updates.REPOSITORY_URL}.git", str(source)])
        try:
            self.command(["git", "merge-base", "--is-ancestor", installed, revision], cwd=source)
            self.command(["git", "merge-base", "--is-ancestor", revision, "origin/main"], cwd=source)
        except UpdateFailure:
            raise UpdateFailure("revision_not_forward") from None
        if installed == revision:
            raise UpdateFailure("revision_not_forward")
        changed = self.command(["git", "diff", "--name-only", installed, revision, "--",
            "docker-compose.yml", "docker-compose.tls.yml", "deploy/", "backend/Dockerfile.updater",
            "backend/app/updater.py", "backend/app/update_runtime.py"], cwd=source)
        if changed.strip():
            raise UpdateFailure("deployment_contract_changed")
        self.command(["git", "-c", "core.hooksPath=/dev/null", "checkout", "--detach", revision], cwd=source)
        actual = self.command(["git", "rev-parse", "HEAD"], cwd=source).decode().strip()
        if actual != revision:
            raise UpdateFailure("revision_not_forward")
        for component in ("backend", "frontend"):
            dockerfile = source / component / "Dockerfile"
            if not dockerfile.resolve().is_relative_to(source) or not dockerfile.is_file():
                raise UpdateFailure("invalid_release_layout")
            name = "api" if component == "backend" else "web"
            self.command([*self.docker, "build", "--build-arg", f"NETSTUDIO_BUILD_REVISION={revision}",
                "--tag", f"netstudio-{name}:update-{revision}", "--file", str(dockerfile), str(source)], timeout=3600)
        return directory

    def wait_quiet(self):
        deadline = time.monotonic() + self.config.drain_timeout
        quiet = 0
        while time.monotonic() < deadline and not self.lost.is_set():
            with self.store.engine.connect() as conn:
                presence = conn.execute(sa.select(self.store.runtime_presence)).mappings().all()
                running = conn.execute(sa.select(sa.func.count()).select_from(self.store.jobs_repository.jobs)
                    .where(self.store.jobs_repository.jobs.c.status == "running")).scalar_one()
            live = [row for row in presence if 0 <= (now() - row["heartbeat_at"].replace(tzinfo=timezone.utc)).total_seconds() < 10]
            quiet = quiet + 1 if live and not running and all(row["active_sessions"] == 0 and row["active_mutations"] == 0 for row in live) else 0
            if quiet >= 4:
                return
            self.stop.wait(3)
        raise UpdateFailure("sessions_busy")

    def compose_fingerprint(self):
        # Includes resolved env/overrides without writing or logging their secrets.
        value = self.command([*self.compose, "config", "--format", "json"])
        return hashlib.sha256(value).hexdigest()

    def compose_images(self):
        value = json.loads(self.command([*self.compose, "config", "--format", "json"]))
        services = value.get("services", {})
        images = {service: services.get(service, {}).get("image") for service in ("api", "web", "collector-worker")}
        if not all(isinstance(image, str) and image for image in images.values()) or images["api"] != images["collector-worker"]:
            raise UpdateFailure("deployment_contract_changed")
        return {"api": images["api"], "web": images["web"]}

    def tag_images(self, images, aliases):
        for service in ("api", "web"):
            self.command([*self.docker, "image", "tag", images[service], aliases[service]])

    def override(self, directory, name, images):
        path = directory / name
        path.write_text(json.dumps({"services": {service: {"image": image} for service, image in images.items()}}))
        path.chmod(0o600)
        return [*self.compose, "-f", str(path)]

    def backup(self, directory, containers):
        # New exclusive 0600 files only. No existing backup is overwritten.
        for name, args in (
            ("database.dump", [*self.docker, "exec", containers["postgres"]["Id"], "pg_dump", "-U", self.pg_user, "-d", self.pg_database, "--format=custom"]),
            ("keyring.json", [*self.docker, "exec", containers["api"]["Id"], "python", "-c",
                "import sys; from app.legacy_compat import keyring_path; sys.stdout.buffer.write(open(keyring_path(),'rb').read())"]),
        ):
            path = directory / name
            with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
                self.command(args, output=output)
            if not path.stat().st_size:
                raise UpdateFailure("backup_failed")
        with (directory / "database.dump").open("rb") as backup:
            self.command([*self.docker, "exec", "-i", containers["postgres"]["Id"], "pg_restore", "--list"], stdin=backup)
        from .vault import CredentialVault
        active, keys = CredentialVault(self.store, str(directory / "keyring.json")).keyring()
        if active not in keys or any(len(key) != 32 for key in keys.values()):
            raise UpdateFailure("backup_failed")
        # Preserve deployment inputs with the encrypted data/keyring for manual
        # recovery. Private directory and exclusive files; never served by API.
        for index, path in enumerate([self.config.env_file, *self.config.compose_files]):
            with (directory / f"deployment-input-{index}").open("xb") as backup:
                backup.write(path.read_bytes())
                backup.flush(); os.fsync(backup.fileno())
        # Immutable image IDs and volume identities are recovery evidence, not secrets.
        (directory / "previous-images.json").write_text(json.dumps({key: value["Image"] for key, value in containers.items()}, indent=2))

    def schema_revision(self):
        with self.store.engine.connect() as conn:
            return tuple(conn.execute(sa.text("SELECT version_num FROM alembic_version ORDER BY version_num")).scalars())

    def finish(self, run, status, error=None):
        with updates.locked(self.store) as (conn, state):
            if state["agent_id"] != self.owner or state["active_run"] != run["id"]:
                self.lost.set(); return
            conn.execute(self.store.update_runs.update().where(self.store.update_runs.c.id == run["id"])
                .values(status=status, error_code=error, updated_at=now()))
            state.update(active_run=None, maintenance=status == "recovery_required", recovery_required=status == "recovery_required")
            if status == "succeeded":
                state["installed_revision"] = run["revision"]
            if status == "recovery_required":
                state["automatic"] = False
            self.store.record(run["actor"], "update.finished", status, target_type="update", target_id=run["id"], conn=conn,
                details={"error_code": error})

    def perform(self, run):
        schema = None
        touched_runtime = False
        migration_started = migration_complete = False
        recovery = False
        old = None
        directory = None
        aliases = None
        aliases_touched = False
        containers = None
        try:
            containers = self.project()
            installed = self.revisions(containers)
            fingerprint = self.compose_fingerprint()
            aliases = self.compose_images()
            directory = self.stage(run, installed)
            old = self.override(directory, "previous-compose.json", {key: containers[key]["Image"] for key in ("api", "web", "collector-worker")})
            images = {service: f"netstudio-{'web' if service == 'web' else 'api'}:update-{run['revision']}"
                for service in ("api", "collector-worker", "web", "migrate")}
            candidate = self.override(directory, "candidate-compose.json", images)
            self.phase(run, "draining")
            self.wait_quiet()
            self.phase(run, "backing_up")
            self.backup(directory, containers)
            schema = self.schema_revision()
            if self.compose_fingerprint() != fingerprint:
                raise UpdateFailure("deployment_contract_changed")
            self.phase(run, "migrating")
            migration_started = True
            self.command([*candidate, "run", "--rm", "--no-deps", "--name",
                f"{self.config.project}-update-{run['id']}", "migrate"], timeout=600)
            migration_complete = True
            self.phase(run, "deploying")
            touched_runtime = True
            self.command([*candidate, "up", "-d", "--no-deps", "--no-build", "--wait", "--wait-timeout", "180", "api", "web", "collector-worker"], timeout=240)
            self.phase(run, "verifying")
            current = self.project()
            if self.revisions(current) != run["revision"]:
                raise UpdateFailure("runtime_revision_mismatch")
            for service in containers:
                before = {(m.get("Name"), m["Destination"]) for m in containers[service]["Mounts"] if m["Type"] == "volume"}
                after = {(m.get("Name"), m["Destination"]) for m in current[service]["Mounts"] if m["Type"] == "volume"}
                if before != after:
                    raise UpdateFailure("volume_identity_changed")
            # Keep plain future `docker compose up` on the verified release
            # instead of resolving the base image tag back to the first build.
            aliases_touched = True
            self.tag_images({
                "api": f"netstudio-api:update-{run['revision']}",
                "web": f"netstudio-web:update-{run['revision']}",
            }, aliases)
            self.finish(run, "succeeded")
        except Exception as exc:
            code = str(exc) if isinstance(exc, UpdateFailure) else "installation_failed"
            if schema is not None:
                try:
                    # Killing a Docker CLI doesn't prove its migration container
                    # stopped. Never resume writes after an ambiguous migration.
                    recovery = (migration_started and not migration_complete) or self.schema_revision() != schema
                    if touched_runtime and not recovery and old:
                        self.command([*old, "up", "-d", "--no-deps", "--no-build", "--wait", "--wait-timeout", "180", "api", "web", "collector-worker"], timeout=240)
                        self.project()
                    if aliases_touched and aliases and containers:
                        self.tag_images({"api": containers["api"]["Image"], "web": containers["web"]["Image"]}, aliases)
                except Exception:
                    recovery = True
            self.finish(run, "recovery_required" if recovery else "failed", code)

    def acknowledge_recovery(self, expected_revision):
        """Explicit operator acknowledgement after independent restore/repair."""
        if self.revisions(self.project()) != expected_revision:
            raise UpdateFailure("runtime_revision_mismatch")
        running = self.command([*self.docker, "ps", "--filter",
            f"name={self.config.project}-update-", "--quiet"]).strip()
        if running:
            raise UpdateFailure("migration_still_running")
        with updates.locked(self.store) as (conn, state):
            if updates.agent_online(state):
                raise UpdateFailure("agent_already_running")
            if not state["recovery_required"] and not state["maintenance"]:
                raise UpdateFailure("recovery_not_required")
            if state["active_run"]:
                conn.execute(self.store.update_runs.update().where(self.store.update_runs.c.id == state["active_run"])
                    .values(status="recovery_required", updated_at=now(), error_code="operator_recovered"))
            state.update(active_run=None, maintenance=False, recovery_required=False, automatic=False,
                installed_revision=expected_revision, agent_ready=False, agent_seen=0)
            self.store.record("system:operator", "update.finished", "succeeded", conn=conn,
                details={"recovery_acknowledged": True}, target_type="revision", target_id=expected_revision)

    def run(self, once=False):
        self.register()
        thread = threading.Thread(target=self.heartbeat, daemon=True)
        thread.start()
        try:
            while not self.stop.is_set() and not self.lost.is_set():
                if run := self.claim():
                    self.perform(run)
                if once:
                    return
                self.stop.wait(5)
        finally:
            self.stop.set(); thread.join(timeout=12)
            with updates.locked(self.store) as (_, state):
                if state["agent_id"] == self.owner:
                    state.update(agent_ready=False, agent_seen=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--acknowledge-recovery", metavar="VERIFIED_INSTALLED_SHA",
        help="After manual recovery and schema validation, clear maintenance; automatic updates stay off")
    args = parser.parse_args()
    try:
        info = args.config.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise UpdateFailure("private_host_config_required")
        config = HostConfig.model_validate_json(args.config.read_text())
        config.validate_paths()
        os.umask(0o077)
        with open(config.state_dir / "agent.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            updater = HostUpdater(config)
            def stop(*_):
                updater.stop.set(); updater.lost.set()
            signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
            if args.acknowledge_recovery:
                updater.acknowledge_recovery(args.acknowledge_recovery)
            else:
                updater.run(once=args.once)
    except Exception as exc:
        # Configuration contains DB credentials: never emit validation inputs.
        print(str(exc) if isinstance(exc, UpdateFailure) else "updater_start_failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
