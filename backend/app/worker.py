"""Run with python -m app.worker; independent of API lifetime and browser cookies."""
import asyncio
from contextlib import suppress
import signal
import socket
import sys
import time
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
import sqlalchemy as sa

from .legacy_compat import getenv
from .auth import Auth
from .collection import ReadResult, merge_read_results, metadata, persist, upsert
from .database import Store, now
from .driver_catalog import GROUPS
from . import queue, scheduler
from .security import Permission, has_permission
from .ssh import ConnectionPolicyError, connect, discover_host_key, error_code, target_allowed
from .ssh_profiles import target_signature
from .transport import SSHTransportAdapter, TransportContext
from .vault import CredentialVault
from .driver_profiles import REGISTRY


def implemented_transports(device):
    runtime = device.resolved_collector if device.collector == "auto" else device.collector
    profile = REGISTRY.runtime_profile(runtime) if runtime else None
    if not profile:
        # Legacy auto/external handling retains the existing SSH/SNMP behavior.
        return {"ssh", "snmp"}
    return {item.kind for item in profile.transports if item.state == "implemented"}


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
                    from .updates import maintenance
                    paused = maintenance(self.store)
                    if not paused and self.scheduling and time.monotonic() - last_schedule >= 2:
                        scheduler.schedule(self.store)
                        last_schedule = time.monotonic()
                    if time.monotonic() - last_cleanup >= 60:
                        from .history import maintain
                        maintain(self.store)
                        last_cleanup = time.monotonic()
                    while not paused and len(self.tasks) < queue.MAX_RUNNING and (job := queue.claim(self.store, self.owner)):
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
            if implemented_transports(device) & {"ssh", "snmp"}:
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
        channel_outcomes, reboot = {}, False
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
                transports = implemented_transports(device)
                if transports == {"api"}:
                    from .controller_transport import ControllerAPITransportAdapter
                    transport_context = TransportContext.create(
                        self.store, self.vault, device, authorize, timeout_seconds=60
                    )
                    await ControllerAPITransportAdapter().collect(transport_context, {"inventory"})
                    result = {"reachable": True, "source": "api"}
                else:
                    async with connect(self.store, self.vault, device):
                        authorize()
                    result = {"reachable": True, "source": "ssh"}
            else:
                groups = set(context["groups"])
                with self.store.engine.connect() as conn:
                    policy_row = conn.execute(sa.select(self.store.polling).where(self.store.polling.c.device_id == device.id)).mappings().first()
                    policy = policy_row["settings"] if policy_row else {}
                    channel_state = policy_row["state"] if policy_row else {}
                snmp_read = ssh_read = api_read = None
                snmp_error = ssh_error = api_error = None
                preference = policy.get("preferred_source", "auto")
                transports = implemented_transports(device)
                transport_context = TransportContext.create(
                    self.store, self.vault, device, authorize, timeout_seconds=180
                )
                if groups and "api" in transports and device.api_configured and preference not in {"ssh", "snmp"} and scheduler.channel_ready(channel_state, "api"):
                    from .controller_transport import ControllerAPITransportAdapter
                    try:
                        api_read = await ControllerAPITransportAdapter().collect(transport_context, groups)
                        channel_outcomes["api"] = None
                    except ConnectionPolicyError as exc:
                        api_error = str(exc)
                        if api_error in {"device_connection_changed", "worker_lease_lost", "session_revoked", "collection_policy_changed"}:
                            raise
                        channel_outcomes["api"] = api_error
                elif preference == "api" and not device.api_configured:
                    api_error = "controller_credentials_missing"
                    channel_outcomes["api"] = api_error

                if groups and "snmp" in transports and device.snmp_configured and preference not in {"ssh", "api"} and scheduler.channel_ready(channel_state, "snmp"):
                    from .snmp import SNMPTransportAdapter
                    try:
                        snmp_read = await SNMPTransportAdapter().collect(transport_context, groups)
                        channel_outcomes["snmp"] = None
                    except ConnectionPolicyError as exc:
                        snmp_error = str(exc)
                        if snmp_error in {"device_connection_changed", "worker_lease_lost", "session_revoked", "collection_policy_changed"}:
                            raise
                        channel_outcomes["snmp"] = snmp_error
                elif preference == "snmp" and not device.snmp_configured:
                    snmp_error = "snmp_credentials_missing"
                    channel_outcomes["snmp"] = snmp_error

                ssh_ready = device.credential_configured and device.host_key_fingerprint
                if groups and "ssh" in transports and preference not in {"snmp", "api"} and ssh_ready and scheduler.channel_ready(channel_state, "ssh"):
                    try:
                        ssh_read = await SSHTransportAdapter().collect(transport_context, groups)
                        channel_outcomes["ssh"] = None
                    except Exception as exc:
                        ssh_error = error_code(exc)
                        if ssh_error in {"device_connection_changed", "worker_lease_lost", "session_revoked", "collection_policy_changed"}:
                            raise
                        channel_outcomes["ssh"] = ssh_error
                elif preference == "ssh" and not ssh_ready:
                    ssh_error = "credentials_missing" if not device.credential_configured else "host_key_required"
                    channel_outcomes["ssh"] = ssh_error

                reads = [value for value in (ssh_read, api_read, snmp_read) if value]
                if reads:
                    read = merge_read_results(*reads)
                    reboot = bool(snmp_read and snmp_read.reboot_detected)
                    for channel, channel_error in (("snmp", snmp_error), ("api", api_error), ("ssh", ssh_error)):
                        if channel_error:
                            failed_source = channel
                            read.capability_evidence.extend((group, metadata(
                                group, f"{channel}_transport", source=failed_source,
                                quality="error", complete=False, reason=channel_error,
                            )) for group in groups)
                            for details in read.metadata.values():
                                details.diagnostics[channel] = channel_error
                                if details.quality == "ok":
                                    details.quality = "partial"
                                details.reason = f"{channel}_failed_using_alternate"
                else:
                    source = preference if preference in {"ssh", "snmp", "api"} else (
                        "api" if api_error else "snmp" if snmp_error else "ssh"
                    )
                    reason = {"api": api_error, "snmp": snmp_error, "ssh": ssh_error}[source]
                    read = ReadResult(device, metadata={group: metadata(
                        group, f"{source}_transport", source=source,
                        quality="error", complete=False,
                        reason=reason or f"{source}_channel_paused",
                    ) for group in groups})
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
                    error = error or "collector_parse_failed"
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
                    error=error, cpu=cpu, policy_version=context["policy_version"],
                    channel_outcomes=channel_outcomes, reboot=reboot)
        except ConnectionPolicyError:
            pass  # New owner has the lease; this worker has no write authority.


async def main():
    store = Store()
    worker = Worker(store, CredentialVault(store, getenv("NETSTUDIO_KEYRING_FILE")))
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
