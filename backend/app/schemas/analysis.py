from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import AnalysisStatus, ApiModel, InputType, Issue, ReviewStatus, Severity, UtcDateTime


# ----------------------------------------------------------------------------------------------------- imagery
class ImageryAssetOut(ApiModel):
    id: UUID
    project_id: UUID | None
    kind: str
    original_filename: str | None
    size_bytes: int
    width: int
    height: int
    band_count: int
    dtype: str
    crs_epsg: int | None
    pixel_size_m: float
    nodata: float | None
    footprint: dict[str, Any]
    bounds: list[float]  # [min_lon, min_lat, max_lon, max_lat]
    band_descriptions: list[str | None] | None
    band_map: dict[str, int] | None
    band_map_confirmed: bool
    band_notes: list[str] = Field(default_factory=list)
    acquisition_start: UtcDateTime | None
    acquisition_end: UtcDateTime | None
    cloud_cover_pct: float | None
    source_provider: str | None
    source_product_id: str | None
    sha256: str
    is_demo: bool
    warnings: list[Issue] = Field(default_factory=list)
    created_at: UtcDateTime


class ImageryUpdate(ApiModel):
    band_map: dict[str, int] | None = None
    acquisition_start: UtcDateTime | None = None
    acquisition_end: UtcDateTime | None = None


class PairValidateRequest(ApiModel):
    before_asset_id: UUID
    after_asset_id: UUID
    aoi_id: UUID | None = None
    band_map: dict[str, int] | None = None


class PairValidationOut(ApiModel):
    ok: bool
    issues: list[Issue]
    analysis_crs_epsg: int | None
    overlap: dict[str, Any]
    resolution: dict[str, Any]
    bands: dict[str, Any]
    suggested_pixel_size_m: float | None
    model_available: bool
    suggested_method: str
    suggested_method_reason: str


# ----------------------------------------------------------------------------------------------------- analysis
class AnalysisCreate(ApiModel):
    project_id: UUID
    name: str | None = Field(default=None, max_length=160)
    before_asset_id: UUID
    after_asset_id: UUID
    before_date: UtcDateTime | None = None
    after_date: UtcDateTime | None = None
    aoi_id: UUID | None = None
    config: dict[str, Any] | None = Field(default=None, description="Partial PipelineConfig overrides (see docs)")
    input_type: InputType = "upload"
    acquisition_params: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _dates_ordered(self):
        if self.before_date and self.after_date and self.before_date >= self.after_date:
            raise ValueError("before_date must be earlier than after_date.")
        return self


class AnalysisEventOut(ApiModel):
    at: UtcDateTime
    status: str
    progress: float
    message: str | None


class AnalysisOut(ApiModel):
    id: UUID
    project_id: UUID
    aoi_id: UUID | None
    created_by: UUID
    name: str
    input_type: str
    status: AnalysisStatus
    stage_message: str | None
    progress: float
    error: dict[str, Any] | None
    cancel_requested: bool
    before_asset_id: UUID | None
    after_asset_id: UUID | None
    before_date: UtcDateTime | None
    after_date: UtcDateTime | None
    method: str | None
    method_reason: str | None
    model_id: str | None
    config: dict[str, Any]
    summary: dict[str, Any] | None
    warnings: list[dict[str, Any]] | None
    validation: dict[str, Any] | None
    processing: dict[str, Any] | None
    artifacts: list[str] = Field(default_factory=list, description="Names of downloadable artifacts")
    bounds: list[float] | None = Field(default=None, description="[min_lon, min_lat, max_lon, max_lat] of the analysed grid")
    is_demo: bool
    data_origin: Literal["live", "demo"]
    created_at: UtcDateTime
    started_at: UtcDateTime | None
    finished_at: UtcDateTime | None


# ----------------------------------------------------------------------------------------------------- features
class ChangeFeatureProps(ApiModel):
    id: UUID
    analysis_id: UUID
    seq: int
    category: str
    category_basis: str
    area_m2: float
    perimeter_m: float
    centroid: list[float]  # [lon, lat]
    point_on_surface: list[float]
    magnitude: float
    confidence: float | None
    confidence_kind: str | None = None
    delta_ndvi: float | None
    severity: Severity
    severity_reasons: list[str]
    distance_to_boundary_m: float | None
    review_status: ReviewStatus
    review_note: str | None
    before_date: UtcDateTime | None
    after_date: UtcDateTime | None
    bbox: list[float]


class ChangeFeatureOut(ChangeFeatureProps):
    geometry: dict[str, Any]


class FeaturePage(ApiModel):
    total: int
    limit: int
    offset: int
    items: list[ChangeFeatureOut]


class ReviewUpdate(ApiModel):
    review_status: ReviewStatus
    review_note: str | None = Field(default=None, max_length=2000)


# ----------------------------------------------------------------------------------------------------- exports
ExportFormat = Literal["geojson", "gpkg", "csv"]


class AssetMlChangesRequest(ApiModel):
    before_asset_id: UUID
    after_asset_id: UUID
    bbox: list[float] = Field(min_length=4, max_length=4, description="[west, south, east, north] common area to compare (WGS84)")
    width: int = Field(default=1536, ge=256, le=2048)
    model_id: str | None = None
