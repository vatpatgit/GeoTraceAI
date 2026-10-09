"""Baseline: the TerraTrack schema as created by ``create_all`` + ``init_postgis.sql``.

Existing databases created by the old startup code are *stamped* at this revision (see ``app.migrate``) instead of
re-running it; fresh databases execute it.

Revision ID: 0001
Revises:
Create Date: 2026-10-09
"""
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "regions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("geometry", Geometry("POLYGON", srid=4326, spatial_index=False), nullable=False),
        sa.Column("center_lat", sa.Float(), nullable=False),
        sa.Column("center_lng", sa.Float(), nullable=False),
        sa.Column("area_km2", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("metadata_json", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_regions_geometry", "regions", ["geometry"], postgresql_using="gist")
    op.create_table(
        "change_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("region_id", sa.Uuid(), sa.ForeignKey("regions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("change_type", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("area_affected_km2", sa.Float(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("geometry", Geometry("POLYGON", srid=4326, spatial_index=False)),
        sa.Column("source", sa.String(50), nullable=False, server_default="sentinel-2"),
        sa.Column("ndvi_before", sa.Float()),
        sa.Column("ndvi_after", sa.Float()),
        sa.Column("metadata_json", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_change_events_geometry", "change_events", ["geometry"], postgresql_using="gist")
    op.create_table(
        "alert_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("region_id", sa.Uuid(), sa.ForeignKey("regions.id", ondelete="CASCADE")),
        sa.Column("change_type", sa.String(30)),
        sa.Column("threshold", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "alert_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("alert_config_id", sa.Uuid(), sa.ForeignKey("alert_configs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("change_event_id", sa.Uuid(), sa.ForeignKey("change_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    for t in ("alert_history", "alert_configs", "change_events", "regions", "users"):
        op.drop_table(t)
