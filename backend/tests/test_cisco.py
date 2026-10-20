"""Sanitized Catalyst 2960-X IOS shapes; never customer CLI output."""
import asyncio
from concurrent.futures import Future
from threading import Thread
import time

import asyncssh
import pytest

from app.cisco import COMMANDS, IOSReader, connector_kind, merge_snapshot, parse_snapshot
from app.ssh import ConnectionPolicyError
from conftest import add_device, inventory, login


VERSION = """Cisco IOS Software, C2960X Software (C2960X-UNIVERSALK9-M), Version 15.2(7)E10, RELEASE SOFTWARE (fc3)
Technical Support: http://www.cisco.com/techsupport
Copyright (c) 1986-2024 by Cisco Systems, Inc.
qa-switch uptime is 1 week, 2 days, 3 hours, 4 minutes
System returned to ROM by power-on
cisco WS-C2960X-48FPD-L (APM86XXX) processor (revision U0) with 524288K bytes of memory.
System serial number            : FOC0000TEST
Model number                    : WS-C2960X-48FPD-L
"""


INTERFACES = """GigabitEthernet1/0/1 is up, line protocol is up (connected)
  Hardware is Gigabit Ethernet, address is 0200.0000.0001
  Description: office-ap
  MTU 1500 bytes, BW 1000000 Kbit/sec
  Full-duplex, 1000Mb/s, media type is 10/100/1000BaseTX
  5 minute input rate 8000 bits/sec, 10 packets/sec
  5 minute output rate 16000 bits/sec, 20 packets/sec
     10 packets input, 1000 bytes, 0 no buffer
     0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored
     20 packets output, 2000 bytes, 0 underruns
     0 output errors, 0 collisions, 0 interface resets
  Total output drops: 0
GigabitEthernet1/0/2 is administratively down, line protocol is down (disabled)
  Hardware is Gigabit Ethernet, address is 0200.0000.0002
  Auto-duplex, Auto-speed, media type is 10/100/1000BaseTX
     0 packets input, 0 bytes, 0 no buffer
     0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored
     0 packets output, 0 bytes, 0 underruns
     0 output errors, 0 collisions, 0 interface resets
  Total output drops: 0
TenGigabitEthernet1/0/1 is up, line protocol is up (connected)
  Hardware is Ten Gigabit Ethernet, address is 0200.0000.0003
  Full-duplex, 10Gb/s, media type is SFP-10GBase-SR
  5 minute input rate 1000 bits/sec, 1 packets/sec
  5 minute output rate 2000 bits/sec, 2 packets/sec
     1 packets input, 100 bytes, 0 no buffer
     0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored
     2 packets output, 200 bytes, 0 underruns
     0 output errors, 0 collisions, 0 interface resets
  Total output drops: 0
Vlan10 is up, line protocol is up
  Hardware is EtherSVI, address is 0200.0000.0010
"""


def status_row(port, name, status, vlan, duplex, speed, media):
    return f"{port:<10}{name:<19}{status:<13}{vlan:<11}{duplex:<8}{speed:<6}{media}\n"


STATUS = "Port      Name               Status       Vlan       Duplex  Speed Type\n" + "".join([
    status_row("Gi1/0/1", "office-ap", "connected", "10", "a-full", "a-1000", "10/100/1000BaseTX"),
    status_row("Gi1/0/2", "", "disabled", "1", "auto", "auto", "10/100/1000BaseTX"),
    status_row("Te1/0/1", "uplink", "connected", "trunk", "full", "10G", "SFP-10GBase-SR"),
])


OUTPUTS = {
    "show version": VERSION,
    "show interfaces": INTERFACES,
    "show interfaces status": STATUS,
    "show ip interface": "Vlan10 is up, line protocol is up\n  Internet address is 192.0.2.2/24\n",
    "show mac address-table": "Mac Address Table\nVlan    Mac Address       Type        Ports\n  10    0200.0000.0011    DYNAMIC     Gi1/0/1\nTotal Mac Addresses for this criterion: 1\n",
    "show arp": "Protocol  Address          Age (min)  Hardware Addr   Type   Interface\nInternet  192.0.2.11            2   0200.0000.0011  ARPA   Vlan10\n",
}


