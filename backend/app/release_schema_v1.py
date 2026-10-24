"""Additive S11 release-decision and rollout-evidence persistence.

The signed payload is stored verbatim as JSON. Runtime readers verify the
signature again before a row can influence the public support catalog, so a
plain database write cannot promote a driver profile.
"""
import sqlalchemy as sa


def define_tables(meta):
    decisions = sa.Table(
        "driver_release_decisions",
        meta,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_revision", sa.String(40), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("release_status", sa.String(24)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("signer_key_id", sa.String(120), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('publish', 'withdraw')",
            name="ck_driver_release_decision_action",
        ),
        sa.CheckConstraint(
            "release_status IS NULL OR release_status IN ('candidate', 'supported')",
            name="ck_driver_release_decision_status",
        ),
        sa.CheckConstraint(
            "profile_revision >= 1 AND expires_at > signed_at",
            name="ck_driver_release_decision_window",
        ),
        sa.CheckConstraint(
            "length(source_revision) = 40 AND length(payload_sha256) = 64",
            name="ck_driver_release_decision_digests",
        ),
    )
    sa.Index(
        "ix_driver_release_decision_current",
        decisions.c.profile_id,
        decisions.c.profile_revision,
        decisions.c.source_revision,
        decisions.c.signed_at,
    )

    rollout = sa.Table(
        "driver_rollout_observations",
        meta,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("decision_id", sa.String(64), nullable=False),
        sa.Column("source_revision", sa.String(40), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("signer_key_id", sa.String(120), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "stage IN ('canary', 'pilot', 'general')",
            name="ck_driver_rollout_observation_stage",
        ),
        sa.CheckConstraint(
            "profile_revision >= 1 AND recorded_at >= observed_at",
            name="ck_driver_rollout_observation_window",
        ),
        sa.CheckConstraint(
            "length(source_revision) = 40 AND length(payload_sha256) = 64",
            name="ck_driver_rollout_observation_digests",
        ),
    )
    sa.Index(
        "ix_driver_rollout_observation_decision",
        rollout.c.decision_id,
        rollout.c.recorded_at,
    )
    return {
        "driver_release_decisions": decisions,
        "driver_rollout_observations": rollout,
    }
