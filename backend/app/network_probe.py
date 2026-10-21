"""VLAN-aware active IPv4 ARP probe orchestration and API routes.

The API never opens a raw socket.  It only approves bounded scopes, leases work
to a separately authenticated agent, and persists replies which still match a
fresh switch FDB observation in the exact site/VLAN/VRF scope.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, ip_address, ip_interface, ip_network
import json
import re
import secrets
from typing import Literal
from uuid import uuid4

from fastapi import Request, Response
from pydantic import Field, field_validator, model_validator
import sqlalchemy as sa

from .auth import digest, fail
from .contracts import StrictModel
from .database import now
from .security import Permission, has_permission

HEARTBEAT_SECONDS = 15
ONLINE_SECONDS = 45
LEASE_SECONDS = 120
DEFAULT_INTERVAL_SECONDS = 900
MAX_RANGE_PREFIX = 22
MAX_TARGETS = 4096
MAX_RATE_PPS = 64
RUN_RETENTION_DAYS = 30
MAC_PATTERN = re.compile(r"^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$")


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def json_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def normalize_mac(value: str) -> str:
    value = value.strip().lower().replace("-", ":")
    if not MAC_PATTERN.fullmatch(value) or value == "00:00:00:00:00:00" or int(value[:2], 16) & 1:
        raise ValueError("invalid_probe_mac")
    return value


class ProbeInterface(StrictModel):
    name: str = Field(min_length=1, max_length=160, pattern=r"^[^/\x00\r\n]+$")
    mac: str = Field(max_length=17)
    addresses: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("mac")
    @classmethod
    def valid_mac(cls, value):
        return normalize_mac(value)

    @field_validator("addresses")
    @classmethod
    def valid_addresses(cls, values):
        result = []
        for value in values:
            interface = ip_interface(value)
            if interface.version != 4 or interface.ip.is_unspecified or interface.ip.is_multicast or interface.ip.is_link_local:
                raise ValueError("invalid_probe_interface_address")
            result.append(str(interface))
        return sorted(set(result))


class EnrollmentCreate(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    site: str = Field(min_length=1, max_length=160)


class AgentHeartbeat(StrictModel):
    interfaces: list[ProbeInterface] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def unique_interfaces(self):
        if len({item.name for item in self.interfaces}) != len(self.interfaces):
            raise ValueError("duplicate_probe_interface")
        return self


class ScopeCreate(StrictModel):
    proposal_id: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    agent_id: str = Field(min_length=1, max_length=64)
    interface_name: str = Field(min_length=1, max_length=160)
    source_ip: str = Field(max_length=45)
    target_cidrs: list[str] = Field(min_length=1, max_length=16)
    interval_seconds: int = Field(default=DEFAULT_INTERVAL_SECONDS, ge=900, le=86400)
    vrf: str | None = Field(default=None, max_length=160)
    confirm_unknown_vrf: bool = False
    active_broadcast_acknowledged: bool

    @field_validator("source_ip")
    @classmethod
    def ipv4_source(cls, value):
        address = ip_address(value)
        if address.version != 4 or address.is_unspecified or address.is_multicast or address.is_link_local or address.is_loopback:
            raise ValueError("invalid_probe_source_ip")
        return str(address)


class ScopeUpdate(StrictModel):
    enabled: bool | None = None
    interface_name: str | None = Field(default=None, min_length=1, max_length=160)
    source_ip: str | None = Field(default=None, max_length=45)
    target_cidrs: list[str] | None = Field(default=None, min_length=1, max_length=16)
    interval_seconds: int | None = Field(default=None, ge=900, le=86400)
    active_broadcast_acknowledged: bool = False


class ProbeMatch(StrictModel):
    mac: str = Field(max_length=17)
    address: str = Field(max_length=45)

    @field_validator("mac")
    @classmethod
    def valid_mac(cls, value):
        return normalize_mac(value)

    @field_validator("address")
    @classmethod
    def ipv4_address(cls, value):
        address = ip_address(value)
        if address.version != 4 or address.is_unspecified or address.is_multicast or address.is_loopback:
            raise ValueError("invalid_probe_reply_address")
        return str(address)


class TaskResult(StrictModel):
    lease_token: str = Field(min_length=32, max_length=256)
    status: Literal["succeeded", "failed"]
    started_at: datetime
    completed_at: datetime
    target_count: int = Field(ge=0, le=MAX_TARGETS)
    reply_count: int = Field(ge=0, le=MAX_TARGETS)
    unknown_count: int = Field(ge=0, le=MAX_TARGETS)
    duration_ms: int = Field(ge=0, le=300_000)
    matches: list[ProbeMatch] = Field(default_factory=list, max_length=MAX_TARGETS)
    error_code: str | None = Field(default=None, max_length=160, pattern=r"^[a-z0-9_.-]+$")

    @model_validator(mode="after")
    def consistent(self):
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise ValueError("probe_result_timezone_required")
        if self.completed_at < self.started_at:
            raise ValueError("invalid_probe_result_time")
        if self.status == "succeeded" and self.error_code:
            raise ValueError("successful_probe_has_error")
        if self.status == "failed" and not self.error_code:
            raise ValueError("failed_probe_requires_error")
        pairs = {(item.mac, item.address) for item in self.matches}
        if (len(pairs) != len(self.matches) or self.unknown_count > self.reply_count
                or len(self.matches) > self.reply_count):
            raise ValueError("invalid_probe_reply_counts")
        return self


def derive_proposals(store, at=None):
    """Create stable, deduplicated scope proposals from fresh switch SVI evidence."""
    from .endpoint_resolution import latest_payloads, network_clock
    at = at or now()
    devices = {device.id: device for device in store.list_devices()}
    payloads = latest_payloads(store, devices)
    grouped = defaultdict(list)
    for device_id, device in devices.items():
        data = payloads.get(device_id) or {}
        observed, fresh = network_clock(data, at)
        if not fresh:
            continue
        for sample in data.get("interfaces", []):
            vlan = sample.get("l3_vlan")
            if not vlan:
                continue
            vrf_known = bool(sample.get("vrf_known", True))
            vrf = sample.get("vrf") if vrf_known else None
            for value in sample.get("addresses", []):
                try:
                    interface = ip_interface(value)
                except ValueError:
                    continue
                if not isinstance(interface, IPv4Interface) or interface.ip.is_loopback or interface.ip.is_link_local:
                    continue
                key = (device.site, int(vlan), vrf, vrf_known, str(interface.network))
                grouped[key].append({"device_id": device_id, "device_name": device.name,
                    "interface_id": sample.get("interface_id", ""), "address": str(interface),
                    "observed_at": sample.get("observed_at") or observed})
    proposals = []
    networks_by_scope = defaultdict(list)
    for key in grouped:
        site, vlan, vrf, vrf_known, network = key
        networks_by_scope[(site, vlan, vrf, vrf_known)].append(IPv4Network(network))
    for (site, vlan, vrf, vrf_known, network), evidence in grouped.items():
        identity = {"site": site, "vlan": vlan, "vrf": vrf, "vrf_known": vrf_known, "network": network}
        stable_evidence = sorted({(row["device_id"], row["interface_id"], row["address"]) for row in evidence})
        fingerprint = json_hash({"identity": identity, "sources": stable_evidence})
        current = IPv4Network(network)
        conflict = any(other != current and other.overlaps(current)
                       for other in networks_by_scope[(site, vlan, vrf, vrf_known)])
        proposals.append({**identity, "id": json_hash(identity), "evidence_fingerprint": fingerprint,
            "evidence": sorted(evidence, key=lambda row: (row["device_name"].casefold(), row["interface_id"])),
            "conflict": conflict, "requires_narrowing": current.prefixlen < MAX_RANGE_PREFIX,
            "max_prefix_span": MAX_RANGE_PREFIX})
    return sorted(proposals, key=lambda row: (row["site"].casefold(), row["vlan"], row["vrf"] or "", row["network"]))


def proposal_map(store, at=None):
    return {item["id"]: item for item in derive_proposals(store, at)}


def online(agent, at=None):
    seen = aware(agent.get("last_seen_at"))
    return bool(agent.get("enabled") and not agent.get("revoked_at") and seen
                and seen >= (at or now()) - timedelta(seconds=ONLINE_SECONDS))


def target_networks(values, proposal):
    parent = IPv4Network(proposal["network"])
    networks, target_count = [], 0
    for value in values:
        try:
            network = ip_network(value, strict=True)
        except ValueError:
            fail("invalid_probe_target_cidr", 422)
        if not isinstance(network, IPv4Network) or network.prefixlen < MAX_RANGE_PREFIX or not network.subnet_of(parent):
            fail("invalid_probe_target_cidr", 422)
        if any(network.overlaps(existing) for existing in networks):
            fail("overlapping_probe_targets", 422)
        networks.append(network)
        target_count += sum(1 for _ in network.hosts())
    if target_count > MAX_TARGETS:
        fail("probe_target_budget_exceeded", 422)
    return sorted(networks, key=lambda item: (int(item.network_address), item.prefixlen)), target_count


def reported_source(agent, interface_name, source_ip, proposal):
    for interface in agent.get("interfaces") or []:
        if interface.get("name") != interface_name:
            continue
        for value in interface.get("addresses") or []:
            parsed = ip_interface(value)
            if str(parsed.ip) == source_ip and parsed.ip in IPv4Network(proposal["network"]):
                return str(parsed)
    fail("probe_source_not_reported", 422)


def validate_scope(store, value: ScopeCreate, *, ignore_scope_id=None, at=None):
    if not value.active_broadcast_acknowledged:
        fail("active_probe_acknowledgement_required", 422)
    proposals = proposal_map(store, at)
    proposal = proposals.get(value.proposal_id)
    if not proposal or proposal["conflict"]:
        fail("probe_proposal_unavailable", 409)
    with store.engine.connect() as conn:
        agent = conn.execute(sa.select(store.network_probe_agents).where(
            store.network_probe_agents.c.id == value.agent_id)).mappings().first()
        scopes = conn.execute(sa.select(store.network_probe_scopes).where(
            store.network_probe_scopes.c.enabled.is_(True))).mappings().all()
    if not agent or not online(agent, at) or agent["site"] != proposal["site"]:
        fail("probe_agent_offline_or_wrong_site", 409)
    chosen_vrf = proposal["vrf"]
    if proposal["vrf_known"]:
        if value.vrf != chosen_vrf:
            fail("probe_vrf_mismatch", 422)
    else:
        if not value.confirm_unknown_vrf:
            fail("probe_vrf_confirmation_required", 422)
        chosen_vrf = value.vrf
    networks, target_count = target_networks(value.target_cidrs, proposal)
    source_cidr = reported_source(agent, value.interface_name, value.source_ip, proposal)
    svi_addresses = {str(ip_interface(item["address"]).ip) for item in proposal["evidence"]}
    if value.source_ip in svi_addresses:
        fail("probe_source_conflicts_with_svi", 422)
    for row in scopes:
        if row["id"] == ignore_scope_id or row["site"] != proposal["site"] or row["vlan"] != proposal["vlan"]:
            continue
        if row["vrf_known"] and (row["vrf"] or None) != (chosen_vrf or None):
            continue
        if any(left.overlaps(ip_network(right)) for left in networks for right in row["target_cidrs"]):
            fail("probe_scope_overlap", 409)
    return proposal, chosen_vrf, source_cidr, [str(network) for network in networks], target_count


def current_fdb_macs(store, scope, at=None):
    from .endpoint_resolution import latest_payloads, network_clock
    at = at or now()
    devices = {device.id: device for device in store.list_devices() if device.site == scope["site"]}
    payloads = latest_payloads(store, devices)
    result = set()
    for device_id, data in payloads.items():
        _, fresh = network_clock(data, at, endpoints=True)
        if not fresh:
            continue
        for entry in (data.get("endpoints") or {}).get("entries", []):
            if entry.get("discovery") != "fdb" or entry.get("state") == "stale" or entry.get("vlan") != scope["vlan"]:
                continue
            if entry.get("vrf_known") and (entry.get("vrf") or None) != (scope.get("vrf") or None):
                continue
            try:
                result.add(normalize_mac(entry["mac"]))
            except (KeyError, ValueError):
                continue
    return result


def task_payload(store, scope, at=None):
    at = at or now()
    macs = sorted(current_fdb_macs(store, scope, at))
    excluded = set()
    for item in scope["evidence"]:
        try:
            excluded.add(str(ip_interface(item["address"]).ip))
        except ValueError:
            pass
    with store.engine.connect() as conn:
        interfaces = conn.execute(sa.select(store.network_probe_agents.c.interfaces).where(
            store.network_probe_agents.c.site == scope["site"], store.network_probe_agents.c.enabled.is_(True))).scalars().all()
    for rows in interfaces:
        for interface in rows or []:
            for value in interface.get("addresses") or []:
                try:
                    excluded.add(str(ip_interface(value).ip))
                except ValueError:
                    pass
    excluded.add(scope["source_ip"])
    excluded = sorted(excluded)
    target_count = sum(1 for cidr in scope["target_cidrs"] for address in ip_network(cidr).hosts()
                       if str(address) not in excluded)
    return {"scope_id": scope["id"], "site": scope["site"], "vlan": scope["vlan"],
        "vrf": scope["vrf"], "interface_name": scope["interface_name"], "source_ip": scope["source_ip"],
        "source_cidr": scope["source_cidr"], "target_cidrs": scope["target_cidrs"],
        "excluded_addresses": excluded, "allowed_macs": macs, "target_count": target_count,
        "max_rate_pps": MAX_RATE_PPS, "reply_wait_seconds": 2, "policy_version": scope["version"]}


def enqueue_scope(store, scope, actor_kind, requested_by, at=None, conn=None):
    at = at or now()
    payload = task_payload(store, scope, at)
    values = {"id": str(uuid4()), "scope_id": scope["id"], "agent_id": scope["agent_id"],
        "status": "queued", "actor_kind": actor_kind, "requested_by": requested_by,
        "policy_version": scope["version"], "payload": payload, "attempt": 0, "queued_at": at}
    def write(connection):
        pending = connection.execute(sa.select(store.network_probe_tasks.c.id).where(
            store.network_probe_tasks.c.scope_id == scope["id"],
            store.network_probe_tasks.c.status.in_(("queued", "leased")))).first()
        if pending:
            return pending[0], False
        connection.execute(store.network_probe_tasks.insert().values(**values))
        return values["id"], True
    if conn is not None:
        return write(conn)
    with store.engine.begin() as connection:
        return write(connection)


def next_due(scope_id, at, interval):
    bucket = int(at.timestamp()) // interval
    fraction = int(hashlib.sha256(f"{scope_id}:{bucket}".encode()).hexdigest()[:8], 16) / 0xffffffff
    return at + timedelta(seconds=round(interval * (.9 + .2 * fraction)))


def schedule_due(store, at=None):
    at = at or now()
    proposals = proposal_map(store, at)
    with store.engine.begin() as conn:
        conn.execute(store.network_probe_observations.delete().where(store.network_probe_observations.c.expires_at <= at))
        retention = at - timedelta(days=RUN_RETENTION_DAYS)
        conn.execute(store.network_probe_runs.delete().where(store.network_probe_runs.c.completed_at < retention))
        conn.execute(store.network_probe_tasks.delete().where(store.network_probe_tasks.c.finished_at < retention,
            store.network_probe_tasks.c.status.in_(("succeeded", "failed", "cancelled")),
            ~sa.exists(sa.select(store.network_probe_observations.c.task_id).where(
                store.network_probe_observations.c.task_id == store.network_probe_tasks.c.id))))
        conn.execute(store.network_probe_enrollments.delete().where(store.network_probe_enrollments.c.expires_at < at - timedelta(days=1)))
        expired = conn.execute(sa.select(store.network_probe_tasks).where(
            store.network_probe_tasks.c.status == "leased", store.network_probe_tasks.c.lease_expires_at <= at)).mappings().all()
        for task in expired:
            if task["attempt"] < 2:
                conn.execute(store.network_probe_tasks.update().where(store.network_probe_tasks.c.id == task["id"]).values(
                    status="queued", lease_token_hash=None, lease_expires_at=None))
            else:
                conn.execute(store.network_probe_tasks.update().where(store.network_probe_tasks.c.id == task["id"]).values(
                    status="failed", lease_token_hash=None, lease_expires_at=None, finished_at=at,
                    result={"error_code": "probe_lease_exhausted"}))
                conn.execute(store.network_probe_runs.insert().values(id=str(uuid4()), task_id=task["id"],
                    scope_id=task["scope_id"], status="failed", target_count=0, reply_count=0,
                    matched_count=0, unknown_count=0, duration_ms=0, error_code="probe_lease_exhausted",
                    started_at=aware(task["started_at"]) or at, completed_at=at))
                conn.execute(store.network_probe_scopes.update().where(store.network_probe_scopes.c.id == task["scope_id"])
                    .values(last_completed_at=at, last_error="probe_lease_exhausted"))
        scopes = conn.execute(sa.select(store.network_probe_scopes)).mappings().all()
        agents = {row["id"]: row for row in conn.execute(sa.select(store.network_probe_agents)).mappings()}
        for scope in scopes:
            proposal = proposals.get(scope["proposal_id"])
            if scope["enabled"] and (not proposal or proposal["evidence_fingerprint"] != scope["evidence_fingerprint"]):
                conn.execute(store.network_probe_scopes.update().where(store.network_probe_scopes.c.id == scope["id"])
                    .values(enabled=False, status="needs_review", updated_at=at, last_error="probe_evidence_changed"))
                conn.execute(store.network_probe_tasks.update().where(store.network_probe_tasks.c.scope_id == scope["id"],
                    store.network_probe_tasks.c.status.in_(("queued", "leased"))).values(status="cancelled",
                        lease_token_hash=None, lease_expires_at=None, finished_at=at))
                continue
            agent = agents.get(scope["agent_id"], {})
            if not scope["enabled"] or scope["status"] != "active":
                conn.execute(store.network_probe_tasks.update().where(store.network_probe_tasks.c.scope_id == scope["id"],
                    store.network_probe_tasks.c.status.in_(("queued", "leased"))).values(status="cancelled",
                        lease_token_hash=None, lease_expires_at=None, finished_at=at))
                continue
            if online(agent, at) and not any(interface.get("name") == scope["interface_name"]
                    and scope["source_cidr"] in (interface.get("addresses") or [])
                    for interface in agent.get("interfaces") or []):
                conn.execute(store.network_probe_scopes.update().where(store.network_probe_scopes.c.id == scope["id"])
                    .values(enabled=False, status="needs_review", updated_at=at, last_error="probe_source_changed"))
                conn.execute(store.network_probe_tasks.update().where(store.network_probe_tasks.c.scope_id == scope["id"],
                    store.network_probe_tasks.c.status.in_(("queued", "leased"))).values(status="cancelled",
                        lease_token_hash=None, lease_expires_at=None, finished_at=at))
                continue
            if aware(scope["next_due_at"]) > at:
                continue
            if not online(agent, at):
                continue
            _, created = enqueue_scope(store, scope, "scheduled", "system:network-probe", at, conn)
            if created:
                conn.execute(store.network_probe_scopes.update().where(store.network_probe_scopes.c.id == scope["id"])
                    .values(next_due_at=next_due(scope["id"], at, scope["interval_seconds"]), updated_at=at))


def authenticate_agent(store, request):
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 256:
        fail("probe_agent_authentication_required", 401)
    token_hash = digest(token)
    with store.engine.connect() as conn:
        row = conn.execute(sa.select(store.network_probe_agents).where(
            store.network_probe_agents.c.token_hash == token_hash)).mappings().first()
    if not row or not row["enabled"] or row["revoked_at"]:
        fail("probe_agent_authentication_required", 401)
    return row


def scope_json(row):
    result = dict(row)
    for key in ("next_due_at", "last_started_at", "last_completed_at", "last_success_at", "last_manual_at", "approved_at", "updated_at"):
        result[key] = aware(result.get(key)).isoformat() if result.get(key) else None
    return result


def dashboard(store):
    at = now()
    with store.engine.connect() as conn:
        agents = conn.execute(sa.select(store.network_probe_agents).order_by(store.network_probe_agents.c.name)).mappings().all()
        scopes = conn.execute(sa.select(store.network_probe_scopes).order_by(store.network_probe_scopes.c.site,
            store.network_probe_scopes.c.vlan)).mappings().all()
        runs = conn.execute(sa.select(store.network_probe_runs).order_by(store.network_probe_runs.c.completed_at.desc()).limit(50)).mappings().all()
    agent_rows = []
    for row in agents:
        item = dict(row)
        item.pop("token_hash", None)
        item["online"] = online(row, at)
        item["last_seen_at"] = aware(row["last_seen_at"]).isoformat() if row["last_seen_at"] else None
        item["enrolled_at"] = aware(row["enrolled_at"]).isoformat()
        item["revoked_at"] = aware(row["revoked_at"]).isoformat() if row["revoked_at"] else None
        agent_rows.append(item)
    run_rows = []
    for row in runs:
        item = dict(row)
        item["started_at"] = aware(row["started_at"]).isoformat()
        item["completed_at"] = aware(row["completed_at"]).isoformat()
        run_rows.append(item)
    return {"agents": agent_rows, "proposals": derive_proposals(store, at),
        "scopes": [scope_json(row) for row in scopes], "runs": run_rows,
        "defaults": {"interval_seconds": DEFAULT_INTERVAL_SECONDS, "max_range_prefix": MAX_RANGE_PREFIX,
            "max_targets": MAX_TARGETS, "max_rate_pps": MAX_RATE_PPS, "heartbeat_seconds": HEARTBEAT_SECONDS}}


def active_probe_state(store, devices, at=None):
    """Return only online, approved and recently successful scope projections."""
    at = at or now()
    sites = {device.site for device in devices.values()}
    if not sites:
        return {"scopes": [], "observations": defaultdict(list)}
    with store.engine.connect() as conn:
        rows = conn.execute(sa.select(store.network_probe_scopes, store.network_probe_agents.c.name.label("agent_name"),
            store.network_probe_agents.c.last_seen_at.label("agent_last_seen"),
            store.network_probe_agents.c.enabled.label("agent_enabled"),
            store.network_probe_agents.c.revoked_at.label("agent_revoked_at"))
            .join(store.network_probe_agents, store.network_probe_agents.c.id == store.network_probe_scopes.c.agent_id)
            .where(store.network_probe_scopes.c.site.in_(sites))).mappings().all()
        observations = conn.execute(sa.select(store.network_probe_observations).where(
            store.network_probe_observations.c.expires_at > at)).mappings().all()
    active = []
    active_ids = set()
    for row in rows:
        last_success = aware(row["last_success_at"])
        agent = {"enabled": row["agent_enabled"], "revoked_at": row["agent_revoked_at"],
            "last_seen_at": row["agent_last_seen"]}
        if (not row["enabled"] or row["status"] != "active" or not online(agent, at) or not last_success
                or last_success < at - timedelta(seconds=row["interval_seconds"] * 2)):
            continue
        item = dict(row)
        item["last_success_at"] = last_success
        active.append(item)
        active_ids.add(row["id"])
    by_scope = defaultdict(list)
    for row in observations:
        if row["scope_id"] in active_ids:
            by_scope[(row["scope_id"], row["mac"])].append(dict(row))
    return {"scopes": active, "observations": by_scope}


def install(app, context):
    class StoreProxy:
        def __getattr__(self, name):
            return getattr(app.state.store, name)
    store = StoreProxy()

    def manager(request, mutation=False):
        auth = context(request, mutation)
        if not has_permission(auth.user, Permission.NETWORK_PROBE_MANAGE, "*"):
            fail("forbidden", 403)
        return auth

    @app.get("/api/v1/network-probes")
    def list_network_probes(request: Request):
        manager(request)
        return dashboard(store)

    @app.post("/api/v1/network-probes/enrollments", status_code=201)
    def create_enrollment(value: EnrollmentCreate, request: Request):
        auth = manager(request, True)
        raw = secrets.token_urlsafe(48)
        at = now()
        with store.engine.begin() as conn:
            conn.execute(store.network_probe_enrollments.insert().values(id=str(uuid4()), name=value.name,
                site=value.site, token_hash=digest(raw), expires_at=at + timedelta(minutes=10), consumed_at=None,
                created_by=auth.user.user_id, created_at=at))
        store.record(auth.user.user_id, "network_probe.enrollment.created", "succeeded", target_type="network_probe",
            target_id=value.site, details={"name": value.name, "site": value.site, "expires_in": 600})
        return {"enrollment_token": raw, "expires_at": (at + timedelta(minutes=10)).isoformat()}

    @app.delete("/api/v1/network-probes/agents/{agent_id}")
    def revoke_agent(agent_id: str, request: Request):
        auth = manager(request, True)
        at = now()
        with store.engine.begin() as conn:
            row = conn.execute(sa.select(store.network_probe_agents).where(
                store.network_probe_agents.c.id == agent_id).with_for_update()).mappings().first()
            if not row:
                fail("probe_agent_not_found", 404)
            conn.execute(store.network_probe_agents.update().where(store.network_probe_agents.c.id == agent_id)
                .values(enabled=False, revoked_at=at))
            conn.execute(store.network_probe_scopes.update().where(store.network_probe_scopes.c.agent_id == agent_id)
                .values(enabled=False, status="disabled", updated_at=at, last_error="probe_agent_revoked"))
            conn.execute(store.network_probe_tasks.update().where(store.network_probe_tasks.c.agent_id == agent_id,
                store.network_probe_tasks.c.status.in_(("queued", "leased"))).values(status="cancelled",
                    lease_token_hash=None, lease_expires_at=None, finished_at=at))
        store.record(auth.user.user_id, "network_probe.agent.revoked", "succeeded", target_type="network_probe", target_id=agent_id)
        return {"status": "revoked"}

    @app.post("/api/v1/network-probes/scopes", status_code=201)
    def create_scope(value: ScopeCreate, request: Request):
        auth = manager(request, True)
        proposal, vrf, source_cidr, targets, _ = validate_scope(store, value)
        at, scope_id = now(), str(uuid4())
        row = {"id": scope_id, "agent_id": value.agent_id, "site": proposal["site"], "vlan": proposal["vlan"],
            "vrf": vrf, "vrf_known": True, "interface_name": value.interface_name, "source_ip": value.source_ip,
            "source_cidr": source_cidr, "target_cidrs": targets, "proposal_id": proposal["id"],
            "evidence_fingerprint": proposal["evidence_fingerprint"], "evidence": proposal["evidence"],
            "interval_seconds": value.interval_seconds, "enabled": True, "status": "active", "version": 1,
            "next_due_at": at, "created_by": auth.user.user_id, "approved_at": at, "updated_at": at}
        with store.engine.begin() as conn:
            conn.execute(store.network_probe_scopes.insert().values(**row))
        store.record(auth.user.user_id, "network_probe.scope.created", "succeeded", target_type="network_probe", target_id=scope_id,
            details={"site": proposal["site"], "vlan": proposal["vlan"], "vrf": vrf, "target_cidrs": targets})
        return scope_json(row)

    @app.patch("/api/v1/network-probes/scopes/{scope_id}")
    def update_scope(scope_id: str, value: ScopeUpdate, request: Request):
        auth = manager(request, True)
        with store.engine.connect() as conn:
            current = conn.execute(sa.select(store.network_probe_scopes).where(
                store.network_probe_scopes.c.id == scope_id)).mappings().first()
        if not current:
            fail("probe_scope_not_found", 404)
        material = bool({"interface_name", "source_ip", "target_cidrs"} & value.model_fields_set)
        enabled = current["enabled"] if value.enabled is None else value.enabled
        interface_name = value.interface_name or current["interface_name"]
        source_ip = value.source_ip or current["source_ip"]
        targets = value.target_cidrs or current["target_cidrs"]
        interval = value.interval_seconds or current["interval_seconds"]
        proposal = proposal_map(store).get(current["proposal_id"])
        if enabled or material:
            if not proposal:
                fail("probe_proposal_unavailable", 409)
            check = ScopeCreate(proposal_id=current["proposal_id"], agent_id=current["agent_id"],
                interface_name=interface_name, source_ip=source_ip, target_cidrs=targets, interval_seconds=interval,
                vrf=current["vrf"], confirm_unknown_vrf=True,
                active_broadcast_acknowledged=value.active_broadcast_acknowledged or not material)
            proposal, _, source_cidr, targets, _ = validate_scope(store, check, ignore_scope_id=scope_id)
        else:
            source_cidr = current["source_cidr"]
        at = now()
        changes = {"enabled": enabled, "status": "active" if enabled else "disabled", "interface_name": interface_name,
            "source_ip": source_ip, "source_cidr": source_cidr, "target_cidrs": targets, "interval_seconds": interval,
            "version": current["version"] + 1, "updated_at": at,
            "evidence_fingerprint": proposal["evidence_fingerprint"] if proposal else current["evidence_fingerprint"],
            "evidence": proposal["evidence"] if proposal else current["evidence"],
            "last_error": None if enabled else current["last_error"], "next_due_at": at if enabled else current["next_due_at"]}
        with store.engine.begin() as conn:
            conn.execute(store.network_probe_scopes.update().where(store.network_probe_scopes.c.id == scope_id).values(**changes))
            conn.execute(store.network_probe_tasks.update().where(store.network_probe_tasks.c.scope_id == scope_id,
                store.network_probe_tasks.c.status.in_(("queued", "leased"))).values(status="cancelled",
                    lease_token_hash=None, lease_expires_at=None, finished_at=at))
        store.record(auth.user.user_id, "network_probe.scope.updated", "succeeded", target_type="network_probe", target_id=scope_id,
            details={"enabled": enabled, "interval_seconds": interval, "material_change": material})
        return scope_json({**dict(current), **changes})

    @app.delete("/api/v1/network-probes/scopes/{scope_id}")
    def delete_scope(scope_id: str, request: Request):
        auth = manager(request, True)
        with store.engine.begin() as conn:
            task_ids = sa.select(store.network_probe_tasks.c.id).where(store.network_probe_tasks.c.scope_id == scope_id)
            conn.execute(store.network_probe_observations.delete().where(store.network_probe_observations.c.scope_id == scope_id))
            conn.execute(store.network_probe_runs.delete().where(store.network_probe_runs.c.scope_id == scope_id))
            conn.execute(store.network_probe_tasks.delete().where(store.network_probe_tasks.c.id.in_(task_ids)))
            result = conn.execute(store.network_probe_scopes.delete().where(store.network_probe_scopes.c.id == scope_id))
            if result.rowcount != 1:
                fail("probe_scope_not_found", 404)
        store.record(auth.user.user_id, "network_probe.scope.deleted", "succeeded", target_type="network_probe", target_id=scope_id)
        return {"status": "deleted"}

    @app.post("/api/v1/network-probes/scopes/{scope_id}/runs", status_code=202)
    def run_scope(scope_id: str, request: Request):
        auth = manager(request, True)
        at = now()
        with store.engine.begin() as conn:
            scope = conn.execute(sa.select(store.network_probe_scopes).where(
                store.network_probe_scopes.c.id == scope_id).with_for_update()).mappings().first()
            if not scope or not scope["enabled"] or scope["status"] != "active":
                fail("probe_scope_not_active", 409)
            if scope["last_manual_at"] and aware(scope["last_manual_at"]) > at - timedelta(minutes=1):
                fail("probe_manual_rate_limited", 429)
            agent = conn.execute(sa.select(store.network_probe_agents).where(
                store.network_probe_agents.c.id == scope["agent_id"])).mappings().first()
            if not online(agent or {}, at):
                fail("probe_agent_offline_or_wrong_site", 409)
            task_id, created = enqueue_scope(store, scope, "manual", auth.user.user_id, at, conn)
            conn.execute(store.network_probe_scopes.update().where(store.network_probe_scopes.c.id == scope_id)
                .values(last_manual_at=at, next_due_at=next_due(scope_id, at, scope["interval_seconds"]), updated_at=at))
        store.record(auth.user.user_id, "network_probe.run.requested", "succeeded", target_type="network_probe", target_id=scope_id,
            details={"task_id": task_id, "coalesced": not created})
        return {"task_id": task_id, "coalesced": not created}

    @app.post("/api/v1/network-probe-agent/enroll", status_code=201)
    def enroll_agent(request: Request):
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token or len(token) > 256:
            fail("probe_enrollment_invalid", 401)
        at, permanent = now(), secrets.token_urlsafe(48)
        with store.engine.begin() as conn:
            enrollment = conn.execute(sa.select(store.network_probe_enrollments).where(
                store.network_probe_enrollments.c.token_hash == digest(token)).with_for_update()).mappings().first()
            if not enrollment or enrollment["consumed_at"] or aware(enrollment["expires_at"]) <= at:
                fail("probe_enrollment_invalid", 401)
            agent_id = str(uuid4())
            conn.execute(store.network_probe_agents.insert().values(id=agent_id, name=enrollment["name"], site=enrollment["site"],
                token_hash=digest(permanent), enabled=True, interfaces=[], enrolled_at=at, last_seen_at=None, revoked_at=None))
            conn.execute(store.network_probe_enrollments.update().where(store.network_probe_enrollments.c.id == enrollment["id"])
                .values(consumed_at=at))
        store.record(f"agent:{agent_id}", "network_probe.agent.enrolled", "succeeded", target_type="network_probe", target_id=agent_id,
            details={"site": enrollment["site"], "name": enrollment["name"]})
        return {"agent_id": agent_id, "agent_token": permanent, "site": enrollment["site"], "name": enrollment["name"]}

    @app.post("/api/v1/network-probe-agent/heartbeat")
    def heartbeat(value: AgentHeartbeat, request: Request):
        from .auditing import audit_request
        agent = authenticate_agent(store, request)
        at = now()
        with store.engine.begin() as conn:
            conn.execute(store.network_probe_agents.update().where(store.network_probe_agents.c.id == agent["id"])
                .values(last_seen_at=at, interfaces=[item.model_dump() for item in value.interfaces]))
        if current := audit_request.get():
            current.recorded = True
        return {"status": "ok", "next_heartbeat_seconds": HEARTBEAT_SECONDS}

    @app.post("/api/v1/network-probe-agent/tasks/claim")
    def claim_task(request: Request):
        from .auditing import audit_request
        agent = authenticate_agent(store, request)
        at = now()
        schedule_due(store, at)
        raw = secrets.token_urlsafe(48)
        with store.engine.begin() as conn:
            active = conn.execute(sa.select(store.network_probe_tasks.c.id).where(
                store.network_probe_tasks.c.agent_id == agent["id"], store.network_probe_tasks.c.status == "leased",
                store.network_probe_tasks.c.lease_expires_at > at)).first()
            if active:
                if current := audit_request.get():
                    current.recorded = True
                return Response(status_code=204)
            query = sa.select(store.network_probe_tasks).where(store.network_probe_tasks.c.agent_id == agent["id"],
                store.network_probe_tasks.c.status == "queued").order_by(store.network_probe_tasks.c.queued_at).limit(1)
            if conn.dialect.name != "sqlite":
                query = query.with_for_update(skip_locked=True)
            task = conn.execute(query).mappings().first()
            if not task:
                if current := audit_request.get():
                    current.recorded = True
                return Response(status_code=204)
            scope = conn.execute(sa.select(store.network_probe_scopes).where(
                store.network_probe_scopes.c.id == task["scope_id"])).mappings().first()
            if not scope or not scope["enabled"] or scope["status"] != "active" or scope["version"] != task["policy_version"]:
                conn.execute(store.network_probe_tasks.update().where(store.network_probe_tasks.c.id == task["id"])
                    .values(status="cancelled", finished_at=at))
                if current := audit_request.get():
                    current.recorded = True
                return Response(status_code=204)
            conn.execute(store.network_probe_tasks.update().where(store.network_probe_tasks.c.id == task["id"]).values(
                status="leased", lease_token_hash=digest(raw), lease_expires_at=at + timedelta(seconds=LEASE_SECONDS),
                attempt=task["attempt"] + 1, started_at=at))
            conn.execute(store.network_probe_scopes.update().where(store.network_probe_scopes.c.id == scope["id"])
                .values(last_started_at=at, updated_at=at))
        if current := audit_request.get():
            current.recorded = True
        return {"id": task["id"], "lease_token": raw, "lease_seconds": LEASE_SECONDS, **task["payload"]}

    @app.post("/api/v1/network-probe-agent/tasks/{task_id}/result")
    def submit_result(task_id: str, value: TaskResult, request: Request):
        agent = authenticate_agent(store, request)
        at = now()
        if aware(value.completed_at) > at + timedelta(seconds=30):
            fail("invalid_probe_result_time", 422)
        with store.engine.connect() as conn:
            task = conn.execute(sa.select(store.network_probe_tasks).where(
                store.network_probe_tasks.c.id == task_id)).mappings().first()
            scope = conn.execute(sa.select(store.network_probe_scopes).where(
                store.network_probe_scopes.c.id == task["scope_id"])).mappings().first() if task else None
        if not task or task["agent_id"] != agent["id"] or task["status"] != "leased" or aware(task["lease_expires_at"]) <= at:
            fail("probe_task_lease_invalid", 409)
        if not hmac.compare_digest(task["lease_token_hash"] or "", digest(value.lease_token)):
            fail("probe_task_lease_invalid", 409)
        if not scope or not scope["enabled"] or scope["status"] != "active" or scope["version"] != task["policy_version"]:
            fail("probe_scope_changed", 409)
        if aware(value.started_at) < aware(task["started_at"]) - timedelta(seconds=5):
            fail("invalid_probe_result_time", 422)
        if value.target_count != task["payload"].get("target_count"):
            fail("probe_result_target_count_mismatch", 422)
        allowed_macs = set(task["payload"].get("allowed_macs", []))
        current_macs = current_fdb_macs(store, scope, at)
        targets = [ip_network(item) for item in task["payload"]["target_cidrs"]]
        accepted = set()
        if value.status == "succeeded":
            for match in value.matches:
                if match.mac not in allowed_macs or match.mac not in current_macs:
                    continue
                address = IPv4Address(match.address)
                if not any(address in network for network in targets):
                    continue
                accepted.add((match.mac, match.address))
        result = {"target_count": value.target_count, "reply_count": value.reply_count,
            "matched_count": len(accepted), "unknown_count": value.unknown_count,
            "duration_ms": value.duration_ms, "error_code": value.error_code}
        retry_queued = False
        with store.engine.begin() as conn:
            locked = conn.execute(sa.select(store.network_probe_tasks).where(
                store.network_probe_tasks.c.id == task_id).with_for_update()).mappings().first()
            if not locked or locked["status"] != "leased" or not hmac.compare_digest(locked["lease_token_hash"] or "", digest(value.lease_token)):
                fail("probe_task_lease_invalid", 409)
            retry_queued = value.status == "failed" and locked["attempt"] < 2
            if value.status == "succeeded":
                conn.execute(store.network_probe_observations.delete().where(
                    store.network_probe_observations.c.scope_id == scope["id"]))
                expiry = aware(value.completed_at) + timedelta(seconds=scope["interval_seconds"] * 2)
                if accepted:
                    conn.execute(store.network_probe_observations.insert(), [{"scope_id": scope["id"], "mac": mac,
                        "address": address, "task_id": task_id, "observed_at": aware(value.completed_at), "expires_at": expiry}
                        for mac, address in sorted(accepted)])
            task_completion = {"status": "queued" if retry_queued else value.status, "result": result,
                "lease_token_hash": None, "lease_expires_at": None, "finished_at": None if retry_queued else at}
            conn.execute(store.network_probe_tasks.update().where(store.network_probe_tasks.c.id == task_id)
                .values(**task_completion))
            conn.execute(store.network_probe_runs.insert().values(id=str(uuid4()), task_id=task_id, scope_id=scope["id"],
                status=value.status, target_count=value.target_count, reply_count=value.reply_count,
                matched_count=len(accepted), unknown_count=value.unknown_count, duration_ms=value.duration_ms,
                error_code=value.error_code, started_at=aware(value.started_at), completed_at=aware(value.completed_at)))
            completion = {"last_completed_at": aware(value.completed_at), "last_error": value.error_code, "updated_at": at}
            if value.status == "succeeded":
                completion["last_success_at"] = aware(value.completed_at)
            conn.execute(store.network_probe_scopes.update().where(store.network_probe_scopes.c.id == scope["id"]).values(**completion))
        store.record(f"agent:{agent['id']}", "network_probe.run.completed", value.status,
            target_type="network_probe", target_id=scope["id"], details={**result, "retry_queued": retry_queued})
        return {"status": "retrying" if retry_queued else value.status, "matched_count": len(accepted)}
