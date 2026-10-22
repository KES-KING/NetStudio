import json
from pathlib import Path
from types import SimpleNamespace

from app import update_setup


REVISION = "a" * 40


class SetupCommand:
    def __init__(self, root: Path):
        self.root = root
        self.calls = []

    def run(self, args, *, cwd=None, env=None, check=True):
        self.calls.append((args, cwd, env, check))
        if args[:4] == ["git", "rev-parse", "--verify", "HEAD"]:
            return f"{REVISION}\n".encode()
        if args[:2] == ["git", "status"]:
            return b""
        if args[:4] == ["git", "remote", "get-url", "origin"]:
            return b"https://github.com/KES-KING/NetStudio.git\n"
        if args[:2] == ["git", "fetch"] or args[:2] == ["git", "merge-base"]:
            return b""
        if args[:3] == ["docker", "context", "show"]:
            return b"default\n"
        if args[:3] == ["docker", "context", "inspect"]:
            return json.dumps([{"Endpoints": {"docker": {"Host": "unix:///var/run/docker.sock"}}}]).encode()
        if "config" in args and "--format" in args:
            return json.dumps({
                "name": "qa-project",
                "services": {"postgres": {
                    "environment": {"POSTGRES_USER": "qa", "POSTGRES_PASSWORD": "secret value", "POSTGRES_DB": "qa"},
                    "ports": [{"target": 5432, "published": "19999", "host_ip": "127.0.0.1"}],
                }},
            }).encode()
        if "ps" in args:
            service = args[-1]
            return f"{service}-id\n".encode()
        if args[:4] == ["docker", "--context", "default", "inspect"]:
            identifier = args[-1]
            service = identifier.removesuffix("-id")
            return json.dumps([{"Config": {"Labels": {
                "com.docker.compose.project.config_files": str(self.root / "docker-compose.yml"),
                "org.opencontainers.image.revision": REVISION,
                "com.docker.compose.service": service,
            }}}]).encode()
        if "up" in args:
            return b""
        raise AssertionError(args)


def test_public_checkout_setup_stamps_images_and_writes_private_config(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "docker-compose.yml").write_text("services: {}\n")
    (root / ".env").write_text("NETSTUDIO_BUILD_REVISION=unknown\nKEEP=value\n")
    state = tmp_path / "state"
    command = SetupCommand(root)
    args = SimpleNamespace(installation_dir=root, env_file=None, compose_file=[], docker_context=None,
        project=None, state_dir=state, drain_timeout=900, no_start=True)

    result = update_setup.setup(args, command)

    assert result == {"project": "qa-project", "revision": REVISION,
        "config": str(state / "config.json"), "service": None}
    assert (root / ".env").read_text() == f"NETSTUDIO_BUILD_REVISION={REVISION}\nKEEP=value\n"
    assert (root / ".env").stat().st_mode & 0o777 == 0o600
    config = json.loads((state / "config.json").read_text())
    assert config["project"] == "qa-project"
    assert config["database_url"] == "postgresql+psycopg://qa:secret%20value@127.0.0.1:19999/qa"
    assert (state / "config.json").stat().st_mode & 0o777 == 0o600
    build = next(call for call in command.calls if "up" in call[0])
    assert build[2]["NETSTUDIO_BUILD_REVISION"] == REVISION


def test_env_revision_is_single_and_private(tmp_path):
    path = tmp_path / ".env"
    original_mode = tmp_path.stat().st_mode & 0o777
    path.write_text("A=1\nNETSTUDIO_BUILD_REVISION=old\nNETSTUDIO_BUILD_REVISION=duplicate\n")
    update_setup.set_env_revision(path, REVISION)
    assert path.read_text() == f"A=1\nNETSTUDIO_BUILD_REVISION={REVISION}\n"
    assert path.stat().st_mode & 0o777 == 0o600
    assert tmp_path.stat().st_mode & 0o777 == original_mode


def test_database_url_requires_explicit_loopback_publish():
    config = {"services": {"postgres": {"environment": {
        "POSTGRES_USER": "user/name", "POSTGRES_PASSWORD": "p@ss", "POSTGRES_DB": "db name",
    }, "ports": [{"target": 5432, "published": "5433", "host_ip": "127.0.0.1"}]}}}
    assert update_setup.database_url(config) == (
        "postgresql+psycopg://user%2Fname:p%40ss@127.0.0.1:5433/db%20name"
    )
