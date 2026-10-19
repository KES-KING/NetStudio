"""Sanitized VRP 5.120 shapes and real local SSH, never customer devices."""
import asyncio
from concurrent.futures import Future
from threading import Thread
import time

import asyncssh
import pytest
import sqlalchemy as sa

from app.huawei import COMMANDS, VRPReader, connector_kind, merge_snapshot, parse_snapshot
from app.ssh import ConnectionPolicyError, algorithm_options, target_allowed
from app.telemetry import normalize, topology
from conftest import ORIGIN, add_device, inventory, login
from test_ssh import until


VERSION = """Huawei Versatile Routing Platform Software
VRP (R) software, Version 5.120 (S5700 V200R002C00SPC100)
Quidway S5700S-28P-LI-AC Routing Switch uptime is 0 week, 0 day, 0 hour, 19 minutes
LS52T28S 0(Master) : uptime is 0 week, 0 day, 0 hour, 18 minutes
"""
INTERFACE = """GigabitEthernet0/0/1 current state : DOWN
Line protocol current state : DOWN
Description:
Switch Port, PVID :    1, TPID : 8100(Hex), The Maximum Frame Length is 9216
IP Sending Frames' Format is PKTFMT_ETHNT_2, Hardware address is 0200-0000-0001
Port Mode: COMMON COPPER
Speed : 1000,  Loopback: NONE
Duplex: FULL,  Negotiation: ENABLE
Last 300 seconds input rate 0 bits/sec, 0 packets/sec
Last 300 seconds output rate 0 bits/sec, 0 packets/sec
Input:  0 packets, 0 bytes
  Discard: 0, Pause: 0
  Total Error: 0
Output:  0 packets, 0 bytes
  Discard: 0, Pause: 0
  Total Error: 0
"""
OUTPUTS = {
    "display version": VERSION,
    "display interface": INTERFACE + INTERFACE.replace("0/0/1", "0/0/2").replace("DOWN", "UP").replace("COMMON COPPER", "COMMON FIBER") + "Vlanif1 current state : UP\nLine protocol current state : UP\n",
    "display ip interface brief": "Interface IP Address/Mask Physical Protocol\nVlanif1 192.0.2.1/24 up up\n",
    "display mac-address": "MAC Address VLAN/VSI Learned-From Type\n0200-0000-0010 1/- GE0/0/1 dynamic\n0200-0000-0011 20/- GE0/0/2 static\nTotal items displayed = 2\n",
    "display arp all": "IP ADDRESS MAC ADDRESS EXPIRE(M) TYPE INTERFACE VPN-INSTANCE\n192.0.2.1 0200-0000-0001 I - Vlanif1\n192.0.2.10 0200-0000-0010 10 D-0 Vlanif1\n192.0.2.11 0200-0000-0011 10 D-0 Vlanif1\n192.0.2.99 0200-0000-0010 10 D-0 Vlanif1 blue\n",
    "display cpu-usage": "CPU Usage : 12% Max: 55%\n",
    "display memory-usage": "Memory Using Percentage Is: 33%\n",
}


def snapshot(system, outputs=None):
    client, store, _, _ = system
    login(client)
    device = store.get_device(add_device(client, collector="huawei_vrp")["id"])
    return merge_snapshot(device, parse_snapshot(device, outputs or OUTPUTS))


