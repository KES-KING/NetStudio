"""Bounded WebSocket/SSH bridge. The browser never chooses a network target."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from ipaddress import ip_address, ip_network
import json
import os
import time
from uuid import uuid4

import asyncssh
from fastapi import HTTPException, WebSocketDisconnect
import sqlalchemy as sa

from .auth import COOKIE, fail
from .security import Permission, SecretStoreError, has_permission


class ConnectionPolicyError(Exception):
    pass


def target_allowed(device):
    networks = [ip_network(s.strip()) for s in os.getenv("STOCC_SSH_ALLOWED_CIDRS", "").split(",") if s.strip()]
    address = ip_address(device.management_address)
    if not any(address in network for network in networks):
        raise ConnectionPolicyError("target_network_denied")


def host_key(store, device_id):
    with store.engine.connect() as conn:
        value = conn.execute(sa.select(store.host_keys.c.public_key).where(store.host_keys.c.device_id == device_id)).scalar_one_or_none()
    if not value:
        raise ConnectionPolicyError("host_key_required")
    return asyncssh.import_public_key(value)


@asynccontextmanager
async def connect(store, vault, device):
    target_allowed(device)
    trusted = host_key(store, device.id)
    credentials = vault.get(device.id)
    keys = []
    password = None
    if credentials["method"] == "private_key":
        try:
            keys = [asyncssh.import_private_key(credentials["private_key"], credentials.get("passphrase") or None)]
        except (ValueError, asyncssh.KeyImportError) as error:
            raise ConnectionPolicyError("invalid_private_key") from error
    else:
        password = credentials["password"]
    connection = await asyncio.wait_for(asyncssh.connect(
        device.management_address, port=device.ssh_port, username=credentials["username"], password=password,
        client_keys=keys, agent_path=None, config=[], known_hosts=([trusted], [], [], [], [], [], []),
        connect_timeout=10, login_timeout=10, keepalive_interval=20, keepalive_count_max=3,
        encoding="utf-8", errors="replace"), timeout=12)
    credentials.clear()
    try:
        yield connection
    finally:
        connection.close()
        await connection.wait_closed()


def error_code(error):
    if isinstance(error, asyncssh.HostKeyNotVerifiable):
        return "host_key_changed"
    if isinstance(error, asyncssh.PermissionDenied):
        return "authentication_failed"
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return "connection_timeout"
    if isinstance(error, (ConnectionPolicyError, SecretStoreError)):
        return str(error)
    return "connection_failed"


@dataclass
class TerminalSession:
    id: str
    user_id: str
    device_id: str
    auth_hash: str
    created: float = field(default_factory=time.monotonic)
    attached: bool = False
    stopped: asyncio.Event = field(default_factory=asyncio.Event)
    reason: str = "session_ended"


class SSHBroker:
    def __init__(self, store, vault, auth):
        self.store, self.vault, self.auth = store, vault, auth
        self.sessions = {}
        self.max_seconds = int(os.getenv("STOCC_SSH_MAX_SECONDS", "3600"))
        self.idle_seconds = int(os.getenv("STOCC_SSH_IDLE_SECONDS", "300"))

    def create(self, context, device):
        self.expire_pending()
        if any(s.user_id == context.user.user_id and s.device_id == device.id for s in self.sessions.values()):
            fail("terminal_already_open", 409)
        if len(self.sessions) >= 20 or sum(s.user_id == context.user.user_id for s in self.sessions.values()) >= 3:
            fail("terminal_limit", 429)
        target_allowed(device)
        host_key(self.store, device.id)
        if not device.credential_configured:
            fail("credentials_missing", 409)
        session = TerminalSession(str(uuid4()), context.user.user_id, device.id, context.session_hash)
        self.store.record(session.user_id, "ssh.created", "pending", device.id, session.id)
        self.sessions[session.id] = session
        return session

    def finish(self, session):
        if self.sessions.pop(session.id, None):
            self.store.record(session.user_id, "ssh.ended", session.reason, session.device_id, session.id)

    def expire_pending(self):
        for session in list(self.sessions.values()):
            if not session.attached and time.monotonic() - session.created > 30:
                session.reason = "session_expired"
                self.finish(session)

    def stop(self, session, reason="session_ended"):
        session.reason = reason
        session.stopped.set()
        if not session.attached:
            self.finish(session)

    def revoke(self, auth_hash=None, device_id=None):
        for session in list(self.sessions.values()):
            if (auth_hash and session.auth_hash == auth_hash) or (device_id and session.device_id == device_id):
                self.stop(session, "session_revoked")

    async def run(self, ws, session_id):
        session = self.sessions.get(session_id)
        try:
            self.auth.origin(ws)
            context = self.auth.validate(ws.cookies.get(COOKIE))
            device = self.store.get_device(session.device_id) if session else None
            if not session or session.attached or session.auth_hash != context.session_hash or not device:
                fail("terminal_session_invalid", 403)
            if not has_permission(context.user, Permission.TERMINAL_OPEN, device.site) or time.monotonic() - session.created > 30:
                fail("terminal_forbidden", 403)
        except HTTPException:
            await ws.close(code=1008)
            return
        session.attached = True
        await ws.accept()
        tasks = []
        try:
            await ws.send_json({"type": "status", "status": "connecting"})
            async with connect(self.store, self.vault, device) as conn:
                # Re-check after a slow handshake before allocating the remote PTY.
                context = self.auth.validate(ws.cookies.get(COOKIE))
                if session.stopped.is_set() or not has_permission(context.user, Permission.TERMINAL_OPEN, device.site):
                    session.reason = "session_revoked"
                    return
                process = await asyncio.wait_for(conn.create_process(term_type="xterm-256color", term_size=(80, 24)), 10)
                self.store.record(session.user_id, "ssh.started", "connected", device.id, session.id)
                await ws.send_json({"type": "status", "status": "connected"})
                last_input = time.monotonic()

                async def input_loop():
                    nonlocal last_input
                    budget, window = 0, time.monotonic()
                    while True:
                        raw = await ws.receive_text()
                        if len(raw.encode()) > 16384:
                            session.reason = "message_too_large"
                            return
                        stamp = time.monotonic()
                        if stamp - window >= 1:
                            budget, window = 0, stamp
                        budget += len(raw.encode())
                        if budget > 65536:
                            session.reason = "input_rate_limited"
                            return
                        message = json.loads(raw)
                        if message.get("type") == "input" and isinstance(message.get("data"), str):
                            context = self.auth.validate(ws.cookies.get(COOKIE))
                            if not has_permission(context.user, Permission.TERMINAL_OPEN, device.site):
                                session.reason = "session_revoked"
                                return
                            process.stdin.write(message["data"])
                            await process.stdin.drain()
                            last_input = stamp
                        elif message.get("type") == "resize":
                            cols, rows = message.get("cols"), message.get("rows")
                            if type(cols) is not int or type(rows) is not int or not (20 <= cols <= 400 and 5 <= rows <= 200):
                                session.reason = "invalid_terminal_size"
                                return
                            process.change_terminal_size(cols, rows)
                        elif message.get("type") == "close":
                            return
                        else:
                            session.reason = "invalid_message"
                            return

                async def output_loop(reader):
                    while chunk := await reader.read(4096):
                        await ws.send_json({"type": "output", "data": chunk})

                async def monitor():
                    while not session.stopped.is_set():
                        await asyncio.sleep(1)
                        current = self.auth.validate(ws.cookies.get(COOKIE))
                        if not has_permission(current.user, Permission.TERMINAL_OPEN, device.site):
                            session.reason = "session_revoked"
                            return
                        if time.monotonic() - session.created > self.max_seconds:
                            session.reason = "session_expired"
                            return
                        if time.monotonic() - last_input > self.idle_seconds:
                            session.reason = "idle_timeout"
                            return

                tasks = [asyncio.create_task(coro) for coro in (input_loop(), output_loop(process.stdout), monitor())]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
                process.close()
        except (WebSocketDisconnect, ConnectionError):
            session.reason = "disconnected"
        except HTTPException:
            session.reason = "session_revoked"
        except (json.JSONDecodeError, AttributeError, TypeError):
            session.reason = "invalid_message"
        except asyncio.CancelledError:
            session.reason = "server_shutdown"
            raise
        except Exception as error:
            session.reason = error_code(error)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.finish(session)
            try:
                await ws.send_json({"type": "status", "status": session.reason})
                await ws.close()
            except (RuntimeError, WebSocketDisconnect, OSError):
                pass
