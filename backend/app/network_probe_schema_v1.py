"""Additive persistence schema for the isolated IPv4 ARP probe agent."""
from __future__ import annotations

import sqlalchemy as sa


def define_tables(metadata):
    enrollments = sa.Table("network_probe_enrollments", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("site", sa.String(160), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    sa.Index("ix_network_probe_enrollment_expiry", enrollments.c.expires_at)

    agents = sa.Table("network_probe_agents", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("site", sa.String(160), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("interfaces", sa.JSON(), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)))
    sa.Index("ix_network_probe_agent_site", agents.c.site)
    sa.Index("ix_network_probe_agent_seen", agents.c.last_seen_at)

    scopes = sa.Table("network_probe_scopes", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("network_probe_agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site", sa.String(160), nullable=False),
        sa.Column("vlan", sa.Integer(), nullable=False),
        sa.Column("vrf", sa.String(160)),
        sa.Column("vrf_known", sa.Boolean(), nullable=False),
        sa.Column("interface_name", sa.String(160), nullable=False),
        sa.Column("source_ip", sa.String(45), nullable=False),
        sa.Column("source_cidr", sa.String(64), nullable=False),
        sa.Column("target_cidrs", sa.JSON(), nullable=False),
        sa.Column("proposal_id", sa.String(64), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(64), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_started_at", sa.DateTime(timezone=True)),
        sa.Column("last_completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_manual_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(160)),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    sa.Index("ix_network_probe_scope_due", scopes.c.enabled, scopes.c.status, scopes.c.next_due_at)
    sa.Index("ix_network_probe_scope_network", scopes.c.site, scopes.c.vlan, scopes.c.vrf)

    tasks = sa.Table("network_probe_tasks", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scope_id", sa.String(64), sa.ForeignKey("network_probe_scopes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("network_probe_agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("requested_by", sa.String(160), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("lease_token_hash", sa.String(64)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)))
    sa.Index("ix_network_probe_task_claim", tasks.c.agent_id, tasks.c.status, tasks.c.queued_at)
    sa.Index("ix_network_probe_task_scope", tasks.c.scope_id, tasks.c.status)

    runs = sa.Table("network_probe_runs", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("network_probe_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_id", sa.String(64), sa.ForeignKey("network_probe_scopes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("reply_count", sa.Integer(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("unknown_count", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(160)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False))
    sa.Index("ix_network_probe_run_scope_time", runs.c.scope_id, runs.c.completed_at)

    observations = sa.Table("network_probe_observations", metadata,
        sa.Column("scope_id", sa.String(64), sa.ForeignKey("network_probe_scopes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("mac", sa.String(17), primary_key=True),
        sa.Column("address", sa.String(45), primary_key=True),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("network_probe_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    sa.Index("ix_network_probe_observation_expiry", observations.c.expires_at)
    sa.Index("ix_network_probe_observation_mac", observations.c.mac)

    return {"network_probe_enrollments": enrollments, "network_probe_agents": agents,
        "network_probe_scopes": scopes, "network_probe_tasks": tasks,
        "network_probe_runs": runs, "network_probe_observations": observations}
