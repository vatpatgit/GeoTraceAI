from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class WeatherAlert(Base):
    """A provider weather alert affecting a saved AOI. Provider-supplied geometry is stored as-is and is NOT a satellite-derived change polygon."""

    __tablename__ = "weather_alerts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    aoi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("areas_of_interest.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(24), nullable=False, default="openweather", server_default="openweather")
    source_alert_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default="unknown")
    urgency: Mapped[str] = mapped_column(String(10), nullable=False, default="unknown")
    certainty: Mapped[str] = mapped_column(String(10), nullable=False, default="unknown")
    industry: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    geometry = mapped_column(Geometry("GEOMETRY", srid=4326, spatial_index=False), nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active", server_default="active")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    change_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    id_synthesized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    notified_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("aoi_id", "provider", "source_alert_id", name="uq_weather_alert_source"),
        CheckConstraint("status in ('active','expired')", name="ck_weather_alerts_status"),
        Index("ix_weather_alerts_geometry", "geometry", postgresql_using="gist"),
        Index("ix_weather_alerts_status", "status", "severity"),
    )


class WeatherAlertEvent(Base):
    """In-app notification inbox entry: created only when an alert is NEW or MATERIALLY CHANGED, never for unchanged re-fetches."""

    __tablename__ = "weather_alert_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("weather_alerts.id", ondelete="CASCADE"), nullable=False, index=True)
    aoi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("areas_of_interest.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # new | updated
    changes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (CheckConstraint("kind in ('new','updated')", name="ck_weather_events_kind"),)


class WeatherAoiState(Base):
    """Per-AOI refresh bookkeeping (rate guard, last outcome, opt-in scheduled monitoring)."""

    __tablename__ = "weather_aoi_state"

    aoi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("areas_of_interest.id", ondelete="CASCADE"), primary_key=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ok | error
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    monitoring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
