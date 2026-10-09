"""Match live hazard events to saved AOIs and keep an in-app alert inbox (deduplicated; unread = notification)."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AreaOfInterest, HazardAlert
from app.providers import hazards as feed
from app.providers.hazards import FeedResult, HazardEvent

SEV_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_cache: dict[str, Any] = {"at": 0.0, "result": None}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def distance_to_aoi_km(poly: BaseGeometry, lat: float, lon: float) -> float:
    """Geodesic distance from the event to the nearest point of the AOI (0 when inside)."""
    pt = Point(lon, lat)
    if poly.covers(pt):
        return 0.0
    a, _ = nearest_points(poly, pt)
    return haversine_km(a.y, a.x, lat, lon)


def quake_severity(mag: float) -> str:
    return "critical" if mag >= 7 else "high" if mag >= 6 else "medium" if mag >= 5 else "low"


def fire_severity(count: int, max_frp: float | None) -> str:
    return "high" if count >= 50 or (max_frp or 0) >= 100 else "medium" if count >= 10 or (max_frp or 0) >= 30 else "low"


STORM_SEV = {"extreme": "critical", "critical": "critical", "high": "high", "severe": "high", "medium": "medium", "moderate": "medium", "low": "low", "minor": "low"}


@dataclass
class Candidate:
    kind: str
    external_id: str
    title: str
    severity: str
    lat: float
    lon: float
    distance_km: float
    occurred_at: datetime | None
    details: dict[str, Any] = field(default_factory=dict)


def match_aoi(poly: BaseGeometry, events: dict[str, list[HazardEvent]], now: datetime) -> list[Candidate]:
    """Pure matching of one AOI against the feed (thresholds from settings). Fire hotspots are aggregated per UTC day."""
    out: list[Candidate] = []
    age = timedelta(hours=settings.HAZARD_MAX_AGE_HOURS)
    for e in events.get("earthquake", []):
        mag = e.details.get("magnitude") or 0.0
        if mag < settings.HAZARD_QUAKE_MIN_MAG or (e.occurred_at and now - e.occurred_at > age):
            continue
        d = distance_to_aoi_km(poly, e.lat, e.lon)
        if d <= settings.HAZARD_QUAKE_RADIUS_KM:
            out.append(Candidate("earthquake", e.external_id, e.title, quake_severity(mag), e.lat, e.lon, d, e.occurred_at, {**e.details, "radius_km": settings.HAZARD_QUAKE_RADIUS_KM}))
    by_day: dict[str, list[tuple[HazardEvent, float]]] = {}
    for e in events.get("fire", []):
        if str(e.details.get("confidence", "")).lower() in ("low", "l") or (e.occurred_at and now - e.occurred_at > age):
            continue
        d = distance_to_aoi_km(poly, e.lat, e.lon)
        if d <= settings.HAZARD_FIRE_RADIUS_KM:
            by_day.setdefault(str(e.details.get("date")), []).append((e, d))
    for day, items in by_day.items():
        frps = [x[0].details.get("frp_mw") for x in items if x[0].details.get("frp_mw") is not None]
        near = min(items, key=lambda x: x[1])
        mx = max(frps) if frps else None
        out.append(Candidate("fire", f"fires-{day}", f"{len(items)} fire hotspot(s) detected on {day} within {settings.HAZARD_FIRE_RADIUS_KM:g} km", fire_severity(len(items), mx),
                             near[0].lat, near[0].lon, near[1], max(x[0].occurred_at for x in items if x[0].occurred_at) if any(x[0].occurred_at for x in items) else None,
                             {"hotspots": len(items), "max_frp_mw": mx, "radius_km": settings.HAZARD_FIRE_RADIUS_KM, "date": day, "source": "NASA FIRMS (satellite thermal anomalies; not confirmed fires)"}))
    sage = timedelta(hours=settings.HAZARD_STORM_MAX_AGE_HOURS)
    for e in events.get("storm", []):
        if e.occurred_at and now - e.occurred_at > sage:
            continue
        d = distance_to_aoi_km(poly, e.lat, e.lon)
        if d <= settings.HAZARD_STORM_RADIUS_KM:
            out.append(Candidate("storm", e.external_id, e.title, STORM_SEV.get((e.severity_hint or "").lower(), "low"), e.lat, e.lon, d, e.occurred_at, {**e.details, "radius_km": settings.HAZARD_STORM_RADIUS_KM, "source": "NASA EONET"}))
    return out


@dataclass
class RefreshSummary:
    aois: int = 0
    new: int = 0
    updated: int = 0
    expired: int = 0
    active: int = 0
    cached: bool = False
    errors: dict[str, str] = field(default_factory=dict)
    fetched: dict[str, int] = field(default_factory=dict)


async def get_feed(force: bool = False) -> tuple[FeedResult, bool]:
    now = time.monotonic()
    if not force and _cache["result"] is not None and now - _cache["at"] < settings.HAZARD_MIN_REFRESH_S:
        return _cache["result"], True
    res = await feed.fetch_feed()
    _cache.update(at=now, result=res)
    return res, False


async def reconcile(db: AsyncSession, aois: Iterable[AreaOfInterest], res: FeedResult, now: datetime | None = None) -> RefreshSummary:
    now = now or datetime.now(timezone.utc)
    sm = RefreshSummary(errors=dict(res.errors), fetched={k: len(v) for k, v in res.events.items()})
    for aoi in aois:
        sm.aois += 1
        cands = match_aoi(to_shape(aoi.geometry), res.events, now)
        existing = {(h.kind, h.external_id): h for h in (await db.execute(select(HazardAlert).where(HazardAlert.aoi_id == aoi.id))).scalars()}
        seen = set()
        for c in cands:
            key = (c.kind, c.external_id)
            seen.add(key)
            row = existing.get(key)
            if row is None:
                db.add(HazardAlert(aoi_id=aoi.id, kind=c.kind, external_id=c.external_id, title=c.title, severity=c.severity, lat=c.lat, lon=c.lon,
                                   distance_km=round(c.distance_km, 1), occurred_at=c.occurred_at, details=c.details, status="active"))
                sm.new += 1
                continue
            changed = (row.title != c.title or row.severity != c.severity or row.details != c.details or row.status != "active")
            if SEV_RANK[c.severity] > SEV_RANK.get(row.severity, 0) or row.status == "expired":
                row.read_at = None  # worse (or back again): notify again
            row.title, row.severity, row.lat, row.lon, row.distance_km, row.occurred_at, row.details = c.title, c.severity, c.lat, c.lon, round(c.distance_km, 1), c.occurred_at, c.details
            row.status, row.last_seen_at = "active", now
            sm.updated += int(changed)
        for key, row in existing.items():
            # a kind whose fetch failed is unknown, not gone: leave it alone
            if key not in seen and row.status == "active" and row.kind in res.events:
                row.status = "expired"
                sm.expired += 1
    await db.commit()
    return sm


async def refresh_for(db: AsyncSession, aois: list[AreaOfInterest], force: bool = False) -> RefreshSummary:
    res, cached = await get_feed(force)
    sm = await reconcile(db, aois, res)
    sm.cached = cached
    sm.active = sum(1 for a in (await db.execute(select(HazardAlert).where(HazardAlert.aoi_id.in_([x.id for x in aois]), HazardAlert.status == "active"))).scalars()) if aois else 0
    return sm
