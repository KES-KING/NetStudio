"""Bootstrap and supervise the zero-configuration Compose updater.

This module runs only in the dedicated ``updater`` service.  It verifies the
mounted checkout without modifying it, discovers the exact Compose project
from its own container labels, creates private deployment inputs in the
updater state volume, and then starts :class:`HostUpdater`.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import signal
import subprocess
import tempfile
import threading
import time

from . import updates
from .updater import HostConfig, HostUpdater, UpdateFailure


OFFICIAL_REMOTES = {
    "https://github.com/KES-KING/NetStudio.git",
    "https://github.com/KES-KING/NetStudio",
    "git@github.com:KES-KING/NetStudio.git",
    "ssh://git@github.com/KES-KING/NetStudio.git",
}
INSTALLATION_DIR = Path("/workspace")
STATE_DIR = Path("/var/lib/netstudio-updater")


class Command:
    """Small bounded executor used before the main updater runner exists."""

    def run(self, args: list[str], *, cwd: Path | None = None, timeout: int = 300,
            extra_env: dict[str, str] | None = None) -> bytes:
        environment = {key: value for key, value in os.environ.items() if key in {
            "PATH", "HOME", "DOCKER_CONFIG", "DOCKER_HOST", "XDG_RUNTIME_DIR",
            "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR",
        }}
        environment.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")
        environment.update(extra_env or {})
        try:
            result = subprocess.run(args, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise UpdateFailure("update_setup_command_failed") from None
        if result.returncode:
            raise UpdateFailure("update_setup_command_failed")
        if len(result.stdout) > 4_000_000:
            raise UpdateFailure("command_output_limit")
        return result.stdout


def private_directory(path: Path) -> None:
    if path.is_symlink():
        raise UpdateFailure("private_state_directory_required")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_uid != os.getuid():
        raise UpdateFailure("private_state_directory_required")
    path.chmod(0o700)


def write_private(path: Path, value: str) -> None:
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise UpdateFailure("invalid_host_config")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def tree_entries(value: bytes, *, index: bool) -> dict[bytes, tuple[bytes, bool]]:
    entries: dict[bytes, tuple[bytes, bool]] = {}
    for record in value.split(b"\0"):
        if not record:
            continue
        try:
            metadata, path = record.split(b"\t", 1)
            fields = metadata.split()
            mode, blob = fields[0], fields[1] if index else fields[2]
            if (index and fields[2] != b"0") or (not index and fields[1] != b"blob"):
                raise ValueError
        except (IndexError, ValueError):
            raise UpdateFailure("update_revision_unknown") from None
        entries[path] = (blob, mode == b"120000")
    return entries


def archive_revision(root: Path, mirror: Path, state_dir: Path, command: Command) -> str:
    # GitHub ZIP/tar downloads contain no .git directory. Build an index in the
    # private volume using the official repository's ignore rules, then compare
    # the exact path/blob set with every commit reachable from current main.
    # Executable-bit differences introduced by ZIP extraction are ignored;
    # regular-file versus symlink identity is not.
    index_path = state_dir / f"archive-{os.getpid()}-{threading.get_ident()}.index"
    environment = {"GIT_INDEX_FILE": str(index_path)}
    git = ["git", f"--git-dir={mirror / '.git'}", f"--work-tree={root}", "-c", "core.autocrlf=false"]
    try:
        command.run([*git, "read-tree", "--empty"], extra_env=environment)
        command.run([*git, "add", "--all", "--", "."], cwd=root, timeout=600, extra_env=environment)
        local = tree_entries(command.run([*git, "ls-files", "--stage", "-z"], extra_env=environment), index=True)
        revisions = command.run(["git", "rev-list", "origin/main"], cwd=mirror).decode().split()
        for revision in revisions:
            if not updates.SHA.fullmatch(revision):
                raise UpdateFailure("update_revision_unknown")
            remote = tree_entries(command.run(["git", "ls-tree", "-r", "-z", revision], cwd=mirror), index=False)
            if local == remote:
                return revision
    finally:
        index_path.unlink(missing_ok=True)
    raise UpdateFailure("update_setup_public_source_required")


def public_revision(root: Path, state_dir: Path, command: Command) -> str:
    has_git = (root / ".git").exists()
    revision = None
    if has_git:
        git = ["git", "-c", f"safe.directory={root}"]
        revision = command.run([*git, "rev-parse", "--verify", "HEAD"], cwd=root).decode().strip()
        if not updates.SHA.fullmatch(revision):
            raise UpdateFailure("update_revision_unknown")
        if command.run([*git, "status", "--porcelain", "--untracked-files=all"], cwd=root).strip():
            raise UpdateFailure("update_setup_clean_checkout_required")
        remote = command.run([*git, "remote", "get-url", "origin"], cwd=root).decode().strip()
        if remote not in OFFICIAL_REMOTES:
            raise UpdateFailure("update_setup_official_remote_required")

    # The source is mounted read-only. Verify publication/ancestry (or identify
    # an exact official archive) in a disposable private clone.
    with tempfile.TemporaryDirectory(prefix="verify-", dir=state_dir) as temporary:
        mirror = Path(temporary) / "source"
        command.run(["git", "clone", "--quiet", "--no-checkout", "--filter=blob:none",
            "--single-branch", "--branch", "main", f"{updates.REPOSITORY_URL}.git", str(mirror)], timeout=600)
        if not has_git:
            return archive_revision(root, mirror, state_dir, command)
        try:
            command.run(["git", "merge-base", "--is-ancestor", revision, "origin/main"], cwd=mirror)
        except UpdateFailure:
            raise UpdateFailure("revision_not_forward") from None
    return revision


def mounted_compose_path(root: Path, host_root: str, raw: str) -> Path:
    """Map a Compose host path to the checkout mounted at ``root``.

    Docker Desktop may record Compose labels with Windows paths even though the
    updater itself is a Linux container.  Parse both path grammars, but accept
    only files underneath the labelled project directory and the read-only
    checkout mount.
    """
    relative = None
    for path_type in (PurePosixPath, PureWindowsPath):
        base = path_type(host_root)
        candidate = path_type(raw)
        if not base.is_absolute() or not candidate.is_absolute():
            continue
        try:
            relative = candidate.relative_to(base)
            break
        except ValueError:
            continue
    if relative is None or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise UpdateFailure("invalid_host_config")
    path = (root.joinpath(*relative.parts)).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise UpdateFailure("invalid_host_config")
    return path


def project_metadata(root: Path, command: Command) -> tuple[str, list[Path]]:
    identifier = os.environ.get("HOSTNAME", "").strip()
    if not identifier:
        raise UpdateFailure("project_identity_mismatch")
    value = json.loads(command.run(["docker", "inspect", identifier]))[0]
    labels = value.get("Config", {}).get("Labels", {})
    if labels.get("com.docker.compose.service") != "updater":
        raise UpdateFailure("project_identity_mismatch")
    project = labels.get("com.docker.compose.project", "")
    host_root = labels.get("com.docker.compose.project.working_dir", "")
    raw_files = labels.get("com.docker.compose.project.config_files", "")
    if not project or not isinstance(host_root, str) or not host_root or not raw_files:
        raise UpdateFailure("project_identity_mismatch")
    files: list[Path] = []
    for raw in raw_files.split(","):
        files.append(mounted_compose_path(root, host_root, raw))
    return project, files


def compose_environment(root: Path, state_dir: Path, project: str, revision: str) -> Path:
    source = root / ".env"
    if source.is_symlink():
        raise UpdateFailure("invalid_host_config")
    contents = source.read_text() if source.is_file() else ""
    if len(contents.encode()) > 1_000_000:
        raise UpdateFailure("invalid_host_config")
    replacements = {"COMPOSE_PROJECT_NAME": project, "NETSTUDIO_BUILD_REVISION": revision}
    output: list[str] = []
    for line in contents.splitlines():
        key = line.split("=", 1)[0].strip()
        if key not in replacements:
            output.append(line)
    output.extend(f"{key}={value}" for key, value in replacements.items())
    path = state_dir / "compose.env"
    write_private(path, "\n".join(output) + "\n")
    return path


def configuration(root: Path = INSTALLATION_DIR, state_dir: Path = STATE_DIR,
        command: Command | None = None) -> HostConfig:
    command = command or Command()
    if not root.is_dir():
        raise UpdateFailure("invalid_host_config")
    private_directory(state_dir)
    revision = public_revision(root, state_dir, command)
    project, files = project_metadata(root, command)
    # `use_api_socket` maps the host-selected local Engine to the container's
    # built-in default socket.  Do not persist a host-only context name such as
    # `desktop-linux`; that definition is not part of the private client state.
    context = "default"
    endpoint = json.loads(command.run(["docker", "context", "inspect", context]))[0]["Endpoints"]["docker"]["Host"]
    if not isinstance(endpoint, str) or not endpoint.startswith("unix://"):
        raise UpdateFailure("local_docker_context_required")
    env_file = compose_environment(root, state_dir, project, revision)
    config = HostConfig(project=project, docker_context=context, installation_dir=root,
        compose_files=files, env_file=env_file, state_dir=state_dir,
        database_url=os.environ.get("DATABASE_URL", ""), runtime="container",
        bootstrap_revision=revision)
    config.validate_paths()
    write_private(state_dir / "config.json", config.model_dump_json(indent=2) + "\n")
    return config


def use_writable_docker_config(state_dir: Path) -> Path:
    """Keep Docker/BuildKit client state on the updater's private volume.

    ``use_api_socket`` intentionally exposes the Engine through a read-only
    container, but Compose may point ``DOCKER_CONFIG`` at an absent read-only
    ``/run/secrets/docker`` directory when the host has no client credentials.
    Builds need to create BuildKit metadata, so use a private writable path.
    NetStudio only pulls public base images and never needs host registry
    credentials inside the updater.
    """
    path = state_dir / "docker-client"
    private_directory(path)
    os.environ["DOCKER_CONFIG"] = str(path)
    return path


def main() -> None:
    os.umask(0o077)
    stopping = threading.Event()
    active: list[HostUpdater] = []

    def stop(*_args):
        stopping.set()
        if active:
            active[0].stop.set()
            active[0].lost.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping.is_set():
        try:
            config = configuration()
            use_writable_docker_config(config.state_dir)
            with open(config.state_dir / "agent.lock", "a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                updater = HostUpdater(config)
                active[:] = [updater]
                updater.run()
        except Exception as exc:
            # Configuration may include credentials.  Emit only stable error
            # codes and retry so a temporarily unavailable GitHub/Engine does
            # not require a second operator command.
            print(str(exc) if isinstance(exc, UpdateFailure) else "updater_start_failed", flush=True)
        finally:
            active.clear()
        stopping.wait(30)


if __name__ == "__main__":
    main()
