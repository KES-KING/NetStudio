"""Restricted Linux AF_PACKET agent for approved NetStudio IPv4 ARP tasks.

The process has no database or device credentials.  Operators create VLAN
subinterfaces and assign unique source addresses before starting it.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, ip_address, ip_interface, ip_network
import json
import os
from pathlib import Path
import re
import select
import secrets
import signal
import socket
import struct
import sys
import threading
import time
import tomllib
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .network_probe import MAX_RATE_PPS, MAX_TARGETS, normalize_mac

ETH_P_ARP = 0x0806
SIOCGIFADDR = 0x8915
SIOCGIFNETMASK = 0x891B
SIOCGIFHWADDR = 0x8927


class AgentError(RuntimeError):
    pass


def utcnow():
    return datetime.now(timezone.utc)


def mac_bytes(value):
    return bytes.fromhex(normalize_mac(value).replace(":", ""))


def build_arp_request(source_mac: str, source_ip: str, target_ip: str) -> bytes:
    source = mac_bytes(source_mac)
    return (b"\xff" * 6 + source + struct.pack("!H", ETH_P_ARP)
        + struct.pack("!HHBBH", 1, 0x0800, 6, 4, 1) + source
        + IPv4Address(source_ip).packed + b"\x00" * 6 + IPv4Address(target_ip).packed)


def parse_arp_reply(frame: bytes, source_mac: str, source_ip: str, targets: set[str]):
    if len(frame) < 42:
        return None
    destination, ethernet_source, ether_type = frame[:6], frame[6:12], struct.unpack("!H", frame[12:14])[0]
    if ether_type != ETH_P_ARP:
        return None
    htype, ptype, hlen, plen, operation = struct.unpack("!HHBBH", frame[14:22])
    if (htype, ptype, hlen, plen, operation) != (1, 0x0800, 6, 4, 2):
        return None
    sender_mac, sender_ip = frame[22:28], str(IPv4Address(frame[28:32]))
    target_mac, target_ip = frame[32:38], str(IPv4Address(frame[38:42]))
    expected = mac_bytes(source_mac)
    if (destination != expected or target_mac != expected or target_ip != source_ip
            or ethernet_source != sender_mac or sender_ip not in targets or sender_mac == expected):
        return None
    try:
        mac = normalize_mac(":".join(f"{byte:02x}" for byte in sender_mac))
    except ValueError:
        return None
    return mac, sender_ip


def interface_ioctl(name: str, command: int) -> bytes:
    if len(name.encode()) > 15:
        raise AgentError("probe_interface_name_too_long")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
        return fcntl.ioctl(control.fileno(), command, struct.pack("256s", name.encode()))


def interface_state(name: str):
    try:
        hardware = interface_ioctl(name, SIOCGIFHWADDR)
        mac = ":".join(f"{byte:02x}" for byte in hardware[18:24])
        address = socket.inet_ntoa(interface_ioctl(name, SIOCGIFADDR)[20:24])
        netmask = socket.inet_ntoa(interface_ioctl(name, SIOCGIFNETMASK)[20:24])
        cidr = str(IPv4Interface(f"{address}/{netmask}"))
        return {"name": name, "mac": normalize_mac(mac), "addresses": [cidr]}
    except OSError as error:
        if error.errno in {19, 99}:  # absent interface or no IPv4 address
            return None
        raise AgentError("probe_interface_read_failed") from error


def configured_interfaces(config):
    rows = []
    names = config["interfaces"]
    if config.get("automatic"):
        names = sorted(name for _, name in socket.if_nameindex() if name != "lo" and len(name.encode()) <= 15)
    for name in names:
        state = interface_state(name)
        if state:
            rows.append(state)
    return rows


def load_config(path):
    with open(path, "rb") as handle:
        value = tomllib.load(handle)
    api_url = str(value.get("api_url", "")).rstrip("/")
    token_file = str(value.get("token_file", ""))
    interfaces = value.get("interfaces")
    if not api_url or not token_file or not isinstance(interfaces, list) or not interfaces:
        raise AgentError("probe_config_invalid")
    parsed = urlparse(api_url)
    local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not (local_http and value.get("allow_insecure_localhost") is True):
        raise AgentError("probe_https_required")
    if any(not isinstance(name, str) or not name or "/" in name or len(name.encode()) > 15 for name in interfaces):
        raise AgentError("probe_config_invalid")
    return {"api_url": api_url, "token_file": token_file, "interfaces": sorted(set(interfaces)),
        "automatic": False, "poll_seconds": max(1, min(int(value.get("poll_seconds", 3)), 30)),
        "timeout_seconds": max(2, min(int(value.get("timeout_seconds", 10)), 30))}


def automatic_config():
    api_url = os.getenv("NETSTUDIO_PROBE_API_URL", "http://127.0.0.1:8000").rstrip("/")
    parsed = urlparse(api_url)
    local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not local_http:
        raise AgentError("probe_https_required")
    state_dir = os.getenv("NETSTUDIO_PROBE_STATE_DIR", "/run/netstudio-probe")
    return {"api_url": api_url, "token_file": str(Path(state_dir) / "agent.token"),
        "bootstrap_token_file": os.getenv("NETSTUDIO_PROBE_BOOTSTRAP_TOKEN_FILE", "/run/secrets/network-probe-bootstrap.token"),
        "node_id_file": str(Path(state_dir) / "node-id"), "interfaces": [], "automatic": True,
        "poll_seconds": max(1, min(int(os.getenv("NETSTUDIO_PROBE_POLL_SECONDS", "3")), 30)),
        "timeout_seconds": max(2, min(int(os.getenv("NETSTUDIO_PROBE_TIMEOUT_SECONDS", "10")), 30))}


def read_secret(path):
    target = Path(path)
    stat = target.stat()
    if stat.st_mode & 0o077:
        raise AgentError("probe_token_permissions_invalid")
    value = target.read_text().strip()
    if not value or len(value) > 256:
        raise AgentError("probe_token_invalid")
    return value


def write_secret(path, value):
    target = Path(path)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = target.with_name(target.name + f".{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, (value + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, target)
    os.chmod(target, 0o600)


def persistent_node_id(path):
    target = Path(path)
    try:
        value = read_secret(target)
    except FileNotFoundError:
        value = secrets.token_hex(32)
        write_secret(target, value)
    if not re.fullmatch(r"[0-9a-f]{32,64}", value):
        raise AgentError("probe_node_id_invalid")
    return value


def api_call(config, token, path, method="POST", payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(config["api_url"] + path, data=body, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "NetStudio-Network-Probe/1"})
    try:
        with urlopen(request, timeout=config["timeout_seconds"]) as response:
            data = response.read()
            return json.loads(data) if data else None
    except HTTPError as error:
        try:
            code = json.loads(error.read()).get("detail", {}).get("code", "probe_api_rejected")
        except Exception:
            code = "probe_api_rejected"
        raise AgentError(code) from error
    except (URLError, TimeoutError) as error:
        raise AgentError("probe_api_unavailable") from error


def task_targets(task):
    networks = []
    for value in task.get("target_cidrs", []):
        network = ip_network(value, strict=True)
        if not isinstance(network, IPv4Network) or network.prefixlen < 22:
            raise AgentError("probe_task_invalid")
        networks.append(network)
    excluded = {str(ip_address(value)) for value in task.get("excluded_addresses", [])}
    targets = sorted({str(address) for network in networks for address in network.hosts()
                      if str(address) not in excluded}, key=lambda value: int(IPv4Address(value)))
    if not targets or len(targets) > MAX_TARGETS:
        raise AgentError("probe_task_target_budget_invalid")
    return targets


def validate_task_interface(task, states):
    state = next((item for item in states if item["name"] == task.get("interface_name")), None)
    if not state:
        raise AgentError("probe_task_interface_unavailable")
    source_ip = str(ip_address(task.get("source_ip", "")))
    source_cidr = str(ip_interface(task.get("source_cidr", "")))
    if str(ip_interface(source_cidr).ip) != source_ip or source_cidr not in state["addresses"]:
        raise AgentError("probe_task_source_changed")
    return state, source_ip


def scan(task, states):
    started = time.monotonic()
    targets = task_targets(task)
    state, source_ip = validate_task_interface(task, states)
    allowed = {normalize_mac(value) for value in task.get("allowed_macs", [])}
    rate = int(task.get("max_rate_pps", 0))
    wait_seconds = int(task.get("reply_wait_seconds", 0))
    if rate < 1 or rate > MAX_RATE_PPS or wait_seconds < 1 or wait_seconds > 5:
        raise AgentError("probe_task_rate_invalid")
    target_set, replies = set(targets), set()
    try:
        packet_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ARP))
        packet_socket.bind((state["name"], 0))
        packet_socket.setblocking(False)
    except PermissionError as error:
        raise AgentError("probe_raw_socket_denied") from error
    except OSError as error:
        raise AgentError("probe_socket_unavailable") from error

    def drain(timeout=0):
        ready, _, _ = select.select([packet_socket], [], [], timeout)
        while ready:
            try:
                frame = packet_socket.recv(2048)
            except BlockingIOError:
                break
            parsed = parse_arp_reply(frame, state["mac"], source_ip, target_set)
            if parsed:
                replies.add(parsed)
            ready, _, _ = select.select([packet_socket], [], [], 0)

    try:
        interval, next_send = 1 / rate, time.monotonic()
        for target in targets:
            delay = next_send - time.monotonic()
            if delay > 0:
                drain(delay)
            packet_socket.send(build_arp_request(state["mac"], source_ip, target))
            next_send = max(next_send + interval, time.monotonic())
            drain(0)
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            drain(min(.2, deadline - time.monotonic()))
    finally:
        packet_socket.close()
    matches = [{"mac": mac, "address": address} for mac, address in sorted(replies) if mac in allowed]
    unknown = sum(1 for mac, _ in replies if mac not in allowed)
    return {"target_count": len(targets), "reply_count": len(replies), "unknown_count": unknown,
        "matches": matches, "duration_ms": round((time.monotonic() - started) * 1000)}


class Agent:
    def __init__(self, config):
        self.config = config
        try:
            self.token = read_secret(config["token_file"])
        except FileNotFoundError:
            if not config.get("automatic"):
                raise
            self.token = bootstrap(config)
        self.stopping = threading.Event()
        self.heartbeat_thread = threading.Thread(target=self.heartbeat_loop, name="network-probe-heartbeat", daemon=True)

    def heartbeat(self):
        return api_call(self.config, self.token, "/api/v1/network-probe-agent/heartbeat",
            payload={"interfaces": configured_interfaces(self.config)})

    def heartbeat_loop(self):
        while not self.stopping.is_set():
            try:
                self.heartbeat()
            except AgentError:
                print("network_probe_heartbeat_failed", file=sys.stderr, flush=True)
            self.stopping.wait(15)

    def execute(self, task):
        started_at = utcnow()
        try:
            result = scan(task, configured_interfaces(self.config))
            payload = {"lease_token": task["lease_token"], "status": "succeeded", "started_at": started_at.isoformat(),
                "completed_at": utcnow().isoformat(), "error_code": None, **result}
        except AgentError as error:
            payload = {"lease_token": task["lease_token"], "status": "failed", "started_at": started_at.isoformat(),
                "completed_at": utcnow().isoformat(), "target_count": int(task.get("target_count", 0)), "reply_count": 0, "unknown_count": 0,
                "matches": [], "duration_ms": 0, "error_code": str(error)}
        api_call(self.config, self.token, f"/api/v1/network-probe-agent/tasks/{task['id']}/result", payload=payload)

    def run(self):
        self.heartbeat()
        self.heartbeat_thread.start()
        while not self.stopping.is_set():
            try:
                task = api_call(self.config, self.token, "/api/v1/network-probe-agent/tasks/claim")
                if task:
                    self.execute(task)
                    continue
            except AgentError:
                print("network_probe_cycle_failed", file=sys.stderr, flush=True)
            self.stopping.wait(self.config["poll_seconds"])


def enroll(config, enrollment_token_file):
    token = read_secret(enrollment_token_file)
    result = api_call(config, token, "/api/v1/network-probe-agent/enroll")
    write_secret(config["token_file"], result["agent_token"])
    return result["agent_id"]


def bootstrap(config):
    bootstrap_token = read_secret(config["bootstrap_token_file"])
    node_id = persistent_node_id(config["node_id_file"])
    name = socket.gethostname().strip()[:160] or "Yerel probe ajanı"
    result = api_call(config, bootstrap_token, "/api/v1/network-probe-agent/bootstrap", payload={
        "node_id": node_id, "name": name, "interfaces": configured_interfaces(config)})
    write_secret(config["token_file"], result["agent_token"])
    return result["agent_token"]


def main():
    parser = argparse.ArgumentParser(description="NetStudio VLAN-aware IPv4 ARP probe")
    startup = parser.add_mutually_exclusive_group(required=True)
    startup.add_argument("--config")
    startup.add_argument("--automatic", action="store_true")
    subcommands = parser.add_subparsers(dest="command")
    enrollment = subcommands.add_parser("enroll")
    enrollment.add_argument("--enrollment-token-file", required=True)
    args = parser.parse_args()
    try:
        if args.command == "enroll" and args.automatic:
            parser.error("enroll requires --config")
        config = automatic_config() if args.automatic else load_config(args.config)
        if args.command == "enroll":
            identifier = enroll(config, args.enrollment_token_file)
            print(f"Ajan kaydedildi: {identifier}")
            return
        agent = Agent(config)
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: agent.stopping.set())
        agent.run()
    except (AgentError, OSError, ValueError) as error:
        print(str(error) if isinstance(error, AgentError) else "network_probe_agent_failed", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
