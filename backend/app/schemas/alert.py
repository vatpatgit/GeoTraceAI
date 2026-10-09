from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import ApiModel, Severity, UtcDateTime

IncidentStatus = Literal["open", "acknowledged", "resolved"]


class AlertRuleBase(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    project_id: UUID | None = None
    region_id: UUID | None = Field(default=None, description="Monitored region the change must relate to")
    aoi_id: UUID | None = None
    region_relation: Literal["intersects", "within_distance"] = "intersects"
    distance_m: float | None = Field(default=None, gt=0, le=500_000)
    categories: list[str] | None = Field(default=None, max_length=30)
    min_area_m2: float = Field(default=0.0, ge=0)
    min_severity: Severity = "low"
    min_magnitude: float | None = Field(default=None, ge=0, le=1)
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    dedup_mode: Literal["none", "spatial"] = "spatial"
    dedup_window_days: int = Field(default=30, ge=1, le=3650)
    dedup_overlap: float = Field(default=0.5, gt=0, le=1)

    @model_validator(mode="after")
    def _distance_required(self):
        if self.region_relation == "within_distance" and not self.distance_m:
            raise ValueError("distance_m is required when region_relation is 'within_distance'.")
        if self.region_relation == "within_distance" and not (self.region_id or self.aoi_id):
            raise ValueError("within_distance needs a region_id or aoi_id to measure from.")
        return self


class AlertRuleCreate(AlertRuleBase):
    pass


class AlertRuleUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None
    project_id: UUID | None = None
    region_id: UUID | None = None
    aoi_id: UUID | None = None
    region_relation: Literal["intersects", "within_distance"] | None = None
    distance_m: float | None = Field(default=None, gt=0, le=500_000)
    categories: list[str] | None = None
    min_area_m2: float | None = Field(default=None, ge=0)
    min_severity: Severity | None = None
    min_magnitude: float | None = Field(default=None, ge=0, le=1)
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    dedup_mode: Literal["none", "spatial"] | None = None
    dedup_window_days: int | None = Field(default=None, ge=1, le=3650)
    dedup_overlap: float | None = Field(default=None, gt=0, le=1)


class AlertRuleOut(AlertRuleBase):
    id: UUID
    owner_id: UUID
    created_at: UtcDateTime
    updated_at: UtcDateTime
    last_evaluated_at: UtcDateTime | None
    incident_count: int = 0


class IncidentOut(ApiModel):
    id: UUID
    rule_id: UUID
    rule_name: str
    analysis_id: UUID
    analysis_name: str | None = None
    feature_id: UUID
    severity: Severity
    category: str
    status: IncidentStatus
    title: str
    message: str
    evidence: dict[str, Any]
    area_m2: float | None = None
    confidence: float | None = None
    centroid: list[float] | None = None  # [lon, lat] for "show on map"
    bbox: list[float] | None = None
    region_id: UUID | None = None
    detected_at: UtcDateTime
    created_at: UtcDateTime
    acknowledged_at: UtcDateTime | None
    resolved_at: UtcDateTime | None
    resolution_note: str | None
    is_demo: bool = False


class IncidentUpdate(ApiModel):
    status: IncidentStatus
    resolution_note: str | None = Field(default=None, max_length=2000)


class IncidentPage(ApiModel):
    total: int
    open: int
    limit: int
    offset: int
    items: list[IncidentOut]
