"""Alert rules and incidents.

Replaces the legacy ``AlertConfig``/``AlertHistory`` (confidence-threshold only, no deduplication, evaluated inside an
admin-only POST). Incidents are produced when an analysis completes and are unique per (rule, feature).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base

INCIDENT_STATUSES = ("open", "acknowledged", "resolved")


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    # Scope
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    region_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("regions.id", ondelete="CASCADE"), nullable=True)
    aoi_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("areas_of_interest.id", ondelete="CASCADE"), nullable=True)
    region_relation: Mapped[str] = mapped_column(String(16), nullable=False, default="intersects", server_default="intersects")
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)  # for relation == within_distance

    # Criteria (all must hold; null/empty = not constrained)
    categories: Mapped[List[str] | None] = mapped_column(JSONB, nullable=True)
    min_area_m2: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    min_severity: Mapped[str] = mapped_column(String(10), nullable=False, default="low", server_default="low")
    min_magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Deduplication across analyses (the (rule, feature) uniqueness always applies)
    dedup_mode: Mapped[str] = mapped_column(String(12), nullable=False, default="spatial", server_default="spatial")  # none | spatial
    dedup_window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30, server_default="30")
    dedup_overlap: Mapped[float] = mapped_column(Float, nullable=False, default=0.5, server_default="0.5")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AlertIncident(Base):
    __tablename__ = "alert_incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False)
    feature_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("change_features.id", ondelete="CASCADE"), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(14), nullable=False, default="open", server_default="open")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("rule_id", "feature_id", name="uq_alert_incident_rule_feature"),
        Index("ix_alert_incidents_status_severity", "status", "severity"),
        Index("ix_alert_incidents_created", "created_at"),
        Index("ix_alert_incidents_analysis", "analysis_id"),
    )
