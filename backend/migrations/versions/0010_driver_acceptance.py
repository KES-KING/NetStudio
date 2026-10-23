"""Add profile bindings, capability evidence, and acceptance records.

Revision ID: 0010_driver_acceptance
Revises: 0009_probe_auto_enroll

The backfill reads legacy device payloads but never rewrites them. Credentials,
host keys, inventory identifiers, telemetry, probe data, and jobs are outside
the migration's write set.
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

from app.compatibility_schema_v1 import define_tables


revision = "0010_driver_acceptance"
down_revision = "0009_probe_auto_enroll"
branch_labels = None
depends_on = None


DIRECT_PROFILES = {
    "cisco_ios": "cisco_ios",
    "cisco_iosxe": "cisco_iosxe",
    "cisco_nxos": "cisco_nxos",
    "juniper_junos": "juniper_junos",
    "aruba_aoscx": "aruba_aoscx",
    "arista_eos": "arista_eos",
    "mikrotik_routeros": "mikrotik_routeros",
    "dell_os10": "dell_os10",
    "extreme_exos": "extreme_exos",
}
SAFE_ALIASES = {
    "hp_procurve": "aruba_aoss",
    "hp_comware": "hpe_comware",
}
CONDITIONAL_ALIASES = {
    "huawei_vrp": ("huawei_vrp_v200", ("v200",)),
    "dell_force10": ("dell_os9", ("os9", "ftos")),
    "extreme_vsp": ("extreme_fabric_engine", ("fabric engine", "voss")),
}


def tables():
    meta = sa.MetaData()
    sa.Table("devices", meta, sa.Column("id", sa.String(64), primary_key=True))
    return define_tables(meta)


def _evidence(payload):
    allowed = ("vendor", "model", "os_version")
    return {
        key: str(payload[key])[:160]
        for key in allowed
        if payload.get(key)
    }


def _binding(payload, at):
    collector = str(payload.get("collector") or "external")
    resolved = payload.get("resolved_collector")
    os_version = str(payload.get("os_version") or "").casefold()
    configured_profile = resolved_profile = None
    profile_revision = None
    status = "unresolved"
    confidence = 0.0
    conflicts = []

    if collector == "external":
        status = "external"
    elif collector == "linux_ssh":
        status = "infrastructure_adapter"
    elif collector == "fortinet":
        status = "manual_resolution_required"
        conflicts = ["legacy_alias_ambiguous"]
    elif collector in DIRECT_PROFILES:
        configured_profile = DIRECT_PROFILES[collector]
    elif collector in SAFE_ALIASES:
        configured_profile = SAFE_ALIASES[collector]
    elif collector in CONDITIONAL_ALIASES:
        configured_profile, markers = CONDITIONAL_ALIASES[collector]
        if not any(marker in os_version for marker in markers):
            status = "manual_resolution_required"
            conflicts = ["identity_evidence_required"]

    if configured_profile:
        profile_revision = 1

    resolved_candidate = DIRECT_PROFILES.get(str(resolved))
    if resolved in CONDITIONAL_ALIASES:
        candidate, markers = CONDITIONAL_ALIASES[str(resolved)]
        if any(marker in os_version for marker in markers):
            resolved_candidate = candidate
    if (
        resolved_candidate
        and (collector == "auto" or resolved_candidate == configured_profile)
        and status != "manual_resolution_required"
    ):
        resolved_profile = resolved_candidate
        profile_revision = 1
        status = "matched"
        confidence = 1.0

    evidence = _evidence(payload)
    if payload.get("management_mode") in {
        "standalone", "controller_managed", "cloud_managed",
        "local_managed", "unknown",
    }:
        evidence["management_mode"] = payload["management_mode"]
    return {
        "device_id": payload["id"],
        "configured_profile_id": configured_profile,
        "legacy_collector_id": collector,
        "resolved_profile_id": resolved_profile,
        "profile_revision": profile_revision,
        "management_mode": "unknown",
        "resolution_status": status,
        "resolution_confidence": confidence,
        "resolution_conflicts": conflicts,
        "identity_evidence": evidence,
        "resolved_at": at if resolved_profile else None,
        "updated_at": at,
        "updated_by": "system:migration:0010",
        "binding_revision": 1,
    }


def upgrade():
    created = tables()
    bind = op.get_bind()
    for table in created.values():
        table.create(bind)

    devices = sa.table(
        "devices",
        sa.column("id", sa.String(64)),
        sa.column("payload", sa.JSON()),
    )
    at = datetime.now(timezone.utc)
    rows = bind.execute(
        sa.select(devices.c.id, devices.c.payload).where(devices.c.payload.is_not(None))
    ).mappings()
    for row in rows:
        payload = dict(row["payload"] or {})
        payload["id"] = row["id"]
        bind.execute(created["driver_bindings"].insert().values(**_binding(payload, at)))


def downgrade():
    # Runtime rollback normally keeps these additive tables and starts the
    # previous image. An explicit downgrade is reserved for disposable QA.
    for table in reversed(list(tables().values())):
        table.drop(op.get_bind())
