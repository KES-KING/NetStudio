import json
import os
from pathlib import Path

import pytest

from app import update_runtime
from app.updater import HostUpdater, UpdateFailure


REVISION = "a" * 40


class RuntimeCommand:
    def __init__(self, root: Path, *, dirty: bool = False):
        self.root = root
        self.dirty = dirty
        self.calls: list[list[str]] = []

    def run(self, args, *, cwd=None, timeout=300, extra_env=None):
        self.calls.append(args)
        if "rev-parse" in args:
            return f"{REVISION}\n".encode()
        if "status" in args:
            return b" M backend/app/api.py\n" if self.dirty else b""
        if "get-url" in args:
            return b"https://github.com/KES-KING/NetStudio.git\n"
        if args[:2] == ["git", "clone"] or "merge-base" in args:
            return b""
        if args[:2] == ["docker", "inspect"]:
            return json.dumps([{"Config": {"Labels": {
                "com.docker.compose.service": "updater",
                "com.docker.compose.project": "qa-project",
                "com.docker.compose.project.working_dir": "/host/netstudio",
                "com.docker.compose.project.config_files": "/host/netstudio/docker-compose.yml",
            }}}]).encode()
        if args[:3] == ["docker", "context", "show"]:
            return b"default\n"
        if args[:3] == ["docker", "context", "inspect"]:
            return json.dumps([{"Endpoints": {"docker": {"Host": "unix:///var/run/docker.sock"}}}]).encode()
        raise AssertionError(args)


class ArchiveCommand(RuntimeCommand):
    def run(self, args, *, cwd=None, timeout=300, extra_env=None):
        self.calls.append(args)
        blob = b"1" * 40
        if args[:2] == ["git", "clone"] or "read-tree" in args or "add" in args:
            return b""
        if "ls-files" in args:
            assert extra_env and extra_env["GIT_INDEX_FILE"].endswith(".index")
            return b"100644 " + blob + b" 0\tdocker-compose.yml\0"
        if args[:3] == ["git", "rev-list", "origin/main"]:
            return f"{REVISION}\n".encode()
        if "ls-tree" in args:
            # Archive extraction may drop an executable bit without changing
            # the official source content represented by the release.
            return b"100755 blob " + blob + b"\tdocker-compose.yml\0"
        return super().run(args, cwd=cwd, timeout=timeout, extra_env=extra_env)


def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "docker-compose.yml").write_text("services: {}\n")
    return root


def test_container_configuration_discovers_project_and_needs_no_env(tmp_path, monkeypatch):
    root = checkout(tmp_path)
    state = tmp_path / "state"
    command = RuntimeCommand(root)
    monkeypatch.setenv("HOSTNAME", "updater-container")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://qa:secret@postgres:5432/qa")

    config = update_runtime.configuration(root, state, command)

    assert config.project == "qa-project"
    assert config.docker_context == "default"
    assert config.runtime == "container"
    assert config.bootstrap_revision == REVISION
    assert config.database_url.endswith("@postgres:5432/qa")
    assert config.env_file.read_text() == (
        f"COMPOSE_PROJECT_NAME=qa-project\nNETSTUDIO_BUILD_REVISION={REVISION}\n"
    )
    assert config.env_file.stat().st_mode & 0o777 == 0o600
    assert (state / "config.json").stat().st_mode & 0o777 == 0o600
    assert any(args[:2] == ["git", "clone"] for args in command.calls)


def test_container_configuration_preserves_optional_env_without_changing_source(tmp_path, monkeypatch):
    root = checkout(tmp_path)
    original = "POSTGRES_DB=custom\nNETSTUDIO_BUILD_REVISION=unknown\nKEEP=value\n"
    (root / ".env").write_text(original)
    state = tmp_path / "state"
    monkeypatch.setenv("HOSTNAME", "updater-container")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://qa:secret@postgres:5432/qa")

    config = update_runtime.configuration(root, state, RuntimeCommand(root))

    assert (root / ".env").read_text() == original
    assert config.env_file.read_text() == (
        "POSTGRES_DB=custom\nKEEP=value\nCOMPOSE_PROJECT_NAME=qa-project\n"
        f"NETSTUDIO_BUILD_REVISION={REVISION}\n"
    )


