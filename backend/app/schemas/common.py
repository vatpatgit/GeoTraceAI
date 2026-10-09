"""Shared API types. Conventions (mirrored by the frontend `src/types/api.ts`):

* JSON keys are snake_case; ids are UUID strings; datetimes are ISO-8601 UTC with a trailing ``Z``.
* All geometries are GeoJSON in EPSG:4326 (lon, lat). Areas are square metres unless the field says otherwise.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer


def _to_utc(v: datetime) -> datetime:
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


def _fmt(v: datetime) -> str:
    return _to_utc(v).isoformat().replace("+00:00", "Z")


UtcDateTime = Annotated[datetime, AfterValidator(_to_utc), PlainSerializer(_fmt, return_type=str, when_used="json")]

Severity = Literal["low", "medium", "high", "critical"]
ReviewStatus = Literal["unreviewed", "confirmed", "rejected"]
AnalysisStatus = Literal[
    "queued", "validating", "acquiring_imagery", "preprocessing", "detecting_changes", "polygonizing",
    "evaluating_alerts", "exporting", "completed", "failed", "cancelled",
]
InputType = Literal["upload", "sentinel", "demo"]
DataOrigin = Literal["live", "demo"]  # 'demo' = seeded / synthetic, never real satellite data


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Issue(ApiModel):
    level: Literal["error", "warning", "info"]
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class GeoJSONGeometry(BaseModel):
    type: str
    coordinates: Any


class Page(ApiModel):
    total: int
    limit: int
    offset: int


class Message(ApiModel):
    detail: str
