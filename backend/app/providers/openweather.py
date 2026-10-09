"""OpenWeather Alerts API client (https://openweathermap.org/openweather-alerts) with strict request building and defensive parsing.

Facts taken from the provider documentation (verified 2026-10): ``GET https://api.openweathermap.org/alerts/1.0`` with query parameters
``appid`` (key), ``location`` (GeoJSON Point or Polygon, WGS84 lon/lat), optional ``source`` (owm|government), ``tags``, ``severity``,
``certainty``, ``urgency``, ``start_date`` / ``end_date`` (ISO 8601; default now .. +1 h), ``show_location``. Errors are ``{"code","message"}``;
404 means "no data for these parameters". The documentation does not publish the full example response, rate limits or the subscription
tier required, so the parser accepts several plausible shapes and never invents fields that are absent.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.geometry.polygon import orient

from app.config import settings
from app.geo.polygonize import geodesic_area_m2
from app.providers.base import ProviderAuthError, ProviderError, ProviderNotConfigured, ProviderRateLimited, ProviderUnavailable
from app.providers.http import request

logger = logging.getLogger(__name__)

SOURCES = {"owm", "government"}
TAGS = {"coastal_event", "extreme_low_temperature", "extreme_high_temperature", "wind", "flood", "sand_dust", "rain", "fire_warning",
        "marine_event", "avalanches", "fog", "air_quality", "tornado", "cyclone", "snow_ice", "thunderstorm", "hail"}
SEVERITIES = ("unknown", "minor", "moderate", "severe", "extreme")
CERTAINTIES = ("unknown", "unlikely", "possible", "likely", "observed")
URGENCIES = ("unknown", "future", "expected", "immediate")


class AoiGeometryError(ValueError):
    """The AOI cannot be sent to the provider (message is safe to show to users)."""


# --------------------------------------------------------------------------------------------------------- AOI validation
def prepare_location(geometry: dict[str, Any] | Polygon, *, max_area_km2: float | None = None, max_vertices: int | None = None) -> dict[str, Any]:
    """Validate an AOI and return the GeoJSON ``location`` object for the provider (Polygon, RFC 7946 winding, lon/lat)."""
    max_area_km2 = max_area_km2 if max_area_km2 is not None else settings.WEATHER_MAX_AOI_KM2
    max_vertices = max_vertices if max_vertices is not None else settings.WEATHER_MAX_VERTICES
    try:
        geom = geometry if isinstance(geometry, Polygon) else shape(geometry)
    except Exception as exc:
        raise AoiGeometryError("The AOI is not valid GeoJSON geometry.") from exc
    if geom.geom_type == "Point":
        raise AoiGeometryError("Weather alerts are requested for an area: provide a Polygon AOI.")
    if geom.geom_type != "Polygon":
        raise AoiGeometryError(f"Unsupported geometry type '{geom.geom_type}': the provider accepts a single Polygon (MultiPolygon is not supported).")
    if geom.is_empty:
        raise AoiGeometryError("The AOI polygon is empty.")
    xs, ys = zip(*[(c[0], c[1]) for c in geom.exterior.coords])
    if not all(math.isfinite(v) for v in xs + ys):
        raise AoiGeometryError("The AOI contains non-finite coordinates.")
    if min(xs) <= -180 or max(xs) >= 180 or min(ys) <= -90 or max(ys) >= 90:
        raise AoiGeometryError("Longitude must be within (-180, 180) and latitude within (-90, 90) (WGS84, longitude first).")
    if not geom.exterior.is_closed:
        raise AoiGeometryError("The AOI polygon ring is not closed.")
    if not geom.is_valid:
        raise AoiGeometryError("The AOI polygon is invalid (self-intersecting or degenerate).")
    n = len(geom.exterior.coords) + sum(len(r.coords) for r in geom.interiors)
    if n > max_vertices:
        raise AoiGeometryError(f"The AOI has {n} vertices; the limit is {max_vertices}. Simplify the polygon.")
    area_km2 = geodesic_area_m2(geom) / 1e6
    if area_km2 > max_area_km2:
        raise AoiGeometryError(f"The AOI covers {area_km2:,.0f} km2; the limit for weather alerts is {max_area_km2:,.0f} km2.")
    if area_km2 <= 0:
        raise AoiGeometryError("The AOI has no area.")
    return mapping(orient(geom, sign=1.0))


# --------------------------------------------------------------------------------------------------------- normalised model
@dataclass
class NormalizedAlert:
    source_alert_id: str
    source: str | None
    title: str
    description: str | None
    tags: list[str]
    severity: str
    urgency: str
    certainty: str
    industry: list[dict[str, Any]] = field(default_factory=list)
    geometry: dict[str, Any] | None = None  # GeoJSON (Point | Polygon), provider-supplied
    start_time: datetime | None = None
    end_time: datetime | None = None
    id_synthesized: bool = False

    def content_hash(self) -> str:
        """Stable digest of everything a user would care about; a change means the alert was materially updated."""
        geom = json.dumps(self.geometry, sort_keys=True, separators=(",", ":")) if self.geometry else ""
        payload = [self.title, self.description, sorted(self.tags), self.severity, self.urgency, self.certainty, self.source, geom,
                   self.start_time.isoformat() if self.start_time else None, self.end_time.isoformat() if self.end_time else None]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _enum(value: Any, allowed: tuple[str, ...]) -> str:
    v = str(value).strip().lower() if value is not None else ""
    return v if v in allowed else "unknown"


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _depth(c: Any) -> int:
    d = 0
    while isinstance(c, (list, tuple)) and c:
        d += 1
        c = c[0]
    return d


def _geometry(loc: Any) -> dict[str, Any] | None:
    """Accept {type:'polygon'|'Polygon'|'point', coordinates:[...]} with either ring-nested or flat vertex lists. None if unusable."""
    if not isinstance(loc, dict):
        return None
    t = str(loc.get("type", "")).strip().lower()
    coords = loc.get("coordinates")
    try:
        if t == "point":
            if _depth(coords) == 1 and len(coords) >= 2:
                return mapping(Point(float(coords[0]), float(coords[1])))
            return None
        if t == "polygon":
            d = _depth(coords)
            rings = [coords] if d == 2 else coords if d == 3 else None
            if rings is None:
                return None
            poly = Polygon([(float(x), float(y)) for x, y, *_ in rings[0]], [[(float(x), float(y)) for x, y, *_ in r] for r in rings[1:]])
            if poly.is_empty or not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty or poly.geom_type != "Polygon":
                return None
            return mapping(poly)
    except (TypeError, ValueError, IndexError):
        return None
    return None


def _as_list(v: Any) -> list[Any]:
    return v if isinstance(v, list) else ([] if v in (None, "") else [v])


def _tags(a: dict[str, Any]) -> list[str]:
    raw = a.get("tags", a.get("tag"))
    out: list[str] = []
    for t in _as_list(raw):
        if isinstance(t, str):
            out.extend(p.strip().lower() for p in t.split(",") if p.strip())
    return list(dict.fromkeys(out))


def normalize_response(payload: Any) -> list[NormalizedAlert]:
    """Turn a provider payload into one NormalizedAlert per alert id (hourly segments are merged into a time span).

    Defensive: tolerates ``{"items":[{"date","alerts":[...]}]}``, ``{"alerts":[...]}`` or a bare list; ``industry`` as object or list;
    missing optional fields; non-dict junk (skipped). Anything unparseable is dropped rather than guessed.
    """
    segments: list[tuple[datetime | None, dict[str, Any]]] = []
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                when = _parse_dt(it.get("date"))
                for a in _as_list(it.get("alerts")):
                    if isinstance(a, dict):
                        segments.append((when, a))
        elif isinstance(payload.get("alerts"), list):
            segments.extend((None, a) for a in payload["alerts"] if isinstance(a, dict))
    elif isinstance(payload, list):
        segments.extend((None, a) for a in payload if isinstance(a, dict))

    merged: dict[str, NormalizedAlert] = {}
    for when, a in segments:
        ind = [i for i in _as_list(a.get("industry")) if isinstance(i, dict)]
        geometry = _geometry(a.get("location"))
        title = str(a.get("title") or a.get("event") or "").strip() or "Weather alert"
        sid = a.get("alert_ID", a.get("alert_id", a.get("id")))
        synthesized = sid in (None, "")
        if synthesized:
            sid = "synth-" + hashlib.sha1(json.dumps([a.get("source"), title, _tags(a), geometry], sort_keys=True, default=str).encode()).hexdigest()[:16]
        sid = str(sid)
        sev_raw = a.get("severity") or next((i.get("severity") for i in ind if i.get("severity")), None)
        desc = a.get("description") or next((i.get("description") for i in ind if i.get("description")), None)
        start = _parse_dt(a.get("start") or a.get("onset") or a.get("effective")) or when
        end = _parse_dt(a.get("end") or a.get("expires")) or ((when + timedelta(hours=1)) if when else None)
        cur = merged.get(sid)
        if cur is None:
            merged[sid] = NormalizedAlert(
                source_alert_id=sid, source=(str(a["source"]).strip().lower() if a.get("source") else None), title=title,
                description=str(desc).strip() if desc else None, tags=_tags(a), severity=_enum(sev_raw, SEVERITIES),
                urgency=_enum(a.get("urgency"), URGENCIES), certainty=_enum(a.get("certainty"), CERTAINTIES),
                industry=[{k: v for k, v in i.items() if k in ("industry_name", "description", "severity")} for i in ind],
                geometry=geometry, start_time=start, end_time=end, id_synthesized=synthesized)
        else:  # same alert in another hourly segment: widen the time span, keep the most severe values seen
            if start and (cur.start_time is None or start < cur.start_time):
                cur.start_time = start
            if end and (cur.end_time is None or end > cur.end_time):
                cur.end_time = end
            if SEVERITIES.index(_enum(sev_raw, SEVERITIES)) > SEVERITIES.index(cur.severity):
                cur.severity = _enum(sev_raw, SEVERITIES)
            cur.geometry = cur.geometry or geometry
    return list(merged.values())


# --------------------------------------------------------------------------------------------------------- client
class OpenWeatherAlerts:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key if api_key is not None else settings.OPENWEATHER_API_KEY
        self.base_url = (base_url or settings.OPENWEATHER_ALERTS_URL).rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def build_params(self, location: dict[str, Any], *, start: datetime | None = None, end: datetime | None = None, source: str | None = None,
                     tags: list[str] | None = None, severity: str | None = None, certainty: str | None = None,
                     urgency: str | None = None) -> dict[str, str]:
        if not self.api_key:
            raise ProviderNotConfigured("Weather alerts are not configured: set OPENWEATHER_API_KEY on the server.")
        params: dict[str, str] = {"appid": self.api_key, "location": json.dumps(location, separators=(",", ":")), "show_location": "true"}
        if source:
            if source not in SOURCES:
                raise ValueError(f"source must be one of {sorted(SOURCES)}")
            params["source"] = source
        if tags:
            bad = [t for t in tags if t not in TAGS]
            if bad:
                raise ValueError(f"unknown tag(s): {bad}")
            params["tags"] = ",".join(tags)
        for name, value, allowed in (("severity", severity, SEVERITIES), ("certainty", certainty, CERTAINTIES), ("urgency", urgency, URGENCIES)):
            if value:
                if value not in allowed:
                    raise ValueError(f"{name} must be one of {list(allowed)}")
                params[name] = value
        for name, dt in (("start_date", start), ("end_date", end)):
            if dt is not None:
                params[name] = dt.astimezone(timezone.utc).isoformat(timespec="seconds")
        return params

    async def fetch(self, location: dict[str, Any], **filters: Any) -> list[NormalizedAlert]:
        """Call the provider. Returns [] (a valid result) for HTTP 404 'no data' and for an empty alert list."""
        params = self.build_params(location, **filters)
        try:
            resp = await request("GET", self.base_url, params=params, retries=2, timeout=settings.OPENWEATHER_TIMEOUT_S)
        except ProviderAuthError as exc:
            raise ProviderAuthError("OpenWeather rejected the API key, or the key's plan does not include the Alerts product (HTTP 401). "
                                    "Check OPENWEATHER_API_KEY and your OpenWeather subscription.") from exc
        except ProviderRateLimited as exc:
            raise ProviderRateLimited("OpenWeather rate limit reached. Try again later.", retry_after=exc.retry_after) from exc
        except ProviderUnavailable as exc:
            raise ProviderUnavailable("OpenWeather is unavailable right now (timeout, network or server error). Try again shortly.", code=exc.code,
                                      status=exc.status) from exc
        except ProviderError as exc:
            if exc.code == "provider_not_found":
                return []  # documented: 404 = no data matches the request parameters
            if exc.code == "provider_bad_request":
                raise ProviderError("OpenWeather rejected the request parameters. " + str(exc).split(": ", 1)[-1], code="provider_bad_request", status=422) from exc
            raise
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ProviderUnavailable("OpenWeather returned a response that is not valid JSON.", code="provider_malformed") from exc
        if not isinstance(payload, (dict, list)):
            raise ProviderUnavailable("OpenWeather returned an unexpected response format.", code="provider_malformed")
        if isinstance(payload, dict) and "items" not in payload and "alerts" not in payload and isinstance(payload.get("code"), int) and payload["code"] >= 400:
            raise ProviderError(f"OpenWeather error {payload['code']}: {str(payload.get('message', ''))[:200]}", code="provider_error")
        return normalize_response(payload)
