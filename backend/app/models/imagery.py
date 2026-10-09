from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class ImageryAsset(Base):
    """A validated raster on disk (uploaded, or retrieved from a provider)."""

    __tablename__ = "imagery_assets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)  # upload | sentinel | synthetic
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)  # relative to STORAGE_DIR
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    band_count: Mapped[int] = mapped_column(Integer, nullable=False)
    dtype: Mapped[str] = mapped_column(String(16), nullable=False)
    crs_epsg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crs_wkt: Mapped[str | None] = mapped_column(String, nullable=True)
    pixel_size_m: Mapped[float] = mapped_column(Float, nullable=False)
    nodata: Mapped[float | None] = mapped_column(Float, nullable=True)
    footprint = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=False), nullable=False)
    band_descriptions: Mapped[List[str | None] | None] = mapped_column(JSONB, nullable=True)
    band_map: Mapped[Dict[str, int] | None] = mapped_column(JSONB, nullable=True)
    band_map_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    acquisition_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acquisition_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cloud_cover_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_product_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raster_info: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    provenance: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_imagery_assets_footprint", "footprint", postgresql_using="gist"),)


class SatelliteAcquisition(Base):
    """A provider catalogue hit and, once retrieved, the resulting asset (provenance of Sentinel imagery)."""

    __tablename__ = "satellite_acquisitions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    aoi_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("areas_of_interest.id", ondelete="SET NULL"), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    collection: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cloud_cover_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    footprint = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=False), nullable=True)
    properties: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    request_params: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="discovered", server_default="discovered")
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("imagery_assets.id", ondelete="SET NULL"), nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("provider", "product_id", "created_by", "aoi_id", name="uq_acquisition_provider_product_user_aoi"),
        Index("ix_satellite_acquisitions_footprint", "footprint", postgresql_using="gist"),
    )
