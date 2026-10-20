"""Real SSH transport against an ephemeral test server, never a physical device."""
import asyncio
from concurrent.futures import Future
import json
import time
from threading import Thread

import asyncssh
import pytest
import sqlalchemy as sa
from starlette.websockets import WebSocketDisconnect
from app.telemetry import timestamp

from conftest import ORIGIN, add_device, inventory, login


@pytest.fixture
def ssh_server():
    loop = asyncio.new_event_loop()
    key = asyncssh.generate_private_key("ssh-ed25519")
    ready = Future()
    counters = {"rx":1000}
    class Server(asyncssh.SSHServer):
        def begin_auth(self, username): return True
        def password_auth_supported(self): return True
        def validate_password(self, username, password): return username == "lab" and password == "lab-secret"
        def public_key_auth_supported(self): return True
        def validate_public_key(self, username, public_key): return username == "lab" and public_key == key.convert_to_public()

    async def terminal(process):
        if process.command:
            counters["rx"] += 100
            outputs = {
                "ip -j -s link show": json.dumps([{"ifindex":1,"ifname":"eth1","link_type":"ether","flags":["UP"],"operstate":"UP","stats64":{"rx":{"bytes":counters["rx"]},"tx":{"bytes":counters["rx"]*2}}}]),
                "ip -j address show": json.dumps([{"ifindex":1,"addr_info":[{"local":"192.0.2.1","prefixlen":24}]}]),
                "cat /proc/uptime": "120.0 240.0\n",
                "cat /proc/sys/kernel/random/boot_id": "test-boot-id\n",
            }
            process.stdout.write(outputs.get(process.command, ""))
            process.exit(0 if process.command in outputs else 1)
            return
        process.stdout.write("LAB SSH READY\n")
        try:
            while True:
                try:
                    line = await process.stdin.readline()
                    if not line: break
                    process.stdout.write(f"LAB REPLY: {line}")
                except asyncssh.TerminalSizeChanged as error:
                    process.stdout.write(f"SIZE:{error.width}x{error.height}\n")
        except (asyncssh.BreakReceived, asyncssh.SignalReceived, asyncssh.ConnectionLost):
            pass
        finally:
            process.exit(0)

    async def start():
        return await asyncssh.create_server(Server, "127.0.0.1", 0, server_host_keys=[key], process_factory=terminal)
    def run():
        asyncio.set_event_loop(loop)
        server = loop.run_until_complete(start())
        ready.set_result(server)
        loop.run_forever()
        pending = asyncio.all_tasks(loop)
        for task in pending: task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
    thread = Thread(target=run, daemon=True); thread.start()
    server = ready.result(timeout=10)
    yield server.get_port(), key
    async def shutdown():
        server.close(); await server.wait_closed()
    asyncio.run_coroutine_threadsafe(shutdown(), loop).result(timeout=10)
    loop.call_soon_threadsafe(loop.stop); thread.join(timeout=10)


def create_terminal(client, server, *, password="lab-secret", key_override=None, private=False, collector="external"):
    port, key = server
    credentials = {"username": "lab", "password": password}
    if private:
        credentials = {"username": "lab", "method": "private_key", "private_key": key.export_private_key(passphrase="phrase-test").decode(), "passphrase": "phrase-test"}
    device = add_device(client, ssh_port=port, credentials=credentials, collector=collector)
    trusted = key_override or key
    response = client.put(f"/api/v1/devices/{device['id']}/host-key", json={"public_key": trusted.export_public_key().decode(), "fingerprint": trusted.get_fingerprint()})
    assert response.status_code == 200, response.text
    ticket = client.post(f"/api/v1/devices/{device['id']}/ssh-sessions")
    assert ticket.status_code == 201, ticket.text
    return device, ticket.json()


def until(ws, match, count=15):
    seen = []
    for _ in range(count):
        message = ws.receive_json(); seen.append(message)
        if match(message): return message
    pytest.fail(f"Expected terminal event missing: {seen}")


def test_real_ssh_input_pty_resize_duplicate_and_logout(system, ssh_server):
    client, store, app, _ = system
    login(client); device, ticket = create_terminal(client, ssh_server)
    assert client.post(f"/api/v1/devices/{device['id']}/ssh-sessions").status_code == 409
    with client.websocket_connect(ticket["websocket_path"], headers={"origin": ORIGIN}) as ws:
        until(ws, lambda m: m.get("status") == "connected")
        ws.send_json({"type": "input", "data": "hello-test\n"})
        until(ws, lambda m: "LAB REPLY: hello-test" in m.get("data", ""))
        ws.send_json({"type": "resize", "cols": 100, "rows": 32})
        until(ws, lambda m: "SIZE:100x32" in m.get("data", ""))
        assert client.post("/api/v1/session/logout").status_code == 200
        until(ws, lambda m: m.get("status") == "session_revoked")
    assert ticket["id"] not in app.state.ssh.sessions
    with store.engine.connect() as conn:
        events = conn.execute(sa.select(store.audit)).mappings().all()
    serialized = json.dumps([dict(e) for e in events], default=str)
    assert "ssh.started" in serialized and "ssh.ended" in serialized
    assert "hello-test" not in serialized and "lab-secret" not in serialized