def test_dirty_checkout_is_not_claimed_as_a_public_revision(tmp_path):
    root = checkout(tmp_path)
    state = tmp_path / "state"
    update_runtime.private_directory(state)
    with pytest.raises(UpdateFailure, match="update_setup_clean_checkout_required"):
        update_runtime.public_revision(root, state, RuntimeCommand(root, dirty=True))


def test_exact_official_archive_without_git_is_identified(tmp_path):
    root = checkout(tmp_path)
    (root / ".git").rmdir()
    state = tmp_path / "state"
    update_runtime.private_directory(state)
    assert update_runtime.public_revision(root, state, ArchiveCommand(root)) == REVISION


def test_unknown_first_build_is_bound_only_to_verified_container_revision(tmp_path):
    root = checkout(tmp_path)
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    env_file = state / "compose.env"
    env_file.write_text("")
    config = update_runtime.HostConfig(project="qa-project", docker_context="default",
        installation_dir=root, compose_files=[root / "docker-compose.yml"], env_file=env_file,
        state_dir=state, database_url="postgresql+psycopg://qa:secret@postgres:5432/qa",
        runtime="container", bootstrap_revision=REVISION)
    updater = HostUpdater(config, store=object())
    containers = {
        "api": {"Image": f"sha256:{'1' * 64}", "Config": {"Labels": {"org.opencontainers.image.revision": "unknown"}}},
        "collector-worker": {"Image": f"sha256:{'1' * 64}", "Config": {"Labels": {"org.opencontainers.image.revision": "unknown"}}},
        "web": {"Image": f"sha256:{'2' * 64}", "Config": {"Labels": {"org.opencontainers.image.revision": "unknown"}}},
    }
    assert updater.revisions(containers) == REVISION
    binding = json.loads((state / "bootstrap-runtime.json").read_text())
    assert binding["revision"] == REVISION
    assert (state / "bootstrap-runtime.json").stat().st_mode & 0o777 == 0o600

    # Pulling newer source alone must not relabel unchanged running images.
    updater.config.bootstrap_revision = "b" * 40
    assert updater.revisions(containers) == REVISION

    # A deliberate rebuild changes both immutable runtime image identities and
    # may be bound to the newly verified clean source.
    containers["api"]["Image"] = containers["collector-worker"]["Image"] = f"sha256:{'3' * 64}"
    containers["web"]["Image"] = f"sha256:{'4' * 64}"
    assert updater.revisions(containers) == "b" * 40
    containers["web"]["Config"]["Labels"]["org.opencontainers.image.revision"] = "b" * 40
    with pytest.raises(UpdateFailure, match="runtime_revision_mismatch"):
        updater.revisions(containers)


def test_docker_client_state_uses_private_writable_volume(tmp_path, monkeypatch):
    state = tmp_path / "state"
    update_runtime.private_directory(state)
    monkeypatch.setenv("DOCKER_CONFIG", "/run/secrets/docker")

    path = update_runtime.use_writable_docker_config(state)

    assert path == state / "docker-client"
    assert os.environ["DOCKER_CONFIG"] == str(path)
    assert path.stat().st_mode & 0o077 == 0


def test_compose_label_paths_support_docker_desktop_windows(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    compose = root / "docker-compose.yml"
    compose.write_text("services: {}\n")

    assert update_runtime.mounted_compose_path(
        root,
        r"C:\Users\operator\NetStudio",
        r"C:\Users\operator\NetStudio\docker-compose.yml",
    ) == compose
    with pytest.raises(UpdateFailure, match="invalid_host_config"):
        update_runtime.mounted_compose_path(
            root,
            r"C:\Users\operator\NetStudio",
            r"C:\Users\operator\outside.yml",
        )