def test_vrp5120_real_format_ports_and_directional_metrics(system):
    device, batch = snapshot(system)
    assert device.os_version == "5.120 (S5700 V200R002C00SPC100)"
    assert len(device.physical_ports) == 2  # Never manufacture the model's 28 ports.
    assert [p.connector for p in device.physical_ports] == ["rj45", "sfp"]
    assert not any(p.verified_layout for p in device.physical_ports)
    assert device.physical_ports[0].label == "1" and device.physical_ports[0].group == "GigabitEthernet0/0"
    port = batch.interfaces[0]
    assert port.admin_up is True and port.oper_up is False
    assert port.capacity_bps == 1e9 and port.duplex == "full"
    assert port.rx_bps == port.tx_bps == port.in_octets == port.errors == port.tx_errors == 0
    assert port.pvid == 1 and port.access_vlan is None and port.vlan_mode == "unknown"
    assert port.rate_interval_seconds == 300
    assert batch.health.uptime_seconds == 1140 and batch.health.status == "unknown"
    assert batch.health.cpu_percent == 12 and batch.health.memory_percent == 33
    assert batch.interfaces[-1].addresses == ["192.0.2.1/24"]
    assert batch.interfaces[-1].vrf_known is False
    assert batch.interfaces[-1].rx_bps is None
    assert batch.neighbors == []  # FDB and ARP are not LLDP or cables.
    endpoints = batch.endpoints.entries
    assert batch.endpoints.status == "ok"
    first = next(e for e in endpoints if e.discovery == "fdb" and e.vlan == 1)
    assert first.addresses == ["192.0.2.10"]  # Excludes blue VRF.
    assert next(e for e in endpoints if e.discovery == "fdb" and e.vlan == 20).addresses == []
    assert not any(e.mac == "02:00:00:00:00:01" for e in endpoints)
    updated, second = merge_snapshot(device, parse_snapshot(device, OUTPUTS))
    assert [i.id for i in updated.interfaces] == [i.id for i in device.interfaces]
    assert [p.id for p in updated.physical_ports] == [p.id for p in device.physical_ports]


@pytest.mark.parametrize(
    "name,text,expected",
    [
        ("GE0/0/25", "Port Mode: COMMON FIBER\nSpeed : 1000", "sfp"),
        ("XGigabitEthernet0/0/1", "Port Mode: FORCE FIBER\nSpeed : 10000", "sfp"),
        ("25GE0/0/1", "Port Mode: COMMON FIBER\nSpeed : 25000", "sfp"),
        ("40GE0/0/1", "Port Mode: COMMON FIBER\nSpeed : 40000", "unknown"),
        ("40GE0/0/1", "Port Mode: COMMON FIBER\nTransceiver Type: 40GBASE-SR4-QSFP+", "qsfp"),
        ("100GE0/0/1", "Port Mode: COMMON FIBER\nTransceiver Type: 100GBASE-LR4-QSFP28", "qsfp"),
        ("GigabitEthernet0/0/1", "Port Mode: FORCE COPPER\nTransceiver Type: 1000_BASE_T_SFP", "rj45"),
        ("Ethernet0/0/1", "Port Mode: COMMON FIBER\nSpeed : 100", "unknown"),
    ],
)
def test_connector_classification_uses_medium_and_interface_evidence(name, text, expected):
    assert connector_kind(name, text) == expected


def test_s5700_style_inventory_keeps_all_four_optical_uplinks_as_sfp(system):
    interfaces = []
    for number in range(1, 29):
        entry = INTERFACE.replace("0/0/1", f"0/0/{number}")
        if number >= 25:
            entry = entry.replace("COMMON COPPER", "COMMON FIBER")
        interfaces.append(entry)
    device, _ = snapshot(system, {**OUTPUTS, "display interface": "".join(interfaces)})
    assert len(device.physical_ports) == 28
    assert [port.connector for port in device.physical_ports[:24]] == ["rj45"] * 24
    assert [(port.label, port.connector) for port in device.physical_ports[24:]] == [
        ("25", "sfp"), ("26", "sfp"), ("27", "sfp"), ("28", "sfp"),
    ]


def test_unrecognized_arp_is_partial_and_unknown_vrf_does_not_merge_subnets(system):
    device, batch = snapshot(system, {**OUTPUTS, "display arp all": OUTPUTS["display arp all"] + "192.0.2.55 unsupported row\n"})
    assert batch.endpoints.status == "partial"
    for sample in batch.interfaces[:2]:
        sample.addresses = ["198.51.100.1/24"]
        sample.vrf_known = False
    nodes = topology(device, batch.model_dump(mode="json"))["nodes"]
    subnets = [n for n in nodes if n["kind"] == "subnet" and n["name"] == "198.51.100.0/24"]
    assert len(subnets) == 2 and all("VRF bilinmiyor" in n["detail"] for n in subnets)


