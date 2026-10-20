"""Explicit isolated QA bootstrap. Synthetic data is confined to netstudio_qa DB."""
from datetime import timedelta
import os
import subprocess
from urllib.parse import urlparse

import httpx
import sqlalchemy as sa

from app.auth import hasher
from app.database import Store, now
from conftest import PASSWORD, inventory, observation


def main():
    url = os.environ["NETSTUDIO_TEST_DATABASE_URL"]
    parsed = urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.path != "/netstudio_qa":
        raise SystemExit("This script only supports a loopback netstudio_qa database.")
    origin = os.getenv("NETSTUDIO_TEST_ORIGIN", "http://127.0.0.1:13000")
    key_url = os.getenv("NETSTUDIO_TEST_SSH_KEY_URL", "http://127.0.0.1:12223")
    for endpoint in (origin, key_url):
        target = urlparse(endpoint)
        if target.scheme != "http" or target.hostname not in {"127.0.0.1", "localhost"} or target.username or target.password or target.path not in {"", "/"} or target.query or target.fragment:
            raise SystemExit("QA bootstrap endpoints must be plain loopback HTTP origins.")
    store = Store(url)
    if store.list_devices():
        raise SystemExit("QA database already contains inventory. No data overwritten.")
    with store.engine.begin() as conn:
        if conn.execute(sa.select(store.users.c.id).limit(1)).first():
            raise SystemExit("QA database already contains users. No account overwritten; use a new isolated project.")
        conn.execute(store.users.insert().values(id="qa-admin", username="qa-admin", password_hash=hasher.hash(PASSWORD), roles=["superadmin"], sites=["*"], enabled=True))
    container = os.getenv("NETSTUDIO_TEST_SSH_CONTAINER", "netstudio-redesign-qa-ssh-lab-1")
    docker_context = os.getenv("NETSTUDIO_TEST_DOCKER_CONTEXT") or subprocess.check_output(
        ["docker", "context", "show"], text=True
    ).strip()
    address = subprocess.check_output(["docker", "--context", docker_context, "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", container], text=True).strip()
    client = httpx.Client(base_url=origin, headers={"origin": origin}, timeout=30)
    response = client.post("/api/v1/session/login", json={"username": "qa-admin", "password": PASSWORD}); response.raise_for_status()
    client.headers["x-csrf-token"] = response.json()["csrf_token"]
    key = httpx.get(key_url).json()
    device_ids = []
    for n, name in enumerate(["QA-Core-01", "QA-Edge-02", "QA-Distribution-03"]):
        response = client.post("/api/v1/devices", json={"name": name, "model": ["QA-24RJ45-4SFP", "QA-6RJ45-4SFP", "QA-12RJ45-4QSFP"][n], "site": "TEST FIXTURE / isolated", "management_address": address if n == 0 else f"192.0.2.{20+n}", "ssh_port": 2222 if n == 0 else 22, "device_type": "switch" if n < 2 else "router", "credentials": {"username": "lab", "password": "lab-secret"} if n == 0 else None}); response.raise_for_status()
        identifier = response.json()["id"]
        device_ids.append(identifier)
        value = inventory(now() - timedelta(hours=2))
        unknown = value["interfaces"][0]["admin_up"]
        count = 28 if n == 0 else 10 if n == 1 else 16
        value["physical_ports"] = [{"id": f"p{i}", "component_id": "chassis", "label": str(i), "connector": "rj45" if i <= count-4 else "sfp" if n < 2 else "qsfp", "group": "Ethernet" if i <= count-4 else "Uplink", "ordinal": i} for i in range(1,count+1)]
        value["interfaces"] = [{"id": f"if{i}", "name": f"Ethernet1/{i}", "kind": "ethernet", "admin_up": unknown, "oper_up": unknown, "speed_mbps": unknown} for i in range(1,count+1)]
        value["bindings"] = [{"id": f"b{i}", "physical_port_id": f"p{i}", "interface_id": f"if{i}", "binding_quality": "explicit"} for i in range(1,count+1)]
        response = client.put(f"/api/v1/devices/{identifier}/inventory", json=value); response.raise_for_status()
        for step in range(45):
            at = now() - timedelta(minutes=45-step + (120 if n == 1 else 0))
            samples = [{"interface_id": f"if{i}", "admin_up": i < count-1, "oper_up": i < count-5, "rx_bps": (4 + step%9 + i%3) * 1_000_000 if i < 5 else 0, "tx_bps": (2 + step%6) * 1_000_000 if i < 5 else 0, "capacity_bps": 1e9, "duplex": "full", "addresses": [f"10.{n+10}.{i}.1/24"] if i in [1,2,25] else []} for i in range(1,count)]
            data = observation(at, interfaces=samples if n != 2 else [], reachability="unreachable" if n == 2 else "reachable", stale_after_seconds=900, health={"status":"warning" if n == 0 else "unknown", "evaluation":"QA fixture: fan warning" if n == 0 else None,"cpu_percent":23 if n == 0 else None,"memory_percent":41 if n == 0 else None,"temperature_c":53 if n == 0 else None,"uptime_seconds":804000 if n == 0 else None,"alerts":["QA fixture: fan warning"] if n == 0 else []}, neighbors=[{"id":"lab-peer", "interface_id":"if25","label":"QA upstream", "relation":"l2","evidence":"Isolated test fixture LLDP relation"}] if n == 0 else [])
            if n < 2:
                data["endpoints"] = {"status": "ok", "entries": [{"id": f"qa-endpoint-{i}", "interface_id": f"if{i}",
                    "mac": f"02:00:00:{n:02x}:00:{i:02x}", "addresses": [f"192.0.{n+2}.{100+i}"], "vlan": 10+n,
                    "discovery": "fdb", "state": "unknown", "evidence": "Isolated QA fixture: same VLAN FDB / ARP correlation"} for i in range(1, 4)]}
            if n == 1:
                data["neighbors"] = [{"id": "qa-core-neighbor", "interface_id": "if8", "label": "QA-Core-01", "relation": "l2",
                    "evidence": "Isolated QA fixture: explicit LLDP inventory identity", "remote_device_id": device_ids[0], "remote_interface_id": "if28"}]
            response = client.post(f"/api/v1/devices/{identifier}/observations", json=data); response.raise_for_status()
        if n == 0:
            response = client.put(f"/api/v1/devices/{identifier}/host-key", json=key); response.raise_for_status()
    client.post("/api/v1/session/logout").raise_for_status()
    print("Isolated QA inventory populated through authenticated APIs: 3 devices / 135 observations.")


if __name__ == "__main__": main()
