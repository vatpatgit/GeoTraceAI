"""ChangeFeature: one detected change polygon, always tied to the analysis (and imagery) that produced it.

This replaces the legacy region-centric ``ChangeEvent`` (which required a made-up ``confidence`` and carried no provenance).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base

REVIEW_STATUSES = ("unreviewed", "confirmed", "rejected")
SEVERITIES = ("low", "medium", "high", "critical")


class ChangeFeature(Base):
    __tablename__ = "change_features"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based rank by area within the analysis
    geometry = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False)
    centroid = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    point_on_surface = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)

    category: Mapped[str] = mapped_column(String(40), nullable=False)
    category_basis: Mapped[str] = mapped_column(String(24), nullable=False)  # observed_difference | spectral_index | model_inferred
    area_m2: Mapped[float] = mapped_column(Float, nullable=False)
    perimeter_m: Mapped[float] = mapped_column(Float, nullable=False)
    pixel_count: Mapped[int] = mapped_column(Integer, nullable=False)
    magnitude: Mapped[float] = mapped_column(Float, nullable=False)  # 0..1, method-specific meaning (see analysis.processing)
    magnitude_max: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # only when the method yields one (uncalibrated)
    delta_ndvi: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    severity_reasons: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    distance_to_boundary_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    nearest_region_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("regions.id", ondelete="SET NULL"), nullable=True)

    review_status: Mapped[str] = mapped_column(String(12), nullable=False, default="unreviewed", server_default="unreviewed")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    properties: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("analysis_id", "seq", name="uq_change_features_analysis_seq"),
        Index("ix_change_features_geometry", "geometry", postgresql_using="gist"),
        Index("ix_change_features_centroid", "centroid", postgresql_using="gist"),
        Index("ix_change_features_analysis_severity", "analysis_id", "severity"),
        Index("ix_change_features_analysis_category", "analysis_id", "category"),
        Index("ix_change_features_analysis_area", "analysis_id", "area_m2"),
    )
