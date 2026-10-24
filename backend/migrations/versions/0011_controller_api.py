"""Add isolated controller API registrations and device bindings.

Revision ID: 0011_controller_api
Revises: 0010_driver_acceptance

This additive migration does not read or rewrite device, SSH, SNMP, telemetry,
job, inventory, probe, or acceptance data.
"""
from alembic import op
import sqlalchemy as sa

from app.controller_schema_v1 import define_tables


revision = "0011_controller_api"
down_revision = "0010_driver_acceptance"
branch_labels = None
depends_on = None


def tables():
    meta = sa.MetaData()
    sa.Table("devices", meta, sa.Column("id", sa.String(64), primary_key=True))
    return define_tables(meta)


def upgrade():
    for table in tables().values():
        table.create(op.get_bind())


def downgrade():
    for table in reversed(list(tables().values())):
        table.drop(op.get_bind())