def snapshot(system, outputs=None):
    client, store, _, _ = system
    login(client)
    device = store.get_device(add_device(client, collector="cisco_ios")['id'])
    return merge_snapshot(device, parse_snapshot(device, outputs or OUTPUTS))


def test_2960x_inventory_uses_reported_ports_and_metrics(system):
    device, batch = snapshot(system)
    assert device.vendor == "Cisco"
    assert device.model == "WS-C2960X-48FPD-L"
    assert device.os_version == "15.2(7)E10"
    assert device.serial == "FOC0000TEST"
    assert len(device.physical_ports) == 3  # Never manufacture the model's 48 + 2 ports.
    assert [port.connector for port in device.physical_ports] == ["rj45", "rj45", "sfp"]
    assert [(port.group, port.label) for port in device.physical_ports] == [
        ("GigabitEthernet1/0", "1"), ("GigabitEthernet1/0", "2"),
        ("TenGigabitEthernet1/0", "1"),
    ]
    assert not any(port.verified_layout for port in device.physical_ports)
    first, second, uplink, svi = batch.interfaces
    assert first.admin_up is first.oper_up is True
    assert first.capacity_bps == 1_000_000_000 and first.duplex == "full"
    assert first.rx_bps == 8000 and first.tx_bps == 16000
    assert first.in_octets == 1000 and first.out_octets == 2000
    assert first.rate_interval_seconds == 300
    assert first.access_vlan == first.pvid == 10 and first.vlan_mode == "access"
    assert second.admin_up is second.oper_up is False
    assert uplink.capacity_bps == 10_000_000_000 and uplink.vlan_mode == "trunk"
    assert svi.addresses == ["192.0.2.2/24"] and svi.vrf_known is False
    assert batch.health.uptime_seconds == 788640
    assert batch.health.status == "unknown"
    assert batch.neighbors == []
    assert batch.endpoints.status == "ok"
    assert batch.endpoints.entries[0].addresses == ["192.0.2.11"]
    assert batch.endpoints.entries[0].vlan == 10


@pytest.mark.parametrize("media,expected", [
    ("10/100/1000BaseTX", "rj45"),
    ("1000BaseT", "rj45"),
    ("SFP-10GBase-SR", "sfp"),
    ("1000BaseLX SFP", "sfp"),
    ("1000BaseT SFP", "sfp"),
    ("QSFP-40G-SR4", "qsfp"),
    ("Not Present", "unknown"),
])
def test_connector_classification_requires_status_type_evidence(media, expected):
    assert connector_kind(media) == expected


@pytest.mark.parametrize("command,output,code", [
    ("show version", "Cisco IOS Software, Version 15.2", "collector_not_cisco_2960x"),
    ("show interfaces", "unknown format", "collector_parse_failed"),
    ("show interfaces status", "unknown format", "collector_parse_failed"),
])
def test_required_output_fails_closed(system, command, output, code):
    with pytest.raises(ConnectionPolicyError, match=code):
        snapshot(system, {**OUTPUTS, command: output})


def test_partially_recognized_port_table_does_not_replace_inventory(system):
    broken = "\n".join(STATUS.splitlines()[:2] + ["UnrecognizedRow bad-row-a"])
    with pytest.raises(ConnectionPolicyError, match="collector_parse_failed"):
        snapshot(system, {**OUTPUTS, "show interfaces status": broken})


def test_duplicate_physical_port_is_not_silently_accepted(system):
    with pytest.raises(ConnectionPolicyError, match="collector_parse_failed"):
        snapshot(system, {**OUTPUTS, "show interfaces status": STATUS + STATUS.splitlines()[1] + "\n"})


def test_optional_outputs_and_manual_geometry_are_preserved(system):
    client, store, _, _ = system
    login(client)
    device = add_device(client, collector="cisco_ios")
    manual = inventory()
    manual["interfaces"][0]["name"] = "Gi1/0/1"
    assert client.put(f"/api/v1/devices/{device['id']}/inventory", json=manual).status_code == 200
    current = store.get_device(device["id"])
    parsed = parse_snapshot(current, {key: value for key, value in OUTPUTS.items() if key in {
        "show version", "show interfaces", "show interfaces status"
    }}, {"show ip interface": "collector_command_unsupported",
         "show mac address-table": "collector_command_unsupported", "show arp": "collector_command_unsupported"})
    updated, batch = merge_snapshot(current, parsed)
    assert updated.physical_ports == current.physical_ports
    assert updated.components == current.components
    assert updated.inventory_source == "manual"
    assert updated.interfaces[0].id == "if1"
    assert batch.endpoints.status == "unsupported"
    assert batch.health.alerts