def test_unknown_optional_data_disabled_port_no_guess_or_counter_fallback(system):
    outputs = {"display version": VERSION, "display interface": INTERFACE.replace("state : DOWN", "state : Administratively DOWN").replace("Last 300 seconds", "Unknown period")}
    device, batch = snapshot(system, outputs)
    assert batch.interfaces[0].admin_up is False and batch.interfaces[0].oper_up is False
    assert batch.interfaces[0].rx_bps is None
    assert normalize(batch, batch.model_dump(mode="json"))["interfaces"][0]["rate_reason"] == "counter_epoch_unknown"
    assert batch.health.cpu_percent is None and batch.health.memory_percent is None
    assert batch.endpoints.status == "error"
    value = parse_snapshot(device, outputs, {c: "collector_command_unsupported" for c in COMMANDS[2:]})
    _, batch = merge_snapshot(device, value)
    assert batch.endpoints.status == "unsupported" and batch.health.alerts


def test_preserve_manual_inventory_ids_geometry_and_timestamp(system):
    client, store, _, _ = system
    login(client)
    device = add_device(client, collector="huawei_vrp")
    manual = inventory()
    manual["interfaces"][0]["name"] = "GE0/0/1"
    assert client.put(f"/api/v1/devices/{device['id']}/inventory", json=manual).status_code == 200
    device = store.get_device(device["id"])
    result, batch = merge_snapshot(device, parse_snapshot(device, OUTPUTS))
    assert result.physical_ports == device.physical_ports and result.components == device.components
    assert result.inventory_source == "manual" and result.inventory_observed_at == device.inventory_observed_at
    assert result.interfaces[0].id == "if1" and result.bindings[0].id == "b1"


@pytest.mark.parametrize("command,output,code", [("display version", "Linux 6.1", "collector_not_huawei_vrp"), ("display interface", "unknown format", "collector_parse_failed")])
def test_required_output_fails_closed(system, command, output, code):
    with pytest.raises(ConnectionPolicyError, match=code):
        snapshot(system, {**OUTPUTS, command: output})


def test_registered_target_approval_optional_network_ceiling_and_bound_identity(system, monkeypatch):
    client, store, _, _ = system
    login(client)
    device = store.get_device(add_device(client, management_address="192.0.2.17")["id"])
    monkeypatch.setenv("STOCC_SSH_ALLOWED_CIDRS", "")
    target_allowed(store, device)
    assert client.post(f"/api/v1/devices/{device.id}/ssh-sessions").json()["detail"]["code"] == "host_key_required"
    for changed in ({"id": "not-registered"}, {"management_address": "192.0.2.18"}, {"ssh_port": 23}, {"ssh_profile": "huawei_legacy"}):
        with pytest.raises(ConnectionPolicyError, match="device_connection_changed"):
            target_allowed(store, device.model_copy(update=changed))
    monkeypatch.setenv("STOCC_SSH_ALLOWED_CIDRS", "198.51.100.0/24")
    with pytest.raises(ConnectionPolicyError, match="target_network_denied"):
        target_allowed(store, device)
    monkeypatch.setenv("STOCC_SSH_ALLOWED_CIDRS", "not-a-cidr")
    with pytest.raises(ConnectionPolicyError, match="invalid_target_network_policy"):
        target_allowed(store, device)
    monkeypatch.setenv("STOCC_SSH_ALLOWED_CIDRS", "")
    mapped = store.get_device(add_device(client, management_address="::ffff:127.0.0.1")["id"])
    with pytest.raises(ConnectionPolicyError, match="target_network_denied"):
        target_allowed(store, mapped)
    for ip in ["169.254.169.254", "::ffff:169.254.169.254", "224.0.0.1", "0.0.0.0", "fe80::1%eth0"]:
        assert client.post("/api/v1/devices", json={"name": "invalid", "site": "lab", "management_address": ip}).status_code == 422


