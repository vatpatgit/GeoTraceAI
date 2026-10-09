from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import ApiModel, UtcDateTime


class ProjectCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    visibility: Literal["private", "shared"] = "private"


class ProjectUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    visibility: Literal["private", "shared"] | None = None


class ProjectOut(ApiModel):
    id: UUID
    name: str
    description: str | None
    owner_id: UUID
    visibility: str
    is_demo: bool
    created_at: UtcDateTime
    updated_at: UtcDateTime
    analysis_count: int = 0
    can_write: bool = False


class AoiCreate(ApiModel):
    """Exactly one of ``geometry`` (Polygon), ``bbox`` or ``center`` + ``radius_m`` defines the area."""

    name: str = Field(min_length=1, max_length=120)
    source: Literal["polygon", "bbox", "point_radius", "region"] = "polygon"
    geometry: dict[str, Any] | None = None
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4, description="[min_lon, min_lat, max_lon, max_lat]")
    center: list[float] | None = Field(default=None, min_length=2, max_length=2, description="[lon, lat]")
    radius_m: float | None = Field(default=None, gt=0)
    region_id: UUID | None = None

    @model_validator(mode="after")
    def _one_definition(self):
        given = [self.geometry is not None, self.bbox is not None, self.center is not None, self.region_id is not None]
        if sum(given) != 1:
            raise ValueError("Provide exactly one of geometry, bbox, center+radius_m, or region_id.")
        if self.center is not None and self.radius_m is None:
            raise ValueError("radius_m is required with center.")
        return self


class AoiOut(ApiModel):
    id: UUID
    project_id: UUID
    name: str
    geometry: dict[str, Any]
    bbox: list[float]
    area_km2: float
    source: str
    region_id: UUID | None = None
    created_at: UtcDateTime
