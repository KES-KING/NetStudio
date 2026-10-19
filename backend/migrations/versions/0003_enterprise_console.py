"""Persistent management console. Existing inventory/jobs remain intact."""
from alembic import op
import sqlalchemy as sa

revision = "0003_enterprise_console"
down_revision = "0002_job_claim_and_observations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("devices", sa.Column("payload", sa.JSON()))
    op.create_table("app_users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(160), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False), sa.Column("sites", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("app_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("app_users.id"), nullable=False),
        sa.Column("csrf", sa.String(128), nullable=False), sa.Column("expires_at", sa.Float(), nullable=False))
    op.create_table("device_secrets",
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), primary_key=True),
        sa.Column("key_id", sa.String(80), nullable=False), sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False))
    op.create_table("device_host_keys",
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), primary_key=True),
        sa.Column("public_key", sa.Text(), nullable=False), sa.Column("fingerprint", sa.String(160), nullable=False))
    op.create_table("device_telemetry",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False), sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("device_id", "observed_at", name="uq_device_telemetry_time"))
    op.create_index("ix_device_telemetry_time", "device_telemetry", ["device_id", "observed_at"])
    op.create_table("audit_events",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("user_id", sa.String(160), nullable=False),
        sa.Column("device_id", sa.String(64)), sa.Column("event", sa.String(80), nullable=False),
        sa.Column("outcome", sa.String(100), nullable=False), sa.Column("session_id", sa.String(64)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_audit_events_time", "audit_events", ["occurred_at"])


def downgrade():
    for table in ("audit_events", "device_telemetry", "device_host_keys", "device_secrets", "app_sessions", "app_users"):
        op.drop_table(table)
    op.drop_column("devices", "payload")
