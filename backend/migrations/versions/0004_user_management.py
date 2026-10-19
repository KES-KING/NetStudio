"""User profiles, avatars, canonical roles and structured, indexed audit history."""
from alembic import op
import sqlalchemy as sa

revision = "0004_user_management"
down_revision = "0003_enterprise_console"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("app_users", sa.Column("display_name", sa.String(100), nullable=False, server_default=""))
    op.add_column("app_users", sa.Column("created_at", sa.DateTime(timezone=True)))
    op.add_column("app_users", sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.add_column("app_users", sa.Column("avatar_version", sa.String(36)))
    op.create_index("ix_app_sessions_user", "app_sessions", ["user_id"])
    op.create_table("user_avatars",
        sa.Column("user_id", sa.String(64), sa.ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("png", sa.LargeBinary(), nullable=False))
    users = sa.table("app_users", sa.column("id"), sa.column("username"), sa.column("display_name"),
        sa.column("roles", sa.JSON()), sa.column("enabled", sa.Boolean()))
    conn = op.get_bind()
    for row in conn.execute(sa.select(users.c.id, users.c.username, users.c.roles)).mappings():
        roles = set(row["roles"] or [])
        role = "superadmin" if roles & {"admin", "superadmin"} else "engineer" if roles & {"operator", "engineer"} else "viewer"
        values = {"roles": [role], "display_name": row["username"][:100]}
        if not roles or roles - {"admin", "operator", "viewer", "engineer", "superadmin"}:
            values["enabled"] = False
        conn.execute(users.update().where(users.c.id == row["id"]).values(**values))
    for column in (
        sa.Column("username", sa.String(160)), sa.Column("roles", sa.JSON()),
        sa.Column("target_type", sa.String(40)), sa.Column("target_id", sa.String(160)),
        sa.Column("request_id", sa.String(36)), sa.Column("method", sa.String(10)),
        sa.Column("route", sa.String(200)), sa.Column("remote_address", sa.String(100)),
        sa.Column("user_agent", sa.String(256)), sa.Column("status_code", sa.Integer()),
        sa.Column("duration_ms", sa.Integer()), sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
    ):
        op.add_column("audit_events", column)
    for name, columns in (
        ("ix_audit_cursor", ["occurred_at", "id"]),
        ("ix_audit_actor_time", ["user_id", "occurred_at", "id"]),
        ("ix_audit_event_time", ["event", "occurred_at", "id"]),
        ("ix_audit_target_time", ["target_id", "occurred_at", "id"]),
    ):
        op.create_index(name, "audit_events", columns)


def downgrade():
    # Profile/audit data must not be silently discarded during a code rollback.
    raise RuntimeError("User-management migration is forward-only; restore an explicitly approved backup to roll back.")
