"""Add durable identity for the local automatic probe agent.

Revision ID: 0009_probe_auto_enroll
Revises: 0008_network_probe
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_probe_auto_enroll"
down_revision = "0008_network_probe"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("network_probe_agents", sa.Column("bootstrap_id", sa.String(64)))
    op.create_index("ux_network_probe_agent_bootstrap_id", "network_probe_agents", ["bootstrap_id"], unique=True)


def downgrade():
    op.drop_index("ux_network_probe_agent_bootstrap_id", table_name="network_probe_agents")
    op.drop_column("network_probe_agents", "bootstrap_id")
