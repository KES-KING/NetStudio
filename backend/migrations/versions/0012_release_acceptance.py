"""Add signed release decisions and rollout observations.

Revision ID: 0012_release_acceptance
Revises: 0011_controller_api

The migration is additive. Existing devices, credentials, host keys,
acceptance records, observations, jobs and controller bindings are untouched.
"""
from alembic import op
import sqlalchemy as sa

from app.release_schema_v1 import define_tables


revision = "0012_release_acceptance"
down_revision = "0011_controller_api"
branch_labels = None
depends_on = None


def tables():
    return define_tables(sa.MetaData())


def upgrade():
    bind = op.get_bind()
    for table in tables().values():
        table.create(bind)


def downgrade():
    # Normal rollback runs the previous application image while preserving
    # these additive records. Explicit downgrade is for disposable QA only.
    for table in reversed(list(tables().values())):
        table.drop(op.get_bind())
