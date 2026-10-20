"""Add durable collection, host-key discovery and separate telemetry histories.

Existing inventory, SSH secrets, host keys and measurements are not rewritten.
"""
from alembic import op
import sqlalchemy as sa

from app.automation_schema_v1 import define_tables

revision = "0006_collection_automation"
down_revision = "0005_topology_workspace"
branch_labels = None
depends_on = None


def tables():
    meta = sa.MetaData()
    for name, kind in (("devices", sa.String(64)), ("app_users", sa.String(64)), ("jobs", sa.Uuid())):
        sa.Table(name, meta, sa.Column("id", kind, primary_key=True))
    return define_tables(meta)


def upgrade():
    for table in tables().values():
        table.create(op.get_bind())


def downgrade():
    # Roll back the application by stopping the worker, not by dropping history.
    # An explicit migration downgrade removes only the new automation tables.
    for table in reversed(list(tables().values())):
        table.drop(op.get_bind())
