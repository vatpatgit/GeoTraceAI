from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import ApiModel, UtcDateTime


class DateWindow(ApiModel):
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self):
        if self.start > self.end:
            raise ValueError("start must not be after end.")
        return self


class SentinelSearchRequest(ApiModel):
    """AOI is given by ``aoi_id`` or by exactly one of bbox / point+radius / geometry. Two date windows: before and after."""

    project_id: UUID | None = None
    aoi_id: UUID | None = None
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    center: list[float] | None = Field(default=None, min_length=2, max_length=2, description="[lon, lat]")
    radius_m: float | None = Field(default=None, gt=0)
    geometry: dict[str, Any] | None = None
    before: DateWindow
    after: DateWindow
    max_cloud_cover_pct: float = Field(default=30.0, ge=0, le=100)
    collection: Literal["sentinel-2-l2a"] = "sentinel-2-l2a"
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _aoi_given(self):
        n = sum(x is not None for x in (self.aoi_id, self.bbox, self.center, self.geometry))
        if n != 1:
            raise ValueError("Provide exactly one of aoi_id, bbox, center+radius_m, or geometry.")
        if self.center is not None and self.radius_m is None:
            raise ValueError("radius_m is required with center.")
        if self.before.end >= self.after.start:
            raise ValueError("The before window must end before the after window starts.")
        return self


class SceneOut(ApiModel):
    product_id: str
    collection: str
    provider: str
    acquired_at: UtcDateTime
    cloud_cover_pct: float | None
    footprint: dict[str, Any] | None
    coverage_of_aoi_pct: float | None = Field(default=None, description="Share of the AOI covered by this scene")
    thumbnail_url: str | None = None
    resolution_m: float | None = 10.0
    platform: str | None = None
    processing_level: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class SentinelSearchResponse(ApiModel):
    provider: str
    aoi_geometry: dict[str, Any]
    aoi_area_km2: float
    before: list[SceneOut]
    after: list[SceneOut]
    suggested_before: str | None = None
    suggested_after: str | None = None
    suggestion_rule: str
    warnings: list[str] = Field(default_factory=list)


class PreviewRequest(ApiModel):
    product_id: str
    acquired_at: UtcDateTime
    bbox: list[float] = Field(min_length=4, max_length=4, description="[min_lon, min_lat, max_lon, max_lat] (<= 0.5 deg)")
    width: int = Field(default=512, ge=64, le=2048)


class AcquireRequest(ApiModel):
    project_id: UUID
    aoi_id: UUID | None = None
    aoi_geometry: dict[str, Any] | None = None
    before_product_id: str | None = None
    after_product_id: str | None = None
    before: DateWindow | None = None
    after: DateWindow | None = None
    max_cloud_cover_pct: float = Field(default=30.0, ge=0, le=100)
    auto_select: bool = Field(default=False, description="Use the documented automatic rule when product ids are omitted")
    pixel_size_m: float = Field(default=10.0, ge=10.0, le=120.0)
    name: str | None = Field(default=None, max_length=160)
    config: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _selection(self):
        if self.aoi_id is None and self.aoi_geometry is None:
            raise ValueError("Provide aoi_id or aoi_geometry.")
        if not self.auto_select and not (self.before_product_id and self.after_product_id):
            raise ValueError("Select a before and an after scene, or set auto_select=true with date windows.")
        if self.auto_select and not (self.before and self.after):
            raise ValueError("auto_select needs before and after date windows.")
        return self


class AcquireResponse(ApiModel):
    analysis_id: UUID
    status: str
    before_product_id: str | None
    after_product_id: str | None
    message: str


class ProviderStatus(ApiModel):
    provider: str
    configured: bool
    catalog: Literal["available", "unavailable", "not_configured"]
    imagery: Literal["available", "unavailable", "not_configured"]
    detail: str


class MlChangesRequest(ApiModel):
    bbox: list[float] = Field(min_length=4, max_length=4, description="[min_lon, min_lat, max_lon, max_lat] (<= 0.5 deg)")
    before_at: UtcDateTime
    after_at: UtcDateTime
    model_id: str | None = None
    width: int = Field(default=1536, ge=256, le=2048)