def test_profile_settings_explicit_consent_rbac_and_audit(system):
    client, store, _, _ = system
    login(client)
    device = add_device(client)
    path = f"/api/v1/devices/{device['id']}/connection-settings"
    settings = {"collector": "huawei_vrp", "ssh_profile": "huawei_legacy"}
    assert client.put(path, json=settings).json()["detail"]["code"] == "legacy_ssh_confirmation_required"
    for username in ("viewer", "outsider"):
        login(client, username)
        assert client.put(path, json={**settings, "legacy_ssh_confirmed": True}).status_code == 404
    login(client, "operator")
    assert client.put(path, json={**settings, "legacy_ssh_confirmed": True}).status_code == 200
    assert client.get(path.replace("/connection-settings", "")).json()["ssh_profile"] == "huawei_legacy"
    assert "legacy_ssh_confirmed" not in client.get(path.replace("/connection-settings", "")).json()
    assert client.put(path, json={**settings, "management_address": "192.0.2.99"}).status_code == 422
    with store.engine.connect() as conn:
        audit = conn.execute(sa.select(store.audit.c.details).where(store.audit.c.event == "device.connection.updated")).scalar_one()
    assert audit["after"] == settings and audit["legacy_ssh_confirmed"] is True
    assert client.post("/api/v1/devices", json={"name": "legacy", "site": "lab", "management_address": "192.0.2.99", **settings}).status_code == 422
    assert algorithm_options(store.get_device(device["id"])).get("encryption_algs") == "+aes128-cbc"


