"""Weather alerts (OpenWeather Alerts API): stored alerts per AOI, notification inbox, per-AOI refresh state.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-10
"""
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB
TS = sa.DateTime(timezone=True)
NOW = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "weather_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("aoi_id", sa.Uuid(), sa.ForeignKey("areas_of_interest.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(24), nullable=False, server_default="openweather"),
        sa.Column("source_alert_id", sa.String(200), nullable=False),
        sa.Column("source", sa.String(40)),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("tags", JSONB(), nullable=False, server_default="[]"),
        sa.Column("severity", sa.String(10), nullable=False, server_default="unknown"),
        sa.Column("urgency", sa.String(10), nullable=False, server_default="unknown"),
        sa.Column("certainty", sa.String(10), nullable=False, server_default="unknown"),
        sa.Column("industry", JSONB(), nullable=False, server_default="[]"),
        sa.Column("geometry", Geometry("GEOMETRY", srid=4326, spatial_index=False)),
        sa.Column("start_time", TS),
        sa.Column("end_time", TS),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("change_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id_synthesized", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("first_seen_at", TS, nullable=False, server_default=NOW),
        sa.Column("last_seen_at", TS, nullable=False, server_default=NOW),
        sa.Column("last_checked_at", TS, nullable=False, server_default=NOW),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
        sa.Column("notified_hash", sa.String(64)),
        sa.Column("notified_at", TS),
        sa.UniqueConstraint("aoi_id", "provider", "source_alert_id", name="uq_weather_alert_source"),
        sa.CheckConstraint("status in ('active','expired')", name="ck_weather_alerts_status"),
    )
    op.create_index("ix_weather_alerts_aoi_id", "weather_alerts", ["aoi_id"])
    op.create_index("ix_weather_alerts_status", "weather_alerts", ["status", "severity"])
    op.create_index("ix_weather_alerts_geometry", "weather_alerts", ["geometry"], postgresql_using="gist")

    op.create_table(
        "weather_alert_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("alert_id", sa.Uuid(), sa.ForeignKey("weather_alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aoi_id", sa.Uuid(), sa.ForeignKey("areas_of_interest.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("changes", JSONB(), nullable=False, server_default="[]"),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("read_at", TS),
        sa.CheckConstraint("kind in ('new','updated')", name="ck_weather_events_kind"),
    )
    op.create_index("ix_weather_alert_events_alert_id", "weather_alert_events", ["alert_id"])
    op.create_index("ix_weather_alert_events_aoi_id", "weather_alert_events", ["aoi_id"])

    op.create_table(
        "weather_aoi_state",
        sa.Column("aoi_id", sa.Uuid(), sa.ForeignKey("areas_of_interest.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("last_checked_at", TS),
        sa.Column("last_status", sa.String(20)),
        sa.Column("last_error", sa.Text()),
        sa.Column("last_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("monitoring", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    for t in ("weather_aoi_state", "weather_alert_events", "weather_alerts"):
        op.drop_table(t)
