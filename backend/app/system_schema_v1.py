"""Frozen additive 0007 schema. No installation or network work on import."""
import sqlalchemy as sa


def define_tables(meta):
    tables = {
        "system_update": sa.Table("system_update", meta,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("payload", sa.JSON(), nullable=False)),
        "update_runs": sa.Table("system_update_runs", meta,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("revision", sa.String(40), nullable=False),
            sa.Column("status", sa.String(40), nullable=False),
            sa.Column("actor", sa.String(160), nullable=False),
            sa.Column("automatic", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("error_code", sa.String(100))),
        "runtime_presence": sa.Table("system_runtime_presence", meta,
            sa.Column("id", sa.String(160), primary_key=True),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("active_sessions", sa.Integer(), nullable=False),
            sa.Column("active_mutations", sa.Integer(), nullable=False, server_default="0")),
        "notification_reads": sa.Table("notification_reads", meta,
            sa.Column("user_id", sa.String(64), sa.ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("event_id", sa.String(64), nullable=False)),
    }
    sa.Index("ix_system_update_runs_time", tables["update_runs"].c.created_at)
    return tables
