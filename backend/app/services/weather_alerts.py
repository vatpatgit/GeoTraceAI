"""Weather-alert refresh: fetch for an AOI, upsert, detect meaningful changes, and emit de-duplicated in-app notification events."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import shape
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AreaOfInterest, WeatherAlert, WeatherAlertEvent, WeatherAoiState
from app.providers.base import ProviderError
from app.providers.openweather import NormalizedAlert, OpenWeatherAlerts, prepare_location

logger = logging.getLogger(__name__)

TRACKED_FIELDS = ("title", "description", "tags", "severity", "urgency", "certainty", "start_time", "end_time", "geometry")


@dataclass
class RefreshResult:
    aoi_id: uuid.UUID
    checked_at: datetime
    cached: bool = False
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    expired: int = 0
    total_active: int = 0
    events: list[uuid.UUID] = field(default_factory=list)


def _geom_value(g: dict[str, Any] | None):
    return from_shape(shape(g), srid=4326) if g else None


def _changed_fields(row: WeatherAlert, n: NormalizedAlert) -> list[str]:
    out = []
    for f in TRACKED_FIELDS:
        old = getattr(row, f)
        new = getattr(n, f)
        if f == "geometry":
            old = to_shape(old).wkt if old is not None else None
            new = shape(new).wkt if new else None
            if old != new:  # compare after a WKT round-trip so float formatting alone is not a "change"
                try:
                    old_g, new_g = to_shape(row.geometry), shape(n.geometry)
                    if old_g.equals_exact(new_g, 1e-6):
                        continue
                except Exception:
                    pass
                out.append(f)
            continue
        if f in ("start_time", "end_time"):
            old = old.astimezone(timezone.utc).replace(microsecond=0) if old else None
            new = new.astimezone(timezone.utc).replace(microsecond=0) if new else None
        if f == "tags":
            old, new = sorted(old or []), sorted(new or [])
        if old != new:
            out.append(f)
    return out


async def refresh_aoi(db: AsyncSession, aoi: AreaOfInterest, *, client: OpenWeatherAlerts | None = None, force: bool = False,
                      source: str | None = None, tags: list[str] | None = None, lookahead_hours: int | None = None) -> RefreshResult:
    """Fetch current alerts for one AOI and reconcile them with the stored set.

    Raises ProviderError (not configured / auth / rate limit / outage) after recording the failed attempt; stored alerts are left untouched.
    """
    client = client or OpenWeatherAlerts()
    now = datetime.now(timezone.utc)
    state = await db.get(WeatherAoiState, aoi.id)
    if state is None:
        state = WeatherAoiState(aoi_id=aoi.id)
        db.add(state)
    if not force and state.last_checked_at and state.last_status == "ok" and (now - state.last_checked_at).total_seconds() < settings.WEATHER_MIN_REFRESH_S:
        active = (await db.execute(select(WeatherAlert).where(WeatherAlert.aoi_id == aoi.id, WeatherAlert.status == "active"))).scalars().all()
        return RefreshResult(aoi_id=aoi.id, checked_at=state.last_checked_at, cached=True, total_active=len(active))

    location = prepare_location(to_shape(aoi.geometry))  # AoiGeometryError propagates (422 at the API layer)
    hours = max(1, min(lookahead_hours or settings.WEATHER_LOOKAHEAD_HOURS, 120))
    try:
        alerts = await client.fetch(location, start=now, end=now + timedelta(hours=hours), source=source, tags=tags)
    except ProviderError as exc:
        state.last_checked_at, state.last_status, state.last_error = now, "error", str(exc)[:500]
        await db.commit()
        raise

    existing = {a.source_alert_id: a for a in (await db.execute(select(WeatherAlert).where(WeatherAlert.aoi_id == aoi.id, WeatherAlert.provider == "openweather"))).scalars()}
    res = RefreshResult(aoi_id=aoi.id, checked_at=now)
    seen: set[str] = set()
    for n in alerts:
        seen.add(n.source_alert_id)
        h = n.content_hash()
        row = existing.get(n.source_alert_id)
        if row is None:
            row = WeatherAlert(
                aoi_id=aoi.id, source_alert_id=n.source_alert_id, source=n.source, title=n.title[:300], description=n.description, tags=n.tags,
                severity=n.severity, urgency=n.urgency, certainty=n.certainty, industry=n.industry, geometry=_geom_value(n.geometry),
                start_time=n.start_time, end_time=n.end_time, content_hash=h, id_synthesized=n.id_synthesized, first_seen_at=now, last_seen_at=now,
                last_checked_at=now, updated_at=now)
            db.add(row)
            await db.flush()
            row.notified_hash, row.notified_at = h, now
            ev = WeatherAlertEvent(alert_id=row.id, aoi_id=aoi.id, kind="new", changes=[], title=row.title, severity=row.severity)
            db.add(ev)
            await db.flush()
            res.new += 1
            res.events.append(ev.id)
            continue
        row.last_seen_at = row.last_checked_at = now
        reappeared = row.status == "expired"
        if row.content_hash != h:
            changes = _changed_fields(row, n)
            row.title, row.description, row.tags, row.severity, row.urgency, row.certainty = n.title[:300], n.description, n.tags, n.severity, n.urgency, n.certainty
            row.source, row.industry, row.geometry, row.start_time, row.end_time = n.source, n.industry, _geom_value(n.geometry), n.start_time, n.end_time
            row.content_hash, row.updated_at, row.status = h, now, "active"
            row.change_count += 1
            if changes:  # a hash difference with no tracked field difference (formatting only) is not worth a notification
                ev = WeatherAlertEvent(alert_id=row.id, aoi_id=aoi.id, kind="updated", changes=changes, title=row.title, severity=row.severity)
                db.add(ev)
                await db.flush()
                row.notified_hash, row.notified_at = h, now
                res.updated += 1
                res.events.append(ev.id)
                continue
        elif reappeared:
            row.status = "active"
            ev = WeatherAlertEvent(alert_id=row.id, aoi_id=aoi.id, kind="updated", changes=["status"], title=row.title, severity=row.severity)
            db.add(ev)
            await db.flush()
            res.updated += 1
            res.events.append(ev.id)
            continue
        res.unchanged += 1
    # alerts the provider no longer returns for this window have ended (only after a SUCCESSFUL fetch, including an empty one)
    for sid, row in existing.items():
        if sid not in seen and row.status == "active":
            row.status = "expired"
            row.last_checked_at = now
            res.expired += 1
    state.last_checked_at, state.last_status, state.last_error = now, "ok", None
    state.last_count = len(alerts)
    res.total_active = len(alerts)
    await db.commit()
    return res


async def monitored_aois(db: AsyncSession) -> list[AreaOfInterest]:
    return list((await db.execute(select(AreaOfInterest).join(WeatherAoiState, WeatherAoiState.aoi_id == AreaOfInterest.id).where(WeatherAoiState.monitoring.is_(True)))).scalars())
