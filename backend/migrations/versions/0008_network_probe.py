"""Add VLAN-aware active ARP probe persistence.

Revision ID: 0008_network_probe
Revises: 0007_settings_updates
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_network_probe"
down_revision = "0007_settings_updates"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("network_probe_enrollments",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("name", sa.String(160), nullable=False),
        sa.Column("site", sa.String(160), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_network_probe_enrollment_expiry", "network_probe_enrollments", ["expires_at"])
    op.create_table("network_probe_agents",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("name", sa.String(160), nullable=False),
        sa.Column("site", sa.String(160), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("interfaces", sa.JSON(), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False), sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_network_probe_agent_site", "network_probe_agents", ["site"])
    op.create_index("ix_network_probe_agent_seen", "network_probe_agents", ["last_seen_at"])
    op.create_table("network_probe_scopes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("network_probe_agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site", sa.String(160), nullable=False), sa.Column("vlan", sa.Integer(), nullable=False),
        sa.Column("vrf", sa.String(160)), sa.Column("vrf_known", sa.Boolean(), nullable=False),
        sa.Column("interface_name", sa.String(160), nullable=False), sa.Column("source_ip", sa.String(45), nullable=False),
        sa.Column("source_cidr", sa.String(64), nullable=False), sa.Column("target_cidrs", sa.JSON(), nullable=False),
        sa.Column("proposal_id", sa.String(64), nullable=False), sa.Column("evidence_fingerprint", sa.String(64), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_started_at", sa.DateTime(timezone=True)), sa.Column("last_completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_manual_at", sa.DateTime(timezone=True)), sa.Column("last_error", sa.String(160)),
        sa.Column("created_by", sa.String(64), nullable=False), sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_network_probe_scope_due", "network_probe_scopes", ["enabled", "status", "next_due_at"])
    op.create_index("ix_network_probe_scope_network", "network_probe_scopes", ["site", "vlan", "vrf"])
    op.create_table("network_probe_tasks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scope_id", sa.String(64), sa.ForeignKey("network_probe_scopes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("network_probe_agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False), sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("requested_by", sa.String(160), nullable=False), sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False), sa.Column("result", sa.JSON()),
        sa.Column("lease_token_hash", sa.String(64)), sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempt", sa.Integer(), nullable=False), sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)))
    op.create_index("ix_network_probe_task_claim", "network_probe_tasks", ["agent_id", "status", "queued_at"])
    op.create_index("ix_network_probe_task_scope", "network_probe_tasks", ["scope_id", "status"])
    op.create_table("network_probe_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("network_probe_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_id", sa.String(64), sa.ForeignKey("network_probe_scopes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False), sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("reply_count", sa.Integer(), nullable=False), sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("unknown_count", sa.Integer(), nullable=False), sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(160)), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_network_probe_run_scope_time", "network_probe_runs", ["scope_id", "completed_at"])
    op.create_table("network_probe_observations",
        sa.Column("scope_id", sa.String(64), sa.ForeignKey("network_probe_scopes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("mac", sa.String(17), primary_key=True), sa.Column("address", sa.String(45), primary_key=True),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("network_probe_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_network_probe_observation_expiry", "network_probe_observations", ["expires_at"])
    op.create_index("ix_network_probe_observation_mac", "network_probe_observations", ["mac"])


def downgrade():
    for table in ("network_probe_observations", "network_probe_runs", "network_probe_tasks", "network_probe_scopes", "network_probe_agents", "network_probe_enrollments"):
        op.drop_table(table)
