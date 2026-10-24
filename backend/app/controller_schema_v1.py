"""Frozen S08 controller/API registration, secret and device binding schema."""
import sqlalchemy as sa


def define_tables(meta):
    tables = {}
    tables["api_controllers"] = sa.Table(
        "api_controllers", meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("vendor", sa.String(32), nullable=False),
        sa.Column("site", sa.String(160), nullable=False),
        sa.Column("endpoint_kind", sa.String(16), nullable=False),
        sa.Column("address", sa.String(64)),
        sa.Column("port", sa.Integer()),
        sa.Column("cloud_region", sa.String(24)),
        sa.Column("ca_pem", sa.Text()),
        sa.Column("external_scope_id", sa.String(160), nullable=False),
        sa.Column("external_site_id", sa.String(160), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(160), nullable=False),
        sa.UniqueConstraint("site", "name", name="uq_api_controller_site_name"),
    )
    sa.Index("ix_api_controllers_site", tables["api_controllers"].c.site)
    tables["api_controller_secrets"] = sa.Table(
        "api_controller_secrets", meta,
        sa.Column("controller_id", sa.String(36), sa.ForeignKey("api_controllers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("auth_kind", sa.String(24), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    tables["device_controller_bindings"] = sa.Table(
        "device_controller_bindings", meta,
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("controller_id", sa.String(36), sa.ForeignKey("api_controllers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("controller_vendor", sa.String(32), nullable=False),
        sa.Column("site", sa.String(160), nullable=False),
        sa.Column("external_device_id", sa.String(160), nullable=False),
        sa.Column("external_site_id", sa.String(160), nullable=False),
        sa.Column("binding_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(160), nullable=False),
        sa.UniqueConstraint("controller_id", "external_device_id", name="uq_controller_external_device"),
        sa.UniqueConstraint(
            "site", "controller_vendor", "external_device_id",
            name="uq_site_vendor_external_device",
        ),
    )
    sa.Index("ix_device_controller_controller", tables["device_controller_bindings"].c.controller_id)
    return tables
