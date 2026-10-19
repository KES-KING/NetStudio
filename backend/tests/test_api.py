import base64
import json
import os
import time
from datetime import timedelta

import asyncssh
import pytest
import sqlalchemy as sa
from starlette.websockets import WebSocketDisconnect

from app.auth import digest
from app.database import now
from app.security import SecretStoreError
from conftest import ORIGIN, PASSWORD, add_device, inventory, login, observation, prepare


def test_authentication_csrf_and_empty_production_inventory(system):
    client, _, _, _ = system
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    assert client.get("/api/v1/devices", headers={"X-Stocc-User": "admin"}).status_code == 401
    assert client.post("/api/v1/session/login", json={"username": "admin", "password": PASSWORD}).status_code == 403
    session = login(client)
    assert "terminal.open" in session["permissions"]
    assert client.get("/api/v1/devices").json() == []
    assert client.get("/api/v1/overview").json()["devices"] == []
    assert client.post("/api/v1/devices", json={"name": "x", "management_address": "127.0.0.1", "site": "lab"}, headers={"x-csrf-token": "bad"}).status_code == 403
    assert client.get("/api/v1/session/me").headers["cache-control"] == "no-store"


def test_site_and_terminal_permission_are_independent(system):
    client, _, _, _ = system
    login(client); device = add_device(client)
    login(client, "viewer")
    assert client.get(f"/api/v1/devices/{device['id']}").status_code == 200
    assert client.post(f"/api/v1/devices/{device['id']}/ssh-sessions").status_code == 404
    assert client.put(f"/api/v1/devices/{device['id']}/credentials", json={"username": "ssh", "password": "secret"}).status_code == 404
    assert client.get("/api/v1/audit").status_code == 403
    login(client, "outsider")
    assert client.get("/api/v1/overview").json()["devices"] == []
    assert client.get(f"/api/v1/devices/{device['id']}").status_code == 404


def test_credentials_encrypted_not_returned_blank_preserved_and_deleted(system):
    client, store, app, _ = system
    login(client); device = add_device(client, credentials={"username": "ssh", "password": "device-secret-test"})
    assert device["credential_configured"] is True
    for path in ["/api/v1/devices", "/api/v1/overview", "/api/v1/audit"]:
        assert "device-secret-test" not in client.get(path).text
    with store.engine.connect() as conn:
        row = conn.execute(sa.select(store.secrets)).mappings().one()
        assert b"device-secret-test" not in row["ciphertext"]
        assert len(row["nonce"]) == 12
    response = client.put(f"/api/v1/devices/{device['id']}/credentials", json={"username": "changed", "password": ""})
    assert response.json()["unchanged"] is True
    assert app.state.vault.get(device["id"])["username"] == "ssh"
    client.put(f"/api/v1/devices/{device['id']}/credentials", json={"username": "ssh", "password": "replacement-test"})
    with store.engine.connect() as conn:
        updated = conn.execute(sa.select(store.secrets)).mappings().one()
    assert updated["nonce"] != row["nonce"]
    assert client.delete(f"/api/v1/devices/{device['id']}/credentials").status_code == 200
    assert not client.get(f"/api/v1/devices/{device['id']}").json()["credential_configured"]


def test_vault_tamper_missing_key_and_rotation(system):
    client, store, app, keyfile = system
    login(client); device = add_device(client, credentials={"username": "ssh", "password": "test-secret"})
    ring = json.loads(keyfile.read_text()); ring["active"] = "v2"; ring["keys"]["v2"] = base64.b64encode(os.urandom(32)).decode(); keyfile.write_text(json.dumps(ring))
    original = app.state.vault.get(device["id"])
    with store.engine.begin() as conn:
        app.state.vault.save(device["id"], original, conn)
    del ring["keys"]["test-v1"]; keyfile.write_text(json.dumps(ring))
    assert app.state.vault.get(device["id"])["password"] == "test-secret"
    with store.engine.begin() as conn:
        conn.execute(store.secrets.update().values(ciphertext=b"tampered"))
    with pytest.raises(SecretStoreError, match="credential_decryption_failed"):
        app.state.vault.get(device["id"])
    keyfile.unlink()
    with pytest.raises(SecretStoreError, match="encryption_key_unavailable"):
        app.state.vault.encode(device["id"], original)


