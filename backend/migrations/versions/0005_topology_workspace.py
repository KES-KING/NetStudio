"""Personal topology workspaces; observations remain in versioned telemetry JSON."""
from alembic import op
import sqlalchemy as sa

revision = "0005_topology_workspace"
down_revision = "0004_user_management"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("topology_boards",
        sa.Column("user_id", sa.String(64), sa.ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    raise RuntimeError("Topology migration is forward-only; preserve personal layouts before an approved restore.")
