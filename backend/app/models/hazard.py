"""Live hazard alerts (earthquake / fire hotspots / storm) near a saved AOI, derived from an external feed.

These are third-party observations matched to an AOI by distance; they are NOT satellite-derived change polygons from GeoTrace analyses."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class HazardAlert(Base):
    __tablename__ = "hazard_alerts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    aoi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("areas_of_interest.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)  # earthquake | fire | storm
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(24), nullable=False, default="osiris", server_default="osiris")
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default="low")  # heuristic tier derived from the figures in `details`
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)  # nearest point of the AOI to the event
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active", server_default="active")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("aoi_id", "kind", "external_id", name="uq_hazard_alert_source"),
        CheckConstraint("status in ('active','expired')", name="ck_hazard_alerts_status"),
        CheckConstraint("kind in ('earthquake','fire','storm')", name="ck_hazard_alerts_kind"),
        Index("ix_hazard_alerts_aoi_id", "aoi_id"),
        Index("ix_hazard_alerts_status_seen", "status", "last_seen_at"),
    )
