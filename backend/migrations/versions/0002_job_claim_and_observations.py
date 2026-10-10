"""Add queue claim metadata and observation snapshots.

Revision ID: 0002_job_claim_and_observations
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_job_claim_and_observations"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("priority", sa.Integer(), nullable=False, server_default="100"))
    op.add_column("jobs", sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("jobs", sa.Column("lease_owner", sa.String(160)))
    op.add_column("jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column("jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
    op.add_column("jobs", sa.Column("idempotency_key", sa.String(255)))
    op.add_column("jobs", sa.Column("payload_ref", sa.String(255)))
    op.add_column("jobs", sa.Column("result_code", sa.String(120)))
    op.execute(sa.text("UPDATE jobs SET next_run_at = created_at WHERE next_run_at IS NULL"))
    op.alter_column("jobs", "next_run_at", nullable=False)
    op.create_index("ix_jobs_queue_claim", "jobs", ["status", "next_run_at", "priority"])
    op.create_unique_constraint("uq_jobs_idempotency_key", "jobs", ["idempotency_key"])

    op.create_table(
        "observation_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("quality", sa.String(30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(255)),
    )
    op.create_index("ix_observation_snapshots_device_time", "observation_snapshots", ["device_id", "observed_at"])


def downgrade() -> None:
    op.drop_index("ix_observation_snapshots_device_time", table_name="observation_snapshots")
    op.drop_table("observation_snapshots")
    op.drop_constraint("uq_jobs_idempotency_key", "jobs", type_="unique")
    op.drop_index("ix_jobs_queue_claim", table_name="jobs")
    op.drop_column("jobs", "result_code")
    op.drop_column("jobs", "payload_ref")
    op.drop_column("jobs", "idempotency_key")
    op.drop_column("jobs", "heartbeat_at")
    op.drop_column("jobs", "lease_expires_at")
    op.drop_column("jobs", "lease_owner")
    op.drop_column("jobs", "max_attempts")
    op.drop_column("jobs", "attempt")
    op.drop_column("jobs", "next_run_at")
    op.drop_column("jobs", "priority")

