"""Run with python -m app.worker; independent of API lifetime and browser cookies."""
import asyncio
from contextlib import suppress
import os
import signal
import socket
import sys
import time
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
import sqlalchemy as sa

from .auth import Auth
from .collection import ReadResult, metadata, persist, upsert
from .database import Store, now
from .driver_catalog import GROUPS
from .drivers import collect
from . import queue, scheduler
from .security import Permission, has_permission
from .ssh import ConnectionPolicyError, connect, discover_host_key, error_code, target_allowed
from .ssh_profiles import target_signature
from .vault import CredentialVault


class Worker:
    def __init__(self, store, vault, auth=None, *, scheduling=True):
        self.store, self.vault, self.auth = store, vault, auth or Auth(store)
        self.owner = f"collector:{socket.gethostname()}:{uuid4()}"
        self.scheduling = scheduling
        self.tasks = set()
        self.stopping = asyncio.Event()

    async def run(self):
        last_schedule = last_cleanup = 0
        try:
            while not self.stopping.is_set():
                try:
                    if self.scheduling and time.monotonic() - last_schedule >= 2:
                        scheduler.schedule(self.store)
                        last_schedule = time.monotonic()
                    if time.monotonic() - last_cleanup >= 60:
                        from .history import maintain
                        maintain(self.store)
                        last_cleanup = time.monotonic()
                    while len(self.tasks) < queue.MAX_RUNNING and (job := queue.claim(self.store, self.owner)):
                        task = asyncio.create_task(self.execute(job))
                        self.tasks.add(task)
                        task.add_done_callback(self.tasks.discard)
                    with self.store.engine.begin() as conn:
                        upsert(conn, self.store.worker_heartbeats, self.store.worker_heartbeats.c.id == self.owner,
                            dict(id=self.owner, heartbeat_at=now(), running=len(self.tasks)))
                except Exception:
                    # Never log driver exceptions, raw responses, keys or secrets.
                    import logging
                    logging.getLogger(__name__).error("collector_tick_failed")
                try:
                    await asyncio.wait_for(self.stopping.wait(), .2)
                except TimeoutError:
                    pass
        finally:
            for task in self.tasks:
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
            with self.store.engine.begin() as conn:
                conn.execute(self.store.worker_heartbeats.delete().where(self.store.worker_heartbeats.c.id == self.owner))

    async def execute(self, job):
        started = time.monotonic()
        device = self.store.get_device(job.device_id)
        with self.store.engine.connect() as conn:
            context = conn.execute(sa.select(self.store.job_contexts).where(self.store.job_contexts.c.job_id == job.id)).mappings().one()
        lost = asyncio.Event()
        async def renew():
            while True:
                await asyncio.sleep(5)
                if not queue.heartbeat(self.store, job, self.owner):
                    lost.set()
                    return
        renewal = asyncio.create_task(renew())

        def authorize():
            if lost.is_set():
                raise ConnectionPolicyError("worker_lease_lost")
            target_allowed(self.store, device)
            if target_signature(device) != context["target_signature"]:
                raise ConnectionPolicyError("device_connection_changed")
            with self.store.engine.connect() as conn:
                queue.owned(self.store, job, self.owner, conn)
                if context["actor_kind"] == "system":
                    policy = conn.execute(sa.select(self.store.polling).where(self.store.polling.c.device_id == device.id)).mappings().first()
                    if not policy or not policy["settings"]["enabled"] or policy["paused_reason"] or policy["version"] != context["policy_version"]:
                        raise ConnectionPolicyError("collection_policy_changed")
            if context["actor_kind"] == "user":
                auth = self.auth.validate_hash(context["session_hash"])
                permission = Permission.CREDENTIAL_MANAGE if job.kind == "ssh_discovery" else Permission.JOB_CREATE
                if not has_permission(auth.user, permission, device.site):
                    raise ConnectionPolicyError("session_revoked")

        status, result, error, cpu = "succeeded", None, None, None
        channel_pause, reboot = None, False
        try:
            authorize()
            if job.kind == "ssh_discovery":
                key, profile = await discover_host_key(self.store, device, authorize=authorize)
                authorize()
                with self.store.engine.begin() as conn:
                    queue.owned(self.store, job, self.owner, conn)
                    conn.execute(self.store.host_candidates.update().where(self.store.host_candidates.c.id == context["candidate_id"],
                        self.store.host_candidates.c.expires_at > now(), self.store.host_candidates.c.consumed.is_(False)).values(
                        public_key=key.export_public_key().decode(), fingerprint=key.get_fingerprint("sha256"), profile=profile))
                result = {"candidate_id": context["candidate_id"], "profile": profile}
            elif job.kind == "connection_test":
                async with connect(self.store, self.vault, device):
                    authorize()
                result = {"reachable": True, "source": "ssh"}
            else:
                groups = context["groups"]
                with self.store.engine.connect() as conn:
                    policy_row = conn.execute(sa.select(self.store.polling).where(self.store.polling.c.device_id == device.id)).mappings().first()
                    policy = policy_row["settings"] if policy_row else {}
                    channel_pause = (policy_row["state"].get("channels", {}).get("snmp") if policy_row else None)
                snmp_read = None
                snmp_error = None
                preference = policy.get("preferred_source", "auto")
                if "fast" in groups and device.snmp_configured and policy.get("preferred_source", "auto") != "ssh" and device.interfaces:
                    from .snmp import collect_snmp
                    try:
                        if channel_pause:
                            raise ConnectionPolicyError(channel_pause)
                        snmp_read = await collect_snmp(self.store, self.vault, device, authorize)
                    except ConnectionPolicyError as exc:
                        snmp_error = str(exc)
                        if snmp_error in {"device_connection_changed", "worker_lease_lost", "session_revoked", "collection_policy_changed"}:
                            raise
                        if snmp_error == "snmp_authentication_failed":
                            channel_pause = snmp_error
                    except TimeoutError:
                        snmp_error = "snmp_timeout"
                    if snmp_read or preference == "snmp":
                        groups = [g for g in groups if g != "fast"]
                    if not snmp_read and preference == "snmp":
                        snmp_read = ReadResult(device, metadata={"fast": metadata("fast", "snmp_if_mib", source="snmp",
                            quality="error", complete=False, reason=snmp_error)})
                elif "fast" in groups and preference == "snmp" and not device.snmp_configured:
                    groups = [g for g in groups if g != "fast"]
                    snmp_read = ReadResult(device, metadata={"fast": metadata("fast", "snmp_if_mib", source="snmp",
                        quality="error", complete=False, reason="snmp_credentials_missing")})
                read = await collect(self.store, self.vault, device, groups, authorize) if groups else ReadResult(device)
                if preference == "snmp" and "fast" not in context["groups"]:
                    read.metadata.pop("fast", None)
                    read.payloads.pop("fast", None)
                if snmp_read:
                    if "fast" not in snmp_read.payloads:
                        read.payloads.pop("fast", None)
                    read.metadata.update(snmp_read.metadata)
                    read.payloads.update(snmp_read.payloads)
                    reboot = snmp_read.reboot_detected
                elif snmp_error and "fast" in read.metadata:
                    read.metadata["fast"].diagnostics["snmp"] = snmp_error
                    read.metadata["fast"].reason = "snmp_failed_using_ssh"
                authorize()
                data = persist(self.store, device, read, fence=lambda conn: queue.owned(self.store, job, self.owner, conn))
                cpu = read.payloads.get("health", {}).get("health", {}).get("cpu_percent")
                partial = any(m.quality != "ok" or m.diagnostics for m in read.metadata.values())
                status = "partial" if partial else "succeeded"
                result = {"interface_count": len(data["interfaces"]), "source": data["source"],
                    "collector": read.device.resolved_collector or device.collector, "groups": {
                        name: m.model_dump(mode="json") for name, m in read.metadata.items()},
                    "endpoint_status": data["endpoints"].get("status", "unknown"), "warnings": []}
                fast = read.metadata.get("fast")
                if fast and fast.quality not in {"ok", "partial"}:
                    error = fast.reason or "collector_parse_failed"
                if all(m.quality not in {"ok", "partial"} for m in read.metadata.values()):
                    error = "collector_parse_failed"
                    status = "failed"
        except asyncio.CancelledError:
            # Lease expiry reconciles an interrupted job. Do not mark all queued
            # work failed merely because a process is stopping.
            raise
        except Exception as exc:
            error = "session_revoked" if isinstance(exc, HTTPException) else error_code(exc)
            status = "blocked" if error in scheduler.PAUSE else "cancelled" if error in {
                "worker_lease_lost", "device_connection_changed", "collection_policy_changed", "session_revoked"} else "failed"
            if job.kind == "inventory_read" and status not in {"cancelled"}:
                with suppress(Exception):
                    failed = ReadResult(device, metadata={g: metadata(g, device.collector, quality="error", complete=False,
                        reason=error) for g in context["groups"]})
                    persist(self.store, device, failed, fence=lambda conn: queue.owned(self.store, job, self.owner, conn))
        finally:
            renewal.cancel()
            await asyncio.gather(renewal, return_exceptions=True)
        try:
            queue.finish(self.store, job, self.owner, status=status, result=result, error=error)
            if job.kind == "inventory_read" and status != "cancelled":
                scheduler.completed(self.store, device, context["groups"], time.monotonic() - started,
                    error=error, cpu=cpu, policy_version=context["policy_version"], channel_pause=channel_pause, reboot=reboot)
        except ConnectionPolicyError:
            pass  # New owner has the lease; this worker has no write authority.


async def main():
    store = Store()
    worker = Worker(store, CredentialVault(store, os.environ.get("STOCC_KEYRING_FILE")))
    for signum in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(signum, worker.stopping.set)
    try:
        await worker.run()
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    if "--healthcheck" in sys.argv:
        store = Store()
        with store.engine.connect() as conn:
            alive = conn.execute(sa.select(store.worker_heartbeats.c.id).where(
                store.worker_heartbeats.c.id.startswith(f"collector:{socket.gethostname()}:"),
                store.worker_heartbeats.c.heartbeat_at > now() - timedelta(seconds=30))).first()
        store.engine.dispose()
        sys.exit(0 if alive else 1)
    else:
        asyncio.run(main())
