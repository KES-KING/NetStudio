"""AES-256-GCM envelope encryption with per-record AAD and versioned file keys."""
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import sqlalchemy as sa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .security import SecretStoreError
from .legacy_compat import decrypt_credential, keyring_path


class CredentialVault:
    def __init__(self, store, key_file=None):
        self.store = store
        self.key_file = keyring_path(key_file)

    def keyring(self):
        try:
            doc = json.loads(Path(self.key_file).read_text())
            keys = {k: base64.b64decode(v, validate=True) for k, v in doc["keys"].items()}
            if doc["active"] not in keys or any(len(v) != 32 for v in keys.values()):
                raise ValueError()
            return doc["active"], keys
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise SecretStoreError("encryption_key_unavailable") from error

    def encode(self, device_id, credentials, protocol=None):
        key_id, keys = self.keyring()
        nonce = os.urandom(12)
        purpose = f"netstudio:{device_id}:{key_id}" + (f":{protocol}" if protocol else "")
        ciphertext = AESGCM(keys[key_id]).encrypt(nonce, json.dumps(credentials).encode(), purpose.encode())
        return {"device_id": device_id, "key_id": key_id, "nonce": nonce, "ciphertext": ciphertext}

    def save(self, device_id, credentials, conn):
        envelope = self.encode(device_id, credentials)
        conn.execute(self.store.secrets.delete().where(self.store.secrets.c.device_id == device_id))
        conn.execute(self.store.secrets.insert().values(**envelope))

    def get(self, device_id):
        with self.store.engine.connect() as conn:
            row = conn.execute(sa.select(self.store.secrets).where(self.store.secrets.c.device_id == device_id)).mappings().first()
        if not row:
            raise SecretStoreError("credentials_missing")
        try:
            _, keys = self.keyring()
            raw = decrypt_credential(keys[row["key_id"]], row["nonce"], row["ciphertext"], device_id, row["key_id"])
            return json.loads(raw)
        except SecretStoreError:
            raise
        except Exception as error:
            raise SecretStoreError("credential_decryption_failed") from error

    def save_protocol(self, device_id, protocol, credentials, metadata, conn):
        if protocol not in {"snmp", "snmp_v2c"}:
            raise SecretStoreError("unsupported_secret_protocol")
        table = self.store.protocol_secrets
        conn.execute(table.delete().where(table.c.device_id == device_id, table.c.protocol == protocol))
        conn.execute(table.insert().values(**self.encode(device_id, credentials, protocol),
                                          protocol=protocol, metadata=metadata))

    def get_protocol(self, device_id, protocol):
        table = self.store.protocol_secrets
        with self.store.engine.connect() as conn:
            row = conn.execute(sa.select(table).where(
                table.c.device_id == device_id, table.c.protocol == protocol)).mappings().first()
        if not row:
            raise SecretStoreError("snmp_credentials_missing")
        try:
            _, keys = self.keyring()
            raw = decrypt_credential(keys[row["key_id"]], row["nonce"], row["ciphertext"], device_id, row["key_id"], protocol)
            return json.loads(raw)
        except SecretStoreError:
            raise
        except Exception as error:
            raise SecretStoreError("credential_decryption_failed") from error

    def save_controller(self, controller_id, credentials, *, auth_kind, scopes, expires_at, conn):
        """Store API credentials in a controller-scoped envelope, never a device secret."""
        key_id, keys = self.keyring()
        nonce = os.urandom(12)
        purpose = f"netstudio:controller:{controller_id}:{key_id}:api"
        ciphertext = AESGCM(keys[key_id]).encrypt(
            nonce, json.dumps(credentials).encode(), purpose.encode()
        )
        table = self.store.api_controller_secrets
        conn.execute(table.delete().where(table.c.controller_id == controller_id))
        conn.execute(table.insert().values(
            controller_id=controller_id, auth_kind=auth_kind, scopes=scopes,
            expires_at=expires_at, key_id=key_id, nonce=nonce,
            ciphertext=ciphertext, updated_at=datetime.now(timezone.utc),
        ))

    def get_controller(self, controller_id):
        table = self.store.api_controller_secrets
        with self.store.engine.connect() as conn:
            row = conn.execute(sa.select(table).where(
                table.c.controller_id == controller_id)).mappings().first()
        if not row:
            raise SecretStoreError("controller_credentials_missing")
        try:
            _, keys = self.keyring()
            purpose = f"netstudio:controller:{controller_id}:{row['key_id']}:api"
            raw = AESGCM(keys[row["key_id"]]).decrypt(
                row["nonce"], row["ciphertext"], purpose.encode()
            )
            return json.loads(raw), {
                "auth_kind": row["auth_kind"], "scopes": list(row["scopes"]),
                "expires_at": row["expires_at"],
            }
        except SecretStoreError:
            raise
        except Exception as error:
            raise SecretStoreError("credential_decryption_failed") from error


def credential_values(value):
    result = {"username": value.username, "method": value.method}
    for field in ("password", "private_key", "passphrase"):
        secret = getattr(value, field)
        result[field] = secret.get_secret_value() if secret else ""
    if not result["password" if value.method == "password" else "private_key"]:
        raise ValueError("credential_secret_required")
    return result
