"""Settings, persistent update requests and per-user notification receipts."""
from alembic import op
import sqlalchemy as sa
from app.system_schema_v1 import define_tables

revision = "0007_settings_updates"
down_revision = "0006_collection_automation"
branch_labels = depends_on = None


def tables():
    meta = sa.MetaData()
    sa.Table("app_users", meta, sa.Column("id", sa.String(64), primary_key=True))
    return define_tables(meta)


def upgrade():
    for table in tables().values():
        table.create(op.get_bind())


def downgrade():
    for table in reversed(list(tables().values())):
        table.drop(op.get_bind())
