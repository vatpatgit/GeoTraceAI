"""Query filters for change features (shared by the list endpoint, exports and analytics)."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ReviewStatus, Severity

SortKey = Literal["area_desc", "area_asc", "severity_desc", "confidence_desc", "seq"]


class FeatureFilter(BaseModel):
    severities: list[Severity] | None = None
    categories: list[str] | None = None
    review_status: list[ReviewStatus] | None = None
    min_area_m2: float | None = Field(default=None, ge=0)
    max_area_m2: float | None = Field(default=None, ge=0)
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    min_magnitude: float | None = Field(default=None, ge=0, le=1)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    aoi_id: UUID | None = None
    ids: list[UUID] | None = None
    sort: SortKey = "area_desc"
