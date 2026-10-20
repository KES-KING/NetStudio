"""Read-only compatibility for installations created before the NetStudio rename.

Keep retired identifiers here, never in new credentials or product branding.
Do not remove this bridge until old configuration and encrypted records migrate.
"""
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .security import SecretStoreError


def getenv(name, default=None):
    """A present new setting (even empty) wins over its old spelling."""
    if name in os.environ:
        return os.environ[name]
    legacy = name.replace("NETSTUDIO_", "STOCC_", 1)
    return os.environ.get(legacy, default)


def keyring_path(explicit=None, directory="/run/secrets"):
    configured = explicit if explicit is not None else getenv("NETSTUDIO_KEYRING_FILE")
    if configured is not None:
        return str(configured)
    current = Path(directory) / "netstudio-keyring.json"
    previous = Path(directory) / "stocc-keyring.json"
    # A pre-existing old volume must never silently receive a second new keyring.
    if current.exists() and previous.exists():
        raise SecretStoreError("ambiguous_keyring_paths")
    return str(previous if previous.exists() else current)


def decrypt_credential(key, nonce, ciphertext, device_id, key_id, protocol=None):
    suffix = f"{device_id}:{key_id}" + (f":{protocol}" if protocol else "")
    cipher = AESGCM(key)
    try:
        return cipher.decrypt(nonce, ciphertext, f"netstudio:{suffix}".encode())
    except InvalidTag:
        # Old envelopes remain device/key/protocol-bound, not unauthenticated.
        return cipher.decrypt(nonce, ciphertext, f"stocc:{suffix}".encode())