@pytest.mark.parametrize("mode,code", [("password", "authentication_failed"), ("host", "host_key_changed")])
def test_real_ssh_denies_bad_credentials_and_changed_host_key(system, ssh_server, mode, code):
    client, _, _, _ = system
    login(client)
    _, ticket = create_terminal(client, ssh_server, password="incorrect" if mode == "password" else "lab-secret", key_override=asyncssh.generate_private_key("ssh-ed25519") if mode == "host" else None)
    with client.websocket_connect(ticket["websocket_path"], headers={"origin": ORIGIN}) as ws:
        result = until(ws, lambda m: m.get("status") not in {None, "connecting"})
        assert result["status"] == code


def test_private_key_and_message_limits(system, ssh_server):
    client, _, _, _ = system
    login(client); _, ticket = create_terminal(client, ssh_server, private=True)
    with client.websocket_connect(ticket["websocket_path"], headers={"origin": ORIGIN}) as ws:
        until(ws, lambda m: m.get("status") == "connected")
        ws.send_json({"type": "input", "data": "x" * 17000})
        until(ws, lambda m: m.get("status") == "message_too_large")


def test_ticket_requires_original_session_and_origin(system, ssh_server):
    client, _, _, _ = system
    login(client); _, ticket = create_terminal(client, ssh_server)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(ticket["websocket_path"], headers={"origin": "https://evil.test"}): pass
    login(client, "operator")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(ticket["websocket_path"], headers={"origin": ORIGIN}): pass


def test_idle_timeout_and_role_revocation(system, ssh_server):
    client, store, app, _ = system
    login(client); _, ticket = create_terminal(client, ssh_server)
    app.state.ssh.idle_seconds = 0
    with client.websocket_connect(ticket["websocket_path"], headers={"origin": ORIGIN}) as ws:
        until(ws, lambda m: m.get("status") == "connected")
        until(ws, lambda m: m.get("status") == "idle_timeout")
    app.state.ssh.idle_seconds = 300
    _, ticket = create_terminal(client, ssh_server)
    with client.websocket_connect(ticket["websocket_path"], headers={"origin": ORIGIN}) as ws:
        until(ws, lambda m: m.get("status") == "connected")
        with store.engine.begin() as conn:
            conn.execute(store.users.update().where(store.users.c.id == "admin").values(roles=["viewer"]))
        until(ws, lambda m: m.get("status") == "session_revoked")


def test_target_allowlist_concurrency_and_ticket_expiry(system, ssh_server, monkeypatch):
    client, _, app, _ = system
    login(client)
    device, ticket = create_terminal(client, ssh_server)
    app.state.ssh.sessions[ticket["id"]].created -= 31
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(ticket["websocket_path"], headers={"origin": ORIGIN}): pass
    app.state.ssh.expire_pending()
    assert ticket["id"] not in app.state.ssh.sessions
    monkeypatch.setenv("STOCC_SSH_ALLOWED_CIDRS", "")
    assert client.post(f"/api/v1/devices/{device['id']}/ssh-sessions").json()["detail"]["code"] == "target_network_denied"
    monkeypatch.setenv("STOCC_SSH_ALLOWED_CIDRS", "127.0.0.1/32")
    for _ in range(3): create_terminal(client, ssh_server)
    assert client.post(f"/api/v1/devices/{device['id']}/ssh-sessions").status_code == 429


def test_real_ssh_jobs_and_linux_collector_preserve_hardware_provenance(system, ssh_server):
    client, _, _, _ = system
    login(client); device, ticket = create_terminal(client, ssh_server, collector="linux_ssh")
    client.delete(f"/api/v1/ssh-sessions/{ticket['id']}")
    hardware = inventory()
    assert client.put(f"/api/v1/devices/{device['id']}/inventory", json=hardware).status_code == 200
    def run(kind):
        response = client.post(f"/api/v1/devices/{device['id']}/{kind}")
        assert response.status_code == 202
        identifier = response.json()["id"]
        for _ in range(100):
            job = client.get(f"/api/v1/jobs/{identifier}").json()
            if job["status"] not in {"queued", "running"}: break
            time.sleep(.02)
        assert job["status"] == ("succeeded" if kind == "connection-tests" else "partial"), job
        if kind == "polls":
            assert job["result"]["groups"]["fast"]["quality"] == "ok"
            assert job["result"]["groups"]["network"]["diagnostics"]["endpoints"] == "parse_error"
        return job
    assert run("connection-tests")["result"]["reachable"] is True
    run("polls"); run("polls")
    row = client.get("/api/v1/overview").json()["devices"][0]
    assert row["device"]["inventory_source"] == "manual"
    assert timestamp(row["device"]["inventory_observed_at"]) == timestamp(hardware["observed_at"])
    assert row["telemetry"]["source"] == "ssh"
    assert row["telemetry"]["health"]["uptime_seconds"] == 120
    assert row["ports"]["total"] == 4 and row["ports"]["counts"]["up"] == 1
    assert row["ports"]["rx_bps"] > 0
    login(client, "outsider")
    assert client.get("/api/v1/jobs").json() == []
