from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base

# Lifecycle (PRD FR-22). Terminal states: completed, failed, cancelled.
ANALYSIS_STATUSES = (
    "queued", "validating", "acquiring_imagery", "preprocessing", "detecting_changes",
    "polygonizing", "evaluating_alerts", "exporting", "completed", "failed", "cancelled",
)
ACTIVE_STATUSES = tuple(s for s in ANALYSIS_STATUSES if s not in ("completed", "failed", "cancelled"))
TERMINAL_STATUSES = ("completed", "failed", "cancelled")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    aoi_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("areas_of_interest.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    input_type: Mapped[str] = mapped_column(String(12), nullable=False)  # upload | sentinel | demo

    before_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("imagery_assets.id", ondelete="SET NULL"), nullable=True)
    after_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("imagery_assets.id", ondelete="SET NULL"), nullable=True)
    before_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    after_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", server_default="queued")
    stage_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    error: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Queue claim (Postgres-as-queue: SELECT ... FOR UPDATE SKIP LOCKED)
    locked_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Effective configuration and what the pipeline actually did
    config: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    acquisition_params: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    method: Mapped[str | None] = mapped_column(String(24), nullable=True)
    method_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    warnings: Mapped[List[Dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    validation: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    processing: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)  # detection details, timings, grid, etc.
    artifacts: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)  # name -> storage-relative path
    bounds_wgs84: Mapped[List[float] | None] = mapped_column(JSONB, nullable=True)  # [minx, miny, maxx, maxy] of the analysed grid
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_analysis_jobs_status_created", "status", "created_at"),)


class AnalysisEvent(Base):
    """Append-only progress log (drives the job timeline and server-sent events)."""

    __tablename__ = "analysis_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    message: Mapped[str | None] = mapped_column(String(300), nullable=True)


class AnalysisExport(Base):
    __tablename__ = "analysis_exports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    format: Mapped[str] = mapped_column(String(12), nullable=False)  # geojson | gpkg | csv | report_json
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="all")  # all | filtered | selected | aoi
    filters: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="completed")
    feature_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
