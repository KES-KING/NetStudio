"""The rename must not strand encrypted credentials or weaken old configuration."""
import base64
import json
import os
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app import keyring
from app.auth import Auth, COOKIE
from app.legacy_compat import decrypt_credential, getenv, keyring_path
from app.security import SecretStoreError
from app.ssh import ConnectionPolicyError, target_allowed
from conftest import add_device, login


def test_new_settings_take_precedence_including_empty(monkeypatch):
    monkeypatch.delenv("NETSTUDIO_SSH_ALLOWED_CIDRS", raising=False)
    monkeypatch.setenv("STOCC_SSH_ALLOWED_CIDRS", "192.0.2.0/24")
    assert getenv("NETSTUDIO_SSH_ALLOWED_CIDRS") == "192.0.2.0/24"
    monkeypatch.setenv("NETSTUDIO_SSH_ALLOWED_CIDRS", "")
    assert getenv("NETSTUDIO_SSH_ALLOWED_CIDRS") == ""


def test_old_production_and_origin_restrictions_still_apply(monkeypatch):
    for name in ("NETSTUDIO_ENV", "NETSTUDIO_ALLOWED_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("STOCC_ENV", "production")
    monkeypatch.setenv("STOCC_ALLOWED_ORIGINS", "https://netstudio.example.org")
    auth = Auth(None)
    assert auth.production and auth.origins == {"https://netstudio.example.org"}
    monkeypatch.setenv("STOCC_ALLOWED_ORIGINS", "http://netstudio.example.org")
    with pytest.raises(RuntimeError, match="HTTPS"):
        Auth(None)


def test_legacy_cidr_ceiling_still_enforced(system, monkeypatch):
    client, store, _, _ = system
    login(client)
    device = store.get_device(add_device(client, management_address="192.0.2.17")["id"])
    monkeypatch.delenv("NETSTUDIO_SSH_ALLOWED_CIDRS")
    monkeypatch.setenv("STOCC_SSH_ALLOWED_CIDRS", "198.51.100.0/24")
    with pytest.raises(ConnectionPolicyError, match="target_network_denied"):
        target_allowed(store, device)
    monkeypatch.setenv("STOCC_SSH_ALLOWED_CIDRS", "invalid")
    with pytest.raises(ConnectionPolicyError, match="invalid_target_network_policy"):
        target_allowed(store, device)


def test_default_keyring_and_existing_file_are_not_replaced(tmp_path, monkeypatch):
    monkeypatch.delenv("NETSTUDIO_KEYRING_FILE", raising=False)
    monkeypatch.delenv("STOCC_KEYRING_FILE", raising=False)
    assert keyring_path(directory=tmp_path) == str(tmp_path / "netstudio-keyring.json")
    old = tmp_path / "stocc-keyring.json"
    old.write_text(json.dumps({"active": "old", "keys": {"old": base64.b64encode(os.urandom(32)).decode()}}))
    original = old.read_bytes()
    assert keyring_path(directory=tmp_path) == str(old)
    monkeypatch.setattr(keyring, "keyring_path", lambda: keyring_path(directory=tmp_path))
    monkeypatch.setattr(sys, "argv", ["keyring", "initialize"])
    keyring.main()
    assert old.read_bytes() == original
    bootstrap = tmp_path / "network-probe-bootstrap.token"
    assert bootstrap.is_file() and bootstrap.stat().st_mode & 0o077 == 0
    assert not (tmp_path / "netstudio-keyring.json").exists()
    (tmp_path / "netstudio-keyring.json").write_text("{}")
    with pytest.raises(SecretStoreError, match="ambiguous_keyring_paths"):
        keyring_path(directory=tmp_path)
    assert keyring_path(str(old), directory=tmp_path) == str(old)
    monkeypatch.setenv("STOCC_KEYRING_FILE", str(old))
    assert keyring_path(directory=tmp_path) == str(old)


@pytest.mark.parametrize("protocol", [None, "snmp"])
def test_legacy_envelopes_read_without_mutation_and_new_writes_use_new_aad(system, protocol):
    client, store, app, _ = system
    login(client)
    device = add_device(client)["id"]
    vault = app.state.vault
    key_id, keys = vault.keyring()
    nonce = os.urandom(12)
    credentials = {"username": "lab", "password": "synthetic-credential"}
    suffix = f"{device}:{key_id}" + (f":{protocol}" if protocol else "")
    ciphertext = AESGCM(keys[key_id]).encrypt(nonce, json.dumps(credentials).encode(), f"stocc:{suffix}".encode())
    table = store.protocol_secrets if protocol else store.secrets
    values = dict(device_id=device, key_id=key_id, nonce=nonce, ciphertext=ciphertext)
    if protocol:
        values.update(protocol=protocol, metadata={})
    with store.engine.begin() as conn:
        conn.execute(table.insert().values(**values))
    assert (vault.get_protocol(device, protocol) if protocol else vault.get(device)) == credentials
    with store.engine.connect() as conn:
        assert conn.execute(sa.select(table.c.ciphertext)).scalar_one() == ciphertext
    encoded = vault.encode(device, credentials, protocol)
    cipher = AESGCM(keys[key_id])
    assert json.loads(cipher.decrypt(encoded["nonce"], encoded["ciphertext"], f"netstudio:{suffix}".encode())) == credentials
    with pytest.raises(InvalidTag):
        cipher.decrypt(encoded["nonce"], encoded["ciphertext"], f"stocc:{suffix}".encode())


@pytest.mark.parametrize("prefix", ["stocc", "netstudio"])
def test_envelope_device_protocol_and_integrity_boundaries(prefix):
    key, nonce = os.urandom(32), os.urandom(12)
    encrypted = AESGCM(key).encrypt(nonce, b"{}", f"{prefix}:device:key:snmp".encode())
    assert decrypt_credential(key, nonce, encrypted, "device", "key", "snmp") == b"{}"
    for device, key_id, protocol, value in [
        ("other", "key", "snmp", encrypted), ("device", "other", "snmp", encrypted),
        ("device", "key", None, encrypted), ("device", "key", "snmp", encrypted[:-1] + bytes([encrypted[-1] ^ 1])),
    ]:
        with pytest.raises(InvalidTag):
            decrypt_credential(key, nonce, value, device, key_id, protocol)


def test_new_cookie_and_api_identity(system):
    client, _, _, _ = system
    login(client)
    assert COOKIE == "netstudio_session"
    assert client.cookies.get(COOKIE)
    assert not client.cookies.get("stocc_session")
    assert client.get("/healthz").json()["service"] == "netstudio-api"
    assert client.get("/readyz").json()["service"] == "netstudio-api"
    assert client.get("/openapi.json").json()["info"]["title"] == "NetStudio API"
    token = client.cookies.get(COOKIE)
    client.cookies.clear()
    client.cookies.set("stocc_session", token)
    assert client.get("/api/v1/session/me").status_code == 401


def test_product_identifiers_and_github_links_stay_canonical():
    root = Path(__file__).resolve().parents[2]
    package = json.loads((root / "frontend/package.json").read_text())
    lock = json.loads((root / "frontend/package-lock.json").read_text())
    assert package["name"] == lock["name"] == lock["packages"][""]["name"] == "netstudio-web"
    assert package["repository"]["url"] == "git+https://github.com/KES-KING/NetStudio.git"
    assert package["homepage"] == "https://github.com/KES-KING/NetStudio#readme"
    for directory in ["backend/app", "frontend/app", "frontend/lib", "frontend/components"]:
        for path in (root / directory).rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx", ".css"} or path.name == "legacy_compat.py":
                continue
            assert "stocc" not in path.read_text().lower(), path.relative_to(root)