def test_cisco_collector_contract_and_existing_legacy_profile(system):
    client, _, _, _ = system
    login(client)
    device = add_device(client)
    response = client.put(f"/api/v1/devices/{device['id']}/connection-settings", json={
        "collector": "cisco_ios", "ssh_profile": "huawei_legacy", "legacy_ssh_confirmed": True,
    })
    assert response.status_code == 200
    assert response.json()["collector"] == "cisco_ios"
    assert response.json()["ssh_profile"] == "huawei_legacy"


def test_reader_rejects_non_allowlisted_commands_and_output_overflow(monkeypatch):
    class Stream:
        async def read(self, _): return "x" * 100
    class Process:
        stdout = Stream()
    monkeypatch.setattr("app.cisco.MAX_OUTPUT", 50)
    with pytest.raises(ConnectionPolicyError, match="collector_output_limit"):
        asyncio.run(IOSReader(Process()).read_prompt())
    with pytest.raises(ConnectionPolicyError, match="collector_command_denied"):
        asyncio.run(IOSReader(Process()).command("configure terminal"))


@pytest.fixture
def ios_server():
    loop, ready = asyncio.new_event_loop(), Future()
    key = asyncssh.generate_private_key("ssh-rsa")
    state = {"commands": [], "outputs": dict(OUTPUTS), "pages": 0, "auth_attempts": 0}

    class Server(asyncssh.SSHServer):
        def begin_auth(self, username): return True
        def password_auth_supported(self): return True
        def validate_password(self, username, password):
            state["auth_attempts"] += 1
            return username == "lab" and password == "lab-secret"

    async def terminal(process):
        process.stdout.write("\r\nQA-C2960X#")
        try:
            while line := await process.stdin.readline():
                command = line.strip()
                state["commands"].append(command)
                output = state["outputs"].get(command, "% Invalid input detected at '^' marker.\n")
                if command == "show interfaces status":
                    middle = output.find("\n", len(output) // 2) + 1
                    process.stdout.write(command + "\r\n" + output[:middle] + " --More-- ")
                    assert await process.stdin.read(1) == " "
                    state["pages"] += 1
                    process.stdout.write("\b" * 10 + output[middle:] + "\r\nQA-C2960X#")
                else:
                    process.stdout.write(command + "\r\n" + output + "\r\nQA-C2960X#")
        finally:
            process.exit(0)

    async def start():
        return await asyncssh.create_server(
            Server, "127.0.0.1", 0, server_host_keys=[key], process_factory=terminal,
            kex_algs=["diffie-hellman-group-exchange-sha1"],
            encryption_algs=["aes128-ctr"], signature_algs=["ssh-rsa"], line_editor=False,
        )

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
        for task in pending:
            task.cancel()
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
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(.02)
    pytest.fail("Job did not complete")


def test_real_legacy_ssh_collection_and_failed_refresh_preserves_inventory(system, ios_server):
    client, _, _, _ = system
    login(client)
    port, key, state = ios_server
    device = add_device(
        client, collector="cisco_ios", ssh_profile="huawei_legacy", legacy_ssh_confirmed=True,
        ssh_port=port, credentials={"username": "lab", "password": "lab-secret"},
    )
    base = f"/api/v1/devices/{device['id']}"
    trusted = client.put(base + "/host-key", json={
        "public_key": key.export_public_key().decode(), "fingerprint": key.get_fingerprint(),
    })
    assert trusted.status_code == 200
    assert wait_job(client, device, "connection-tests")["status"] == "succeeded"
    job = wait_job(client, device)
    assert job["status"] == "partial", job  # Lab doesn't implement optional health/LLDP commands.
    from app.driver_catalog import IOS
    assert state["commands"] == [c.text for c in IOS]
    assert state["pages"] == 1
    current = client.get(base).json()
    assert current["model"] == "WS-C2960X-48FPD-L"
    assert len(current["physical_ports"]) == 3
    state["outputs"]["show interfaces status"] = "unrecognized\n"
    assert wait_job(client, device)["error_code"] == "collector_parse_failed"
    assert client.get(base).json() == current