def test_invalid_secret_input_is_not_echoed_and_target_is_inventory_only(system):
    client, _, _, _ = system
    login(client)
    response = client.post("/api/v1/devices", json={"name": "bad", "site": "lab", "management_address": "https://example.com", "credentials": {"username": "bad user", "password": "DO-NOT-ECHO"}})
    assert response.status_code == 422 and "DO-NOT-ECHO" not in response.text
    device = add_device(client)
    assert client.post(f"/api/v1/devices/{device['id']}/ssh-sessions").json()["detail"]["code"] == "host_key_required"


def test_telemetry_semantics_unknown_stale_health_and_topology(system):
    client, _, _, _ = system
    login(client); device = prepare(client); path = f"/api/v1/devices/{device['id']}/observations"
    data = observation(health={"status": "warning", "evaluation": "Source reported fan alarm", "alerts": ["Fan alarm"]})
    assert client.post(path, json=data).status_code == 201
    row = client.get("/api/v1/overview").json()["devices"][0]
    assert row["reachability"] == "reachable" and row["health_status"] == "warning"
    assert row["ports"]["counts"] == {"up": 1, "down": 1, "disabled": 1, "unknown": 1}
    assert row["ports"]["total"] == 4 and row["ports"]["active_ratio"] == 25
    assert row["ports"]["rx_bps"] == 800 and row["ports"]["tx_bps"] == 1600
    assert all(link["relation"] == "l3" for link in row["topology"]["links"])
    assert all("127.0.0.1" not in node["name"] for node in row["topology"]["nodes"])
    assert client.post(path, json=data).status_code == 409
    assert client.post(path, json=observation(interfaces=[{"interface_id": "missing"}])).status_code == 422


def test_stale_observation_not_zero_or_healthy_and_last_success_outside_range(system):
    client, _, _, _ = system
    login(client); device = prepare(client)
    client.post(f"/api/v1/devices/{device['id']}/observations", json=observation(now() - timedelta(hours=2), health={"status": "ok", "evaluation": "Source clear"}))
    row = client.get("/api/v1/overview?minutes=5").json()["devices"][0]
    assert row["data_state"] == "stale" and row["health_status"] == "unknown"
    assert row["ports"]["active_ratio"] is None and row["ports"]["rx_bps"] is None
    assert row["ports"]["counts"]["unknown"] == 4
    assert row["last_success_at"] is not None and row["traffic"] == []


def test_reject_fixture_invalid_references_and_unsourced_health(system):
    client, _, _, _ = system
    login(client); device = add_device(client); value = inventory()
    value["interfaces"][0]["admin_up"]["source"] = "fixture"
    assert client.put(f"/api/v1/devices/{device['id']}/inventory", json=value).status_code == 422
    value = inventory(); value["physical_ports"][0]["parent_port_id"] = "missing"
    assert client.put(f"/api/v1/devices/{device['id']}/inventory", json=value).status_code == 422
    assert client.post(f"/api/v1/devices/{device['id']}/observations", json=observation(health={"status": "ok"})).status_code == 422


def test_logout_expiry_and_websocket_origin(system):
    client, store, _, _ = system
    login(client)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/ssh-sessions/no-ticket/ws", headers={"origin": "https://evil.test"}):
            pass
    assert client.post("/api/v1/session/logout").status_code == 200
    assert client.get("/api/v1/session/me").status_code == 401
    login(client)
    with store.engine.begin() as conn:
        conn.execute(store.sessions.update().values(expires_at=time.time() - 1))
    assert client.get("/api/v1/session/me").status_code == 401


def test_host_key_trust_requires_matching_fingerprint_and_explicit_replacement(system):
    client, _, _, _ = system
    login(client); device = add_device(client); key = asyncssh.generate_private_key("ssh-ed25519")
    path = f"/api/v1/devices/{device['id']}/host-key"
    value = {"public_key": key.export_public_key().decode(), "fingerprint": key.get_fingerprint()}
    assert client.put(path, json={**value, "fingerprint": "SHA256:" + "x" * 43}).status_code == 422
    assert client.put(path, json=value).status_code == 200
    assert client.put(path, json=value).status_code == 409
    assert client.put(path, json={**value, "replace_existing": True}).status_code == 200
