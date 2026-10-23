"""Frozen additive S02 compatibility persistence definitions.

The tables deliberately reference the existing device row instead of copying
inventory, credentials, host keys, telemetry, or job history.
"""
import sqlalchemy as sa


def define_tables(meta):
    bindings = sa.Table(
        "device_driver_bindings",
        meta,
        sa.Column(
            "device_id",
            sa.String(64),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("configured_profile_id", sa.String(64)),
        sa.Column("legacy_collector_id", sa.String(64)),
        sa.Column("resolved_profile_id", sa.String(64)),
        sa.Column("profile_revision", sa.Integer()),
        sa.Column("management_mode", sa.String(32), nullable=False),
        sa.Column("resolution_status", sa.String(40), nullable=False),
        sa.Column("resolution_confidence", sa.Float(), nullable=False),
        sa.Column("resolution_conflicts", sa.JSON(), nullable=False),
        sa.Column("identity_evidence", sa.JSON(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(160), nullable=False),
        sa.Column("binding_revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "management_mode IN ('standalone', 'controller_managed', "
            "'cloud_managed', 'local_managed', 'unknown')",
            name="ck_device_driver_binding_mode",
        ),
        sa.CheckConstraint(
            "resolution_status IN ('unresolved', 'matched', 'conflict', "
            "'unsupported', 'manual_resolution_required', "
            "'infrastructure_adapter', 'external')",
            name="ck_device_driver_binding_status",
        ),
        sa.CheckConstraint(
            "resolution_confidence >= 0 AND resolution_confidence <= 1",
            name="ck_device_driver_binding_confidence",
        ),
        sa.CheckConstraint(
            "profile_revision IS NULL OR profile_revision >= 1",
            name="ck_device_driver_binding_profile_revision",
        ),
        sa.CheckConstraint(
            "binding_revision >= 1",
            name="ck_device_driver_binding_revision",
        ),
    )
    sa.Index("ix_device_driver_binding_profile", bindings.c.resolved_profile_id)
    sa.Index("ix_device_driver_binding_status", bindings.c.resolution_status)

    capabilities = sa.Table(
        "device_capability_observations_v2",
        meta,
        sa.Column(
            "device_id",
            sa.String(64),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("profile_id", sa.String(64), primary_key=True),
        sa.Column("profile_revision", sa.Integer(), primary_key=True),
        sa.Column("transport", sa.String(16), primary_key=True),
        sa.Column("capability_id", sa.String(120), primary_key=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("reason_code", sa.String(120)),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_digest", sa.String(64)),
        sa.CheckConstraint(
            "transport IN ('ssh', 'snmp', 'api')",
            name="ck_device_capability_v2_transport",
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'partial', 'unknown', 'unsupported', "
            "'permission_denied', 'parse_error', 'timeout', 'error')",
            name="ck_device_capability_v2_status",
        ),
        sa.CheckConstraint(
            "profile_revision >= 1 AND expires_at > checked_at",
            name="ck_device_capability_v2_window",
        ),
        sa.CheckConstraint(
            "evidence_digest IS NULL OR length(evidence_digest) = 64",
            name="ck_device_capability_v2_digest",
        ),
    )
    sa.Index(
        "ix_device_capability_v2_expiry",
        capabilities.c.device_id,
        capabilities.c.expires_at,
    )

    acceptance = sa.Table(
        "driver_acceptance_records",
        meta,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_revision", sa.String(40), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("vendor", sa.String(120), nullable=False),
        sa.Column("model_family", sa.String(160), nullable=False),
        sa.Column("exact_model", sa.String(160), nullable=False),
        sa.Column("hardware_revision", sa.String(120), nullable=False),
        sa.Column("os_family", sa.String(120), nullable=False),
        sa.Column("os_version", sa.String(160), nullable=False),
        sa.Column("management_mode", sa.String(32), nullable=False),
        sa.Column("transport", sa.String(16), nullable=False),
        sa.Column("security_profile", sa.String(120), nullable=False),
        sa.Column("capability_id", sa.String(120), nullable=False),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("test_suite_revision", sa.String(80), nullable=False),
        sa.Column("validation_level", sa.String(40), nullable=False),
        sa.Column("result", sa.String(24), nullable=False),
        sa.Column("evidence_ref", sa.String(500), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_sanitized", sa.Boolean(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.String(160), nullable=False),
        sa.CheckConstraint(
            "management_mode IN ('standalone', 'controller_managed', "
            "'cloud_managed', 'local_managed', 'unknown')",
            name="ck_driver_acceptance_mode",
        ),
        sa.CheckConstraint(
            "transport IN ('ssh', 'snmp', 'api')",
            name="ck_driver_acceptance_transport",
        ),
        sa.CheckConstraint(
            "validation_level IN ('not_tested', 'unit_verified', "
            "'fixture_verified', 'transport_lab_validated', "
            "'physical_validated')",
            name="ck_driver_acceptance_validation",
        ),
        sa.CheckConstraint(
            "result IN ('pass', 'fail', 'blocked', 'withdrawn')",
            name="ck_driver_acceptance_result",
        ),
        sa.CheckConstraint(
            "profile_revision >= 1 AND expires_at > recorded_at "
            "AND recorded_at >= observed_at",
            name="ck_driver_acceptance_window",
        ),
        sa.CheckConstraint(
            "length(evidence_sha256) = 64",
            name="ck_driver_acceptance_digest",
        ),
        sa.CheckConstraint(
            "evidence_sanitized",
            name="ck_driver_acceptance_sanitized",
        ),
    )
    sa.Index(
        "ix_driver_acceptance_match",
        acceptance.c.profile_id,
        acceptance.c.profile_revision,
        acceptance.c.result,
        acceptance.c.expires_at,
    )

    return {
        "driver_bindings": bindings,
        "capability_observations_v2": capabilities,
        "driver_acceptance": acceptance,
    }
