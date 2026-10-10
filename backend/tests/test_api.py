from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_and_device_contract():
    assert client.get("/healthz").json()["status"] == "ok"
    response = client.get("/api/v1/devices")
    assert response.status_code == 200
    device = response.json()[0]
    assert len(device["physical_ports"]) == 28
    assert device["read_only"] is True
    assert device["interfaces"][0]["admin_up"]["source"] == "fixture"
    assert device["interfaces"][0]["oper_up"]["observed_at"] is not None


def test_connection_test_is_a_job_and_demo_never_reaches_network():
    response = client.post("/api/v1/devices/dev-demo-01/connection-tests", headers={"X-Stocc-User": "tester"})
    assert response.status_code == 202
    job = response.json()
    assert job["kind"] == "connection_test"
    assert job["status"] == "succeeded"
    assert job["started_at"] is not None
    assert job["finished_at"] is not None
    assert job["result"]["reachable"] is False
    assert "gerçek ağ bağlantısı açmaz" in job["result"]["message"]
    assert job["result_code"] == "fixture_unreachable"


def test_session_is_site_scoped_and_required_for_jobs():
    response = client.get("/api/v1/session/me", headers={"X-Stocc-User": "operator-1"})
    assert response.status_code == 200
    assert response.json()["site_ids"] == ["LAB / Demo"]
    unauthenticated = client.post("/api/v1/devices/dev-demo-01/connection-tests")
    assert unauthenticated.status_code == 401


def test_poll_job_returns_observation_snapshot_without_network_access():
    response = client.post("/api/v1/devices/dev-demo-01/polls", headers={"X-Stocc-User": "operator-1"})
    assert response.status_code == 202
    job = response.json()
    assert job["kind"] == "inventory_read"
    assert job["result_code"] == "fixture_snapshot"
    assert len(job["result"]["snapshot"]["observations"]) == 28


def test_latest_observations_contract_excludes_logical_interfaces():
    response = client.get("/api/v1/devices/dev-demo-01/observations/latest", headers={"X-Stocc-User": "operator-1"})
    assert response.status_code == 200
    names = {item["interface_name"] for item in response.json()["observations"]}
    assert "Vlan10" not in names
    assert "GigabitEthernet0/1" in names


def test_unknown_device_has_structured_error():
    response = client.get("/api/v1/devices/not-here")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "device_not_found"
