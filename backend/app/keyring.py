"""Explicit Docker secret-volume initialization/rotation. Never print key material."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import tempfile
from uuid import uuid4

from .legacy_compat import keyring_path


def probe_bootstrap_path():
    return Path(keyring_path()).with_name("network-probe-bootstrap.token")


def ensure_probe_bootstrap_token():
    """Create the local probe bootstrap capability without ever printing it."""
    path = probe_bootstrap_path()
    if path.exists():
        if not path.is_file() or path.stat().st_mode & 0o077:
            raise SystemExit("Invalid network probe bootstrap token.")
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".network-probe-bootstrap-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(secrets.token_urlsafe(48) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if os.geteuid() == 0:
            os.chown(temporary, 100, 101)
        os.chmod(temporary, 0o600)
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["initialize", "add-key"])
    args = parser.parse_args()
    path = Path(keyring_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        ring = json.loads(path.read_text())
        assert ring["active"] in ring["keys"], "Invalid keyring; not overwritten"
        if args.command == "initialize":
            ensure_probe_bootstrap_token()
            print("Existing encryption keyring preserved.")
            return
    else:
        if args.command != "initialize":
            raise SystemExit("Initialize a keyring first.")
        ring = {"keys": {}}
    identifier = str(uuid4())
    ring["active"] = identifier
    ring["keys"][identifier] = base64.b64encode(secrets.token_bytes(32)).decode()
    descriptor, temporary = tempfile.mkstemp(prefix=".keyring-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(ring, handle)
            handle.flush()
            os.fsync(handle.fileno())
        if os.geteuid() == 0:
            os.chown(temporary, 100, 101)
        os.chmod(temporary, 0o600)
        if args.command == "initialize":
            os.link(temporary, path)  # O_EXCL semantics: competing initialization cannot overwrite.
        else:
            os.replace(temporary, path)
        ensure_probe_bootstrap_token()
        print("Encryption keyring initialized." if args.command == "initialize" else "New active key added; old keys retained. Run rotate-secrets next.")
    finally:
        Path(temporary).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
