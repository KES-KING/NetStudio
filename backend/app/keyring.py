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
        print("Encryption keyring initialized." if args.command == "initialize" else "New active key added; old keys retained. Run rotate-secrets next.")
    finally:
        Path(temporary).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
