"""Live hazard alerts matched to AOIs.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-10
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None
TS = sa.DateTime(timezone=True)
NOW = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "hazard_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("aoi_id", sa.Uuid(), sa.ForeignKey("areas_of_interest.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(24), nullable=False, server_default="osiris"),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False, server_default="low"),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column("occurred_at", TS),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.Column("first_seen_at", TS, nullable=False, server_default=NOW),
        sa.Column("last_seen_at", TS, nullable=False, server_default=NOW),
        sa.Column("read_at", TS),
        sa.UniqueConstraint("aoi_id", "kind", "external_id", name="uq_hazard_alert_source"),
        sa.CheckConstraint("status in ('active','expired')", name="ck_hazard_alerts_status"),
        sa.CheckConstraint("kind in ('earthquake','fire','storm')", name="ck_hazard_alerts_kind"),
    )
    op.create_index("ix_hazard_alerts_aoi_id", "hazard_alerts", ["aoi_id"])
    op.create_index("ix_hazard_alerts_status_seen", "hazard_alerts", ["status", "last_seen_at"])


def downgrade() -> None:
    op.drop_table("hazard_alerts")
