"""Concrete providers: Copernicus Data Space Ecosystem (CDSE) and commercial Sentinel Hub.

The two are NOT interchangeable (different endpoints, token issuers and catalogue APIs):

  * CDSE            catalogue = public STAC (no credentials needed), imagery = Sentinel Hub Process API at
                    ``sh.dataspace.copernicus.eu`` using a CDSE OAuth client (client ids look like ``sh-<uuid>``).
  * Sentinel Hub    catalogue = Catalog API, imagery = Process API at ``services.sentinel-hub.com`` using a Sentinel Hub
                    OAuth client (plain UUID client ids).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.providers.base import ProviderError, ProviderNotConfigured, SceneNotFound, SceneRecord
from app.providers.http import TokenManager, request
from app.providers.process_api import ProcessClient

logger = logging.getLogger(__name__)
SH_TOKEN_URL = "https://services.sentinel-hub.com/oauth/token"


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _scene_from_feature(f: dict[str, Any], provider: str, collection: str) -> SceneRecord:
    p = f.get("properties", {})
    keep = {k: p[k] for k in ("view:sun_elevation", "view:sun_azimuth", "view:incidence_angle", "sat:relative_orbit", "sat:orbit_state",
                              "grid:code", "processing:version", "constellation", "eo:snow_cover") if k in p}
    cc = p.get("eo:cloud_cover")
    return SceneRecord(
        product_id=f["id"], collection=collection, provider=provider, acquired_at=_parse_dt(p["datetime"]),
        cloud_cover_pct=float(cc) if cc is not None else None, footprint=f.get("geometry"), platform=p.get("platform"),
        processing_level=p.get("processing:level"), resolution_m=float(p.get("gsd", 10) or 10), properties=keep)


class _ShProcessing:
    """Shared Process-API plumbing."""

    name: str
    _process: ProcessClient | None

    async def process_geotiff(self, **kw) -> bytes:
        return await self._require_process().geotiff(**kw)

    async def process_preview_png(self, **kw) -> bytes:
        return await self._require_process().preview_png(**kw)

    async def process_badmask_png(self, **kw) -> bytes:
        return await self._require_process().badmask_png(**kw)

    def _require_process(self) -> ProcessClient:
        if self._process is None:
            raise ProviderNotConfigured(
                f"{self.name}: imagery retrieval needs OAuth client credentials on the server (SENTINEL_HUB_CLIENT_ID / "
                "SENTINEL_HUB_CLIENT_SECRET). Catalogue search works without them.")
        return self._process


class CdseProvider(_ShProcessing):
    name = "cdse"

    def __init__(self, client_id: str | None, client_secret: str | None):
        self._tokens = TokenManager(settings.CDSE_TOKEN_URL, client_id, client_secret) if client_id and client_secret else None
        self._process = ProcessClient(settings.CDSE_SH_BASE_URL, self._tokens) if self._tokens else None

    @property
    def imagery_configured(self) -> bool:
        return self._process is not None

    async def search(self, aoi_geojson: dict[str, Any], start: datetime, end: datetime, *, max_cloud_pct: float, limit: int,
                     collection: str = "sentinel-2-l2a") -> list[SceneRecord]:
        body = {
            "collections": [collection], "intersects": aoi_geojson,
            "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "limit": min(max(limit, 1), 100),
            "query": {"eo:cloud_cover": {"lte": max_cloud_pct}},
            "sortby": [{"field": "properties.datetime", "direction": "asc"}],
        }
        resp = await request("POST", f"{settings.CDSE_STAC_URL.rstrip('/')}/search", json=body)
        feats = resp.json().get("features", [])
        return [_scene_from_feature(f, self.name, collection) for f in feats if f.get("properties", {}).get("datetime")]

    async def get_scene(self, product_id: str, collection: str = "sentinel-2-l2a") -> SceneRecord:
        resp = await request("GET", f"{settings.CDSE_STAC_URL.rstrip('/')}/collections/{collection}/items/{product_id}")
        f = resp.json()
        if not f.get("properties", {}).get("datetime"):
            raise SceneNotFound(f"Scene {product_id} has no acquisition time in the catalogue.")
        return _scene_from_feature(f, self.name, collection)

    async def probe(self) -> dict[str, Any]:
        out: dict[str, Any] = {"catalog": "unavailable", "imagery": "not_configured", "detail": ""}
        try:
            await request("GET", f"{settings.CDSE_STAC_URL.rstrip('/')}/", retries=1, timeout=10.0)
            out["catalog"] = "available"
        except ProviderError as exc:
            out["detail"] = f"STAC catalogue: {exc}"
        if self._tokens:
            try:
                await self._tokens.get()
                out["imagery"] = "available"
                out["detail"] = out["detail"] or "CDSE catalogue (public STAC) and Process API (OAuth) reachable."
            except ProviderError as exc:
                out["imagery"] = "unavailable"
                out["detail"] = f"{out['detail']} Process API auth: {exc}".strip()
        else:
            out["detail"] = out["detail"] or "CDSE catalogue reachable. No OAuth client configured, so imagery retrieval is disabled."
        return out


class SentinelHubProvider(_ShProcessing):
    name = "sentinel_hub"

    def __init__(self, client_id: str | None, client_secret: str | None, base_url: str):
        self.base_url = base_url.rstrip("/")
        token_url = settings.SENTINEL_HUB_TOKEN_URL or SH_TOKEN_URL
        self._tokens = TokenManager(token_url, client_id, client_secret) if client_id and client_secret else None
        self._process = ProcessClient(self.base_url, self._tokens) if self._tokens else None

    async def search(self, aoi_geojson: dict[str, Any], start: datetime, end: datetime, *, max_cloud_pct: float, limit: int,
                     collection: str = "sentinel-2-l2a") -> list[SceneRecord]:
        if self._tokens is None:
            raise ProviderNotConfigured("Sentinel Hub catalogue search requires OAuth client credentials (SENTINEL_HUB_CLIENT_ID / SECRET).")
        token = await self._tokens.get()
        body = {
            "collections": [collection], "intersects": aoi_geojson,
            "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}", "limit": min(max(limit, 1), 100),
            "filter": {"op": "<=", "args": [{"property": "eo:cloud_cover"}, max_cloud_pct]}, "filter-lang": "cql2-json",
            "fields": {"include": ["id", "properties.datetime", "properties.eo:cloud_cover"], "exclude": []},
        }
        resp = await request("POST", f"{self.base_url}/api/v1/catalog/1.0.0/search", json=body, headers={"Authorization": f"Bearer {token}"})
        return [_scene_from_feature(f, self.name, collection) for f in resp.json().get("features", []) if f.get("properties", {}).get("datetime")]

    async def get_scene(self, product_id: str, collection: str = "sentinel-2-l2a") -> SceneRecord:
        if self._tokens is None:
            raise ProviderNotConfigured("Sentinel Hub requires OAuth client credentials.")
        token = await self._tokens.get()
        body = {"collections": [collection], "ids": [product_id], "limit": 1}
        resp = await request("POST", f"{self.base_url}/api/v1/catalog/1.0.0/search", json=body, headers={"Authorization": f"Bearer {token}"})
        feats = resp.json().get("features", [])
        if not feats or not feats[0].get("properties", {}).get("datetime"):
            raise SceneNotFound(f"Scene {product_id} was not found in the Sentinel Hub catalogue.")
        return _scene_from_feature(feats[0], self.name, collection)

    async def probe(self) -> dict[str, Any]:
        if self._tokens is None:
            return {"catalog": "not_configured", "imagery": "not_configured", "detail": "Sentinel Hub OAuth client not configured."}
        try:
            await self._tokens.get()
            return {"catalog": "available", "imagery": "available", "detail": "Sentinel Hub OAuth succeeded."}
        except ProviderError as exc:
            return {"catalog": "unavailable", "imagery": "unavailable", "detail": str(exc)}


_cache: dict[str, Any] = {}


def build_provider():
    """Select a provider per ``SENTINEL_PROVIDER``. 'auto': an ``sh-<uuid>`` client id is a CDSE client; anything else (or a
    custom non-CDSE base URL) is Sentinel Hub; with no credentials at all the public CDSE catalogue is used (search only)."""
    mode = settings.SENTINEL_PROVIDER
    cid, sec = settings.SENTINEL_HUB_CLIENT_ID, settings.SENTINEL_HUB_CLIENT_SECRET
    if mode == "none":
        return None
    if mode == "sentinel_hub":
        return SentinelHubProvider(cid, sec, settings.SENTINEL_HUB_BASE_URL)
    if mode == "cdse":
        return CdseProvider(cid, sec)
    if cid and cid.startswith("sh-"):
        return CdseProvider(cid, sec)
    if cid and sec:
        return SentinelHubProvider(cid, sec, settings.SENTINEL_HUB_BASE_URL)
    return CdseProvider(None, None)


def get_provider():
    key = (settings.SENTINEL_PROVIDER, settings.SENTINEL_HUB_CLIENT_ID, settings.SENTINEL_HUB_CLIENT_SECRET, settings.SENTINEL_HUB_BASE_URL)
    if _cache.get("key") != key:
        _cache["key"], _cache["provider"] = key, build_provider()
    return _cache["provider"]


def reset_provider_cache() -> None:
    _cache.clear()
