"""Frozen 0006 schema definitions, shared by migration and isolated SQLite tests.

Do not alter these definitions for later migrations: add a new schema revision.
No connection, secret, device IO or data mutation occurs on import.
"""
import sqlalchemy as sa


def define_tables(meta):
    device = lambda: sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), primary_key=True)
    tables = {}
    tables["polling"] = sa.Table("device_polling", meta,
        device(), sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused_reason", sa.String(120)),
        sa.Column("updated_by", sa.String(160), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    sa.Index("ix_device_polling_due", tables["polling"].c.due_at)
    tables["collection_groups"] = sa.Table("device_collection_groups", meta,
        device(), sa.Column("group_name", sa.String(24), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False))
    tables["collection_history"] = sa.Table("device_collection_history", meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("group_name", sa.String(24), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False))
    sa.Index("ix_collection_history_time", tables["collection_history"].c.device_id, tables["collection_history"].c.observed_at)
    tables["latest_telemetry"] = sa.Table("device_latest_telemetry", meta,
        device(), sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False))
    tables["metric_samples"] = sa.Table("device_metric_samples", meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("group_name", sa.String(24), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False))
    sa.Index("ix_metric_samples_time", tables["metric_samples"].c.device_id, tables["metric_samples"].c.observed_at)
    sa.Index("ix_metric_samples_retention", tables["metric_samples"].c.observed_at)
    tables["metric_rollups"] = sa.Table("device_metric_rollups", meta,
        device(), sa.Column("group_name", sa.String(24), primary_key=True),
        sa.Column("bucket_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False))
    sa.Index("ix_metric_rollups_bucket", tables["metric_rollups"].c.bucket_at)
    tables["host_candidates"] = sa.Table("ssh_host_candidates", meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_revision", sa.Integer(), nullable=False),
        sa.Column("target_signature", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("public_key", sa.Text()), sa.Column("fingerprint", sa.String(160)),
        sa.Column("profile", sa.String(40)), sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.false()))
    sa.Index("ix_host_candidates_device_time", tables["host_candidates"].c.device_id, tables["host_candidates"].c.created_at)
    tables["ssh_cache"] = sa.Table("device_ssh_cache", meta,
        device(), sa.Column("target_signature", sa.String(64), nullable=False),
        sa.Column("profile", sa.String(40), nullable=False),
        sa.Column("negotiated", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    tables["protocol_secrets"] = sa.Table("device_protocol_secrets", meta,
        device(), sa.Column("protocol", sa.String(20), primary_key=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False))
    tables["job_contexts"] = sa.Table("collector_job_contexts", meta,
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id"), primary_key=True),
        sa.Column("actor_kind", sa.String(20), nullable=False),
        sa.Column("session_hash", sa.String(64)),
        sa.Column("connection_revision", sa.Integer(), nullable=False),
        sa.Column("target_signature", sa.String(64), nullable=False),
        sa.Column("groups", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.Integer()),
        sa.Column("candidate_id", sa.String(36)))
    tables["capabilities"] = sa.Table("device_command_capabilities", meta,
        device(), sa.Column("command_id", sa.String(120), primary_key=True),
        sa.Column("revision_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False))
    tables["worker_heartbeats"] = sa.Table("collector_worker_heartbeats", meta,
        sa.Column("id", sa.String(160), primary_key=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("running", sa.Integer(), nullable=False))
    return tables