@pytest.fixture(params=["diffie-hellman-group1-sha1", "diffie-hellman-group-exchange-sha1"])
def vrp_server(request):
    loop, ready = asyncio.new_event_loop(), Future()
    key = asyncssh.generate_private_key("ssh-rsa")
    state = {"outputs": dict(OUTPUTS), "commands": [], "pages": 0}
    class Server(asyncssh.SSHServer):
        def begin_auth(self, username): return True
        def password_auth_supported(self): return True
        def validate_password(self, username, password): return username == "lab" and password == "lab-secret"
    async def terminal(process):
        process.stdout.write("\r\n<QA-VRP>")
        try:
            while line := await process.stdin.readline():
                command = line.strip()
                state["commands"].append(command)
                output = state["outputs"].get(command, "Error: Unrecognized command found at '^' position.\n")
                if command == "display interface":
                    process.stdout.write(command + "\r\n" + output[:len(output)//2] + "\x1b[7m  ---- More ----\x1b[0m")
                    assert await process.stdin.read(1) == " "
                    state["pages"] += 1
                    process.stdout.write("\b" * 16 + output[len(output)//2:] + "\r\n<QA-VRP>")
                else:
                    process.stdout.write(command + "\r\n" + output + "\r\n<QA-VRP>")
        finally:
            process.exit(0)
    async def start():
        return await asyncssh.create_server(Server, "127.0.0.1", 0, server_host_keys=[key], process_factory=terminal,
            kex_algs=[request.param], encryption_algs=["aes128-cbc"], signature_algs=["ssh-rsa"], line_editor=False)
    def run():
        asyncio.set_event_loop(loop)
        try:
            server = loop.run_until_complete(start())
        except Exception as error:
            ready.set_exception(error)
            return
        ready.set_result(server)
        loop.run_forever()
        pending = asyncio.all_tasks(loop)
        for task in pending: task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
    thread = Thread(target=run, daemon=True)
    thread.start()
    server = ready.result(timeout=10)
    yield server.get_port(), key, state
    async def shutdown():
        server.close()
        await server.wait_closed()
    asyncio.run_coroutine_threadsafe(shutdown(), loop).result(timeout=10)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=10)


def wait_job(client, device, kind="polls"):
    response = client.post(f"/api/v1/devices/{device['id']}/{kind}")
    assert response.status_code == 202, response.text
    for _ in range(300):
        job = client.get(f"/api/v1/jobs/{response.json()['id']}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(.02)
    pytest.fail("Job did not complete")


def test_real_legacy_ssh_pagination_collection_trust_and_settings_revocation(system, vrp_server):
    client, store, app, _ = system
    login(client)
    port, key, state = vrp_server
    device = add_device(client, collector="huawei_vrp", ssh_port=port, credentials={"username": "lab", "password": "lab-secret"})
    base = f"/api/v1/devices/{device['id']}"
    assert client.put(base + "/host-key", json={"public_key": key.export_public_key().decode(), "fingerprint": key.get_fingerprint()}).status_code == 200
    job = wait_job(client, device)
    # Either peer can close first on a KEX mismatch; no fallback may occur.
    assert job["status"] == "failed" and job["error_code"] in {"ssh_algorithms_incompatible", "connection_failed"}, job
    assert state["commands"] == []
    settings = {"collector": "huawei_vrp", "ssh_profile": "huawei_legacy", "legacy_ssh_confirmed": True}
    assert client.put(base + "/connection-settings", json=settings).status_code == 200
    assert wait_job(client, device, "connection-tests")["status"] == "succeeded"
    job = wait_job(client, device)
    assert job["status"] == "succeeded", job
    assert state["commands"] == list(COMMANDS) and state["pages"] == 1
    row = client.get("/api/v1/overview").json()["devices"][0]
    assert row["ports"]["total"] == 2 and row["ports"]["counts"]["up"] == 1
    assert row["telemetry"]["health"]["uptime_seconds"] == 1140
    assert row["ports"]["rx_bps"] == 0
    prior = client.get(base).json()
    state["outputs"]["display interface"] = "Unparseable inventory\n"
    assert wait_job(client, device)["error_code"] == "collector_parse_failed"
    assert client.get(base).json() == prior  # A failed read cannot clear the ports.
    ticket = client.post(base + "/ssh-sessions").json()
    with client.websocket_connect(ticket["websocket_path"], headers={"origin": ORIGIN}) as ws:
        until(ws, lambda m: m.get("status") == "connected")
        assert client.put(base + "/connection-settings", json={"collector": "huawei_vrp", "ssh_profile": "standard"}).status_code == 200
        until(ws, lambda m: m.get("status") == "session_revoked")
    assert client.put(base + "/connection-settings", json=settings).status_code == 200
    wrong = asyncssh.generate_private_key("ssh-rsa")
    assert client.put(base + "/host-key", json={"public_key": wrong.export_public_key().decode(), "fingerprint": wrong.get_fingerprint(), "replace_existing": True}).status_code == 200
    assert wait_job(client, device, "connection-tests")["error_code"] == "host_key_changed"


def test_reader_fixed_commands_disconnect_and_size_limit(monkeypatch):
    class Stream:
        async def read(self, _): return "x" * 100
    class Process:
        stdout = Stream()
    monkeypatch.setattr("app.huawei.MAX_OUTPUT", 50)
    with pytest.raises(ConnectionPolicyError, match="collector_output_limit"):
        asyncio.run(VRPReader(Process()).read_prompt())
    with pytest.raises(ConnectionPolicyError, match="collector_command_denied"):
        asyncio.run(VRPReader(Process()).command("system-view"))
    class EOF:
        async def read(self, _): return ""
    Process.stdout = EOF()
    with pytest.raises(ConnectionPolicyError, match="collector_disconnected"):
        asyncio.run(VRPReader(Process()).read_prompt())


def test_reader_bounds_timeout_and_does_not_execute_a_second_command(monkeypatch):
    commands = []
    class Stream:
        def write(self, value): commands.append(value)
        async def drain(self): pass
        async def read(self, _):
            await asyncio.sleep(1)
            return ""
    class Process:
        stdin = Stream()
        stdout = Stream()
    monkeypatch.setattr("app.huawei.COMMAND_TIMEOUT", .01)
    with pytest.raises(TimeoutError):
        asyncio.run(VRPReader(Process()).command("display interface"))
    assert commands == ["display interface\n"]
