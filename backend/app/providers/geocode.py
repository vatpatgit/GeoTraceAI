"""Place-name search (OpenStreetMap Nominatim by default). Server-side only; the endpoint is configuration, never user input."""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass

from app.config import settings
from app.providers import http
from app.providers.base import ProviderError, ProviderNotConfigured

_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_COORD = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")
_cache: dict[str, tuple[float, list["Place"]]] = {}
_lock = asyncio.Lock()
_last_call = 0.0
CACHE_TTL_S = 3600.0
MIN_INTERVAL_S = 1.1  # Nominatim usage policy: at most one request per second


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float
    bbox: tuple[float, float, float, float]  # west, south, east, north
    category: str
    kind: str
    importance: float

    def public(self) -> dict:
        return {"name": self.name, "lat": self.lat, "lon": self.lon, "bbox": list(self.bbox), "category": self.category, "kind": self.kind, "importance": round(self.importance, 3)}


def clean(text: str, limit: int = 200) -> str:
    """Untrusted provider text: drop control characters and bound the length."""
    return _CTRL.sub(" ", text or "").strip()[:limit]


def parse_coordinates(q: str) -> tuple[float, float] | None:
    """'lat, lon' typed by the user (no network needed)."""
    m = _COORD.match(q)
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


async def search(query: str, limit: int = 5) -> list[Place]:
    global _last_call
    q = clean(query, 120)
    if len(q) < 2:
        return []
    if settings.GEOCODER_PROVIDER == "none":
        raise ProviderNotConfigured("Place search is disabled on this server (GEOCODER_PROVIDER=none). Select the area on the map instead.")
    key = q.lower()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
        return hit[1]
    async with _lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            resp = await http.request("GET", settings.GEOCODER_URL.rstrip("/") + "/search", retries=2, timeout=settings.GEOCODER_TIMEOUT_S,
                                      params={"q": q, "format": "jsonv2", "limit": max(1, min(limit, 10))},
                                      headers={"User-Agent": settings.GEOCODER_USER_AGENT, "Accept-Language": "en"})
        finally:
            _last_call = time.monotonic()
    try:
        rows = resp.json()
    except ValueError as exc:
        raise ProviderError("The place-search service returned an unreadable answer.", code="geocoder_bad_response") from exc
    out: list[Place] = []
    for r in rows if isinstance(rows, list) else []:
        try:
            s, n, w, e = (float(v) for v in r["boundingbox"])
            out.append(Place(name=clean(r.get("display_name", q)), lat=float(r["lat"]), lon=float(r["lon"]), bbox=(w, s, e, n),
                             category=clean(str(r.get("category", "")), 40), kind=clean(str(r.get("type", "")), 40), importance=float(r.get("importance") or 0.0)))
        except (KeyError, TypeError, ValueError):
            continue
    if len(_cache) > 256:
        _cache.clear()
    _cache[key] = (time.monotonic(), out)
    return out
