import base64
import json
import os
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.auth import hasher
from app.database import Store, now

ORIGIN = "http://testserver"
PASSWORD = "test-only-password-1234"


@pytest.fixture
def system(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCC_ENV", "development")
    monkeypatch.setenv("STOCC_ALLOWED_ORIGINS", ORIGIN)
    monkeypatch.setenv("STOCC_SSH_ALLOWED_CIDRS", "127.0.0.1/32")
    store = Store(f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
    store.meta.create_all(store.engine)
    key_file = tmp_path / "keyring.json"
    key_file.write_text(json.dumps({"active": "test-v1", "keys": {"test-v1": base64.b64encode(os.urandom(32)).decode()}}))
    with store.engine.begin() as conn:
        for name, role, site in [("admin", "admin", "*"), ("viewer", "viewer", "lab"), ("operator", "operator", "lab"), ("outsider", "operator", "other")]:
            conn.execute(store.users.insert().values(id=name, username=name, password_hash=hasher.hash(PASSWORD), roles=[role], sites=[site], enabled=True))
    app = create_app(store, str(key_file))
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, store, app, key_file
    store.engine.dispose()


def login(client, username="admin"):
    result = client.post("/api/v1/session/login", json={"username": username, "password": PASSWORD}, headers={"origin": ORIGIN})
    assert result.status_code == 200, result.text
    client.headers.update({"origin": ORIGIN, "x-csrf-token": result.json()["csrf_token"]})
    return result.json()


def add_device(client, **changes):
    value = {"name": "Test switch", "management_address": "127.0.0.1", "site": "lab", **changes}
    response = client.post("/api/v1/devices", json=value)
    assert response.status_code == 201, response.text
    return response.json()


def inventory(at=None):
    at = at or now() - timedelta(seconds=60)
    unknown = {"value": None, "observed_at": at.isoformat(), "stale_after_seconds": 120, "source": "manual", "quality": "unknown"}
    return {"source": "manual", "observed_at": at.isoformat(), "components": [{"id": "chassis", "kind": "chassis", "label": "Test chassis"}],
        "physical_ports": [{"id": f"p{i}", "component_id": "chassis", "label": str(i), "connector": "qsfp" if i == 4 else "sfp" if i == 3 else "rj45", "group": "Test", "ordinal": i} for i in range(1, 5)],
        "interfaces": [{"id": f"if{i}", "name": f"eth{i}" if i < 5 else "Vlan10", "kind": "ethernet" if i < 5 else "svi", "admin_up": unknown, "oper_up": unknown, "speed_mbps": unknown} for i in range(1, 6)],
        "bindings": [{"id": f"b{i}", "physical_port_id": f"p{i}", "interface_id": f"if{i}", "binding_quality": "explicit"} for i in range(1, 5)]}


def observation(at=None, **changes):
    return {"observed_at": (at or now()).isoformat(), "source": "manual", "reachability": "reachable", "interfaces": [
        {"interface_id": "if1", "admin_up": True, "oper_up": True, "rx_bps": 800, "tx_bps": 1600, "capacity_bps": 10000, "addresses": ["192.0.2.1/24"]},
        {"interface_id": "if2", "admin_up": True, "oper_up": False}, {"interface_id": "if3", "admin_up": False, "oper_up": False},
        {"interface_id": "if5", "admin_up": True, "oper_up": True, "rx_bps": 999999, "addresses": ["198.51.100.1/24"]}], **changes}


def prepare(client, **changes):
    device = add_device(client, **changes)
    response = client.put(f"/api/v1/devices/{device['id']}/inventory", json=inventory())
    assert response.status_code == 200, response.text
    return device
