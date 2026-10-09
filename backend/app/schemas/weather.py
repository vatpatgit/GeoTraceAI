from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.common import ApiModel, UtcDateTime


class WeatherAlertOut(ApiModel):
    id: UUID
    aoi_id: UUID
    aoi_name: str | None = None
    provider: str
    source_alert_id: str
    source: str | None
    title: str
    description: str | None
    tags: list[str]
    severity: str
    urgency: str
    certainty: str
    industry: list[dict[str, Any]]
    geometry: dict[str, Any] | None = Field(description="Provider-supplied area of the alert (GeoJSON, WGS84). Not a satellite-derived change polygon and not the extent of physical damage.")
    start_time: UtcDateTime | None
    end_time: UtcDateTime | None
    status: str
    change_count: int
    first_seen_at: UtcDateTime
    last_seen_at: UtcDateTime
    last_checked_at: UtcDateTime
    notified_at: UtcDateTime | None


class AoiWeatherState(ApiModel):
    aoi_id: UUID
    aoi_name: str
    last_checked_at: UtcDateTime | None
    last_status: str | None
    last_error: str | None
    alert_count: int
    monitoring: bool


class WeatherAlertList(ApiModel):
    configured: bool
    items: list[WeatherAlertOut]
    aois: list[AoiWeatherState]


class RefreshRequest(ApiModel):
    aoi_id: UUID
    force: bool = False
    source: str | None = Field(default=None, description="owm | government")
    tags: list[str] | None = Field(default=None, max_length=17)
    lookahead_hours: int | None = Field(default=None, ge=1, le=120)


class RefreshOut(ApiModel):
    aoi_id: UUID
    checked_at: UtcDateTime
    cached: bool
    new: int
    updated: int
    unchanged: int
    expired: int
    total_active: int
    items: list[WeatherAlertOut]


class MonitoringRequest(ApiModel):
    enabled: bool


class WeatherEventOut(ApiModel):
    id: UUID
    alert_id: UUID
    aoi_id: UUID
    kind: str
    changes: list[str]
    title: str
    severity: str
    created_at: UtcDateTime
    read_at: UtcDateTime | None


class EventsRead(ApiModel):
    ids: list[UUID] | None = None
    all: bool = False


class WeatherStatus(ApiModel):
    configured: bool
    scheduled_refresh_minutes: int
    lookahead_hours: int
    max_aoi_km2: float
    sources: list[str]
    tags: list[str]
