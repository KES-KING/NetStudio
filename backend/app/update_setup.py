"""Prepare a clean public checkout for the opt-in host updater.

This command is intentionally run on the host.  It stamps the exact published
checkout into the Docker images, preserves the existing Compose project and
data volumes, writes a private updater configuration, and starts the updater as
a user service (or a detached process when no user service manager exists).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote

from .database import Store
from .updater import HostConfig, UpdateFailure
from . import updates


OFFICIAL_REMOTES = {
    "https://github.com/KES-KING/NetStudio.git",
    "https://github.com/KES-KING/NetStudio",
    "git@github.com:KES-KING/NetStudio.git",
    "ssh://git@github.com/KES-KING/NetStudio.git",
}
PROJECT = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


class Command:
    def run(self, args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
            check: bool = True) -> bytes:
        result = subprocess.run(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if check and result.returncode:
            raise UpdateFailure("update_setup_command_failed")
        return result.stdout


def exact_public_revision(root: Path, command: Command) -> str:
    if not (root / ".git").exists():
        raise UpdateFailure("update_setup_git_checkout_required")
    revision = command.run(["git", "rev-parse", "--verify", "HEAD"], cwd=root).decode().strip()
    if not updates.SHA.fullmatch(revision):
        raise UpdateFailure("update_revision_unknown")
    if command.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root).strip():
        raise UpdateFailure("update_setup_clean_checkout_required")
    remote = command.run(["git", "remote", "get-url", "origin"], cwd=root).decode().strip()
    if remote not in OFFICIAL_REMOTES:
        raise UpdateFailure("update_setup_official_remote_required")
    command.run(["git", "fetch", "--quiet", "--no-tags", "origin", "main"], cwd=root)
    command.run(["git", "merge-base", "--is-ancestor", revision, "FETCH_HEAD"], cwd=root)
    return revision


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


def set_env_revision(path: Path, revision: str) -> None:
    if path.is_symlink() or (path.exists() and path.stat().st_uid != os.getuid()):
        raise UpdateFailure("invalid_host_config")
    lines = path.read_text().splitlines() if path.exists() else []
    result: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith("NETSTUDIO_BUILD_REVISION="):
            if not replaced:
                result.append(f"NETSTUDIO_BUILD_REVISION={revision}")
                replaced = True
            continue
        result.append(line)
    if not replaced:
        result.append(f"NETSTUDIO_BUILD_REVISION={revision}")
    write_private(path, "\n".join(result) + "\n")


def docker_context(command: Command) -> str:
    context = command.run(["docker", "context", "show"]).decode().strip()
    if not context:
        raise UpdateFailure("local_docker_context_required")
    data = json.loads(command.run(["docker", "context", "inspect", context]))
    endpoint = data[0]["Endpoints"]["docker"]["Host"]
    if not isinstance(endpoint, str) or not endpoint.startswith("unix://"):
        raise UpdateFailure("local_docker_context_required")
    return context


def compose_command(context: str, root: Path, env_file: Path, files: list[Path], project: str | None = None) -> list[str]:
    value = ["docker", "--context", context, "compose"]
    if project:
        value += ["--project-name", project]
    value += ["--project-directory", str(root), "--env-file", str(env_file)]
    for path in files:
        value += ["-f", str(path)]
    return value


def discover_compose_files(root: Path, env_file: Path, context: str, requested: list[Path], command: Command) -> list[Path]:
    files = [path.resolve() for path in requested] if requested else [(root / "docker-compose.yml").resolve()]
    base = compose_command(context, root, env_file, files)
    ids = command.run([*base, "ps", "--all", "--quiet", "api"], check=False).decode().split()
    if len(ids) == 1 and not requested:
        inspected = json.loads(command.run(["docker", "--context", context, "inspect", ids[0]]))[0]
        label = inspected["Config"]["Labels"].get("com.docker.compose.project.config_files", "")
        if label:
            files = [Path(value).resolve() for value in label.split(",")]
    for path in files:
        if not path.is_file() or not path.is_relative_to(root):
            raise UpdateFailure("invalid_host_config")
    return files


def render_compose(base: list[str], revision: str, command: Command) -> dict:
    environment = os.environ.copy()
    environment["NETSTUDIO_BUILD_REVISION"] = revision
    return json.loads(command.run([*base, "config", "--format", "json"], env=environment))


def database_url(config: dict) -> str:
    postgres = config.get("services", {}).get("postgres", {})
    environment = postgres.get("environment", {})
    ports = postgres.get("ports", [])
    published = [item for item in ports if int(item.get("target", 0)) == 5432
        and item.get("host_ip") in {"127.0.0.1", "localhost"}]
    if len(published) != 1:
        raise UpdateFailure("database_must_be_explicit_loopback")
    user = environment.get("POSTGRES_USER")
    password = environment.get("POSTGRES_PASSWORD")
    name = environment.get("POSTGRES_DB")
    if not all(isinstance(value, str) and value for value in (user, password, name)):
        raise UpdateFailure("database_project_mismatch")
    port = int(published[0]["published"])
    return f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}@127.0.0.1:{port}/{quote(name, safe='')}"


def verify_runtime_revision(base: list[str], context: str, revision: str, command: Command) -> None:
    for service in ("api", "web", "collector-worker"):
        ids = command.run([*base, "ps", "--all", "--quiet", service]).decode().split()
        if len(ids) != 1:
            raise UpdateFailure("existing_project_required")
        value = json.loads(command.run(["docker", "--context", context, "inspect", ids[0]]))[0]
        if value["Config"]["Labels"].get("org.opencontainers.image.revision") != revision:
            raise UpdateFailure("update_revision_unknown")


def systemd_quote(value: str) -> str:
    return '"' + value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"') + '"'


def start_agent(config_path: Path, root: Path, project: str, command: Command) -> str:
    executable = Path(sys.executable).resolve()
    unit = f"netstudio-updater-{project}.service"
    systemctl = shutil.which("systemctl")
    if systemctl:
        probe = subprocess.run([systemctl, "--user", "show-environment"], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if probe.returncode == 0:
            directory = Path.home() / ".config/systemd/user"
            private_directory(directory)
            unit_path = directory / unit
            body = "\n".join((
                "[Unit]", "Description=NetStudio host updater", "After=network-online.target", "Wants=network-online.target", "",
                "[Service]", "Type=simple", f"WorkingDirectory={systemd_quote(str(root))}",
                f"ExecStart={systemd_quote(str(executable))} -m app.updater --config {systemd_quote(str(config_path))}",
                "Restart=on-failure", "RestartSec=15", "UMask=0077", "NoNewPrivileges=true", "",
                "[Install]", "WantedBy=default.target", "",
            ))
            write_private(unit_path, body)
            unit_path.chmod(0o644)
            command.run([systemctl, "--user", "daemon-reload"])
            command.run([systemctl, "--user", "enable", "--now", unit])
            return f"systemd-user:{unit}"
    state = config_path.parent
    pid_path = state / "agent.pid"
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            os.kill(pid, 0)
            return f"detached:{pid}"
        except (ValueError, ProcessLookupError, PermissionError):
            pass
    log = open(state / "agent.log", "ab", buffering=0)
    process = subprocess.Popen([str(executable), "-m", "app.updater", "--config", str(config_path)],
        cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    log.close()
    write_private(pid_path, f"{process.pid}\n")
    return f"detached:{process.pid}"


def wait_for_agent(url: str, timeout: float = 30) -> None:
    store = Store(url)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if updates.agent_online(updates.read(store)):
                return
            time.sleep(.5)
    finally:
        store.engine.dispose()
    raise UpdateFailure("update_agent_unavailable")


def setup(args, command: Command | None = None) -> dict:
    command = command or Command()
    root = args.installation_dir.resolve()
    if not root.is_dir():
        raise UpdateFailure("invalid_host_config")
    env_file = (args.env_file or root / ".env").resolve()
    if not env_file.exists():
        example = root / ".env.example"
        if not example.is_file():
            raise UpdateFailure("invalid_host_config")
        write_private(env_file, example.read_text())
    revision = exact_public_revision(root, command)
    context = args.docker_context or docker_context(command)
    files = discover_compose_files(root, env_file, context, args.compose_file, command)
    initial = compose_command(context, root, env_file, files)
    rendered = render_compose(initial, revision, command)
    project = args.project or rendered.get("name")
    if not isinstance(project, str) or not PROJECT.fullmatch(project):
        raise UpdateFailure("invalid_host_config")
    base = compose_command(context, root, env_file, files, project)
    set_env_revision(env_file, revision)
    environment = os.environ.copy()
    environment["NETSTUDIO_BUILD_REVISION"] = revision
    command.run([*base, "up", "--build", "-d", "--wait"], env=environment)
    verify_runtime_revision(base, context, revision, command)
    url = database_url(rendered)
    state_dir = (args.state_dir or Path.home() / ".local/state/netstudio-updater" / project).resolve()
    private_directory(state_dir)
    config_path = state_dir / "config.json"
    config = HostConfig(project=project, docker_context=context, installation_dir=root,
        compose_files=files, env_file=env_file, state_dir=state_dir, database_url=url,
        drain_timeout=args.drain_timeout)
    config.validate_paths()
    write_private(config_path, config.model_dump_json(indent=2) + "\n")
    result = {"project": project, "revision": revision, "config": str(config_path), "service": None}
    if not args.no_start:
        result["service"] = start_agent(config_path, root, project, command)
        wait_for_agent(url)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup"])
    parser.add_argument("--installation-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--compose-file", type=Path, action="append", default=[])
    parser.add_argument("--docker-context")
    parser.add_argument("--project")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--drain-timeout", type=int, default=900)
    parser.add_argument("--no-start", action="store_true", help="Prepare private configuration but do not start the updater")
    args = parser.parse_args()
    try:
        result = setup(args)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print(str(exc) if isinstance(exc, UpdateFailure) else "update_setup_failed", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
