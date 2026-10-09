"""Provider-neutral types and errors for satellite catalogue / imagery services."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


class ProviderError(Exception):
    """User-presentable provider failure. ``status`` is the HTTP status the API should answer with."""

    code = "provider_error"
    status = 502

    def __init__(self, message: str, *, code: str | None = None, status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        if code:
            self.code = code
        if status:
            self.status = status
        self.retry_after = retry_after


class ProviderNotConfigured(ProviderError):
    code = "provider_not_configured"
    status = 503


class ProviderAuthError(ProviderError):
    code = "provider_auth_failed"
    status = 502


class ProviderRateLimited(ProviderError):
    code = "provider_rate_limited"
    status = 429


class ProviderUnavailable(ProviderError):
    code = "provider_unavailable"
    status = 502


class SceneNotFound(ProviderError):
    code = "scene_unavailable"
    status = 404


@dataclass
class SceneRecord:
    product_id: str
    collection: str
    provider: str
    acquired_at: datetime
    cloud_cover_pct: float | None
    footprint: dict[str, Any] | None  # GeoJSON geometry (WGS84)
    platform: str | None = None
    processing_level: str | None = None
    resolution_m: float | None = 10.0
    properties: dict[str, Any] = field(default_factory=dict)


class SatelliteProvider(Protocol):
    name: str

    async def search(self, aoi_geojson: dict[str, Any], start: datetime, end: datetime, *, max_cloud_pct: float, limit: int,
                     collection: str = "sentinel-2-l2a") -> list[SceneRecord]: ...

    async def process_geotiff(self, *, epsg: int, bbox: tuple[float, float, float, float], width: int, height: int,
                              acquired_at: datetime, window_s: int = 600) -> bytes: ...

    async def process_preview_png(self, *, bbox_wgs84: tuple[float, float, float, float], acquired_at: datetime, width: int,
                                  height: int, window_s: int = 600) -> bytes: ...

    async def probe(self) -> dict[str, Any]: ...
