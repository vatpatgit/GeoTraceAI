"""Weather alerts (OpenWeather Alerts API) for saved AOIs. The provider key never leaves the server."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_authenticated_user, require_user_or_admin
from app.config import settings
from app.database import get_db
from app.models import AreaOfInterest, Project, User, WeatherAlert, WeatherAlertEvent, WeatherAoiState
from app.providers.base import ProviderError
from app.providers.openweather import SOURCES, TAGS, AoiGeometryError, OpenWeatherAlerts
from app.schemas.weather import (AoiWeatherState, EventsRead, MonitoringRequest, RefreshOut, RefreshRequest, WeatherAlertList, WeatherAlertOut,
                                 WeatherEventOut, WeatherStatus)
from app.services import access
from app.services.weather_alerts import refresh_aoi

router = APIRouter()


def _out(a: WeatherAlert, aoi_name: str | None) -> WeatherAlertOut:
    return WeatherAlertOut(
        id=a.id, aoi_id=a.aoi_id, aoi_name=aoi_name, provider=a.provider, source_alert_id=a.source_alert_id, source=a.source, title=a.title,
        description=a.description, tags=a.tags or [], severity=a.severity, urgency=a.urgency, certainty=a.certainty, industry=a.industry or [],
        geometry=mapping(to_shape(a.geometry)) if a.geometry is not None else None, start_time=a.start_time, end_time=a.end_time, status=a.status,
        change_count=a.change_count, first_seen_at=a.first_seen_at, last_seen_at=a.last_seen_at, last_checked_at=a.last_checked_at, notified_at=a.notified_at)


async def _load_aoi(db: AsyncSession, aoi_id: uuid.UUID, user: User, *, write: bool = False) -> AreaOfInterest:
    aoi = await db.get(AreaOfInterest, aoi_id)
    if aoi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "AOI not found")
    await access.load_project(db, aoi.project_id, user, write=write)  # 404 for hidden projects, 403 for read-only users on write
    return aoi


def _provider_http(exc: ProviderError) -> HTTPException:
    headers = {"Retry-After": str(int(exc.retry_after))} if getattr(exc, "retry_after", None) else None
    return HTTPException(exc.status, detail={"code": exc.code, "message": str(exc)}, headers=headers)


@router.get("/status", response_model=WeatherStatus)
async def weather_status(user: User = Depends(require_authenticated_user)):
    return WeatherStatus(configured=OpenWeatherAlerts().configured, scheduled_refresh_minutes=max(0, settings.WEATHER_REFRESH_MINUTES),
                         lookahead_hours=settings.WEATHER_LOOKAHEAD_HOURS, max_aoi_km2=settings.WEATHER_MAX_AOI_KM2, sources=sorted(SOURCES), tags=sorted(TAGS))


@router.get("", response_model=WeatherAlertList)
async def list_alerts(aoi_id: uuid.UUID | None = None, status_filter: str | None = Query(default=None, alias="status", pattern="^(active|expired)$"),
                      db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    """Stored alerts for every AOI the caller can read (optionally one AOI / one status). Never calls the provider."""
    aoi_q = select(AreaOfInterest).join(Project, Project.id == AreaOfInterest.project_id).where(access.readable_projects_clause(user))
    if aoi_id:
        aoi_q = aoi_q.where(AreaOfInterest.id == aoi_id)
    aois = {a.id: a for a in (await db.execute(aoi_q)).scalars()}
    if aoi_id and aoi_id not in aois:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "AOI not found")
    items: list[WeatherAlert] = []
    states: dict[uuid.UUID, WeatherAoiState] = {}
    if aois:
        q = select(WeatherAlert).where(WeatherAlert.aoi_id.in_(list(aois)))
        if status_filter:
            q = q.where(WeatherAlert.status == status_filter)
        items = list((await db.execute(q.order_by(WeatherAlert.status, WeatherAlert.severity.desc(), WeatherAlert.last_seen_at.desc()))).scalars())
        states = {s.aoi_id: s for s in (await db.execute(select(WeatherAoiState).where(WeatherAoiState.aoi_id.in_(list(aois))))).scalars()}
    active = {}
    for a in items:
        if a.status == "active":
            active[a.aoi_id] = active.get(a.aoi_id, 0) + 1
    return WeatherAlertList(
        configured=OpenWeatherAlerts().configured,
        items=[_out(a, aois[a.aoi_id].name) for a in items],
        aois=[AoiWeatherState(aoi_id=i, aoi_name=a.name, last_checked_at=(states[i].last_checked_at if i in states else None),
                              last_status=(states[i].last_status if i in states else None), last_error=(states[i].last_error if i in states else None),
                              alert_count=active.get(i, 0), monitoring=(states[i].monitoring if i in states else False)) for i, a in aois.items()])


@router.post("/refresh", response_model=RefreshOut)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_user_or_admin)):
    """Fetch current alerts for the AOI from OpenWeather and reconcile them with stored ones (rate-guarded unless ``force``)."""
    aoi = await _load_aoi(db, body.aoi_id, user, write=True)
    if body.source and body.source not in SOURCES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"source must be one of {sorted(SOURCES)}")
    bad = [t for t in (body.tags or []) if t not in TAGS]
    if bad:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown tag(s): {bad}")
    try:
        res = await refresh_aoi(db, aoi, force=body.force, source=body.source, tags=body.tags, lookahead_hours=body.lookahead_hours)
    except AoiGeometryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "bad_aoi", "message": str(exc)}) from exc
    except ProviderError as exc:
        raise _provider_http(exc) from exc
    rows = (await db.execute(select(WeatherAlert).where(WeatherAlert.aoi_id == aoi.id, WeatherAlert.status == "active")
                             .order_by(WeatherAlert.severity.desc(), WeatherAlert.last_seen_at.desc()))).scalars().all()
    return RefreshOut(aoi_id=aoi.id, checked_at=res.checked_at, cached=res.cached, new=res.new, updated=res.updated, unchanged=res.unchanged,
                      expired=res.expired, total_active=res.total_active, items=[_out(a, aoi.name) for a in rows])


@router.patch("/aois/{aoi_id}/monitoring", response_model=AoiWeatherState)
async def set_monitoring(aoi_id: uuid.UUID, body: MonitoringRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_user_or_admin)):
    aoi = await _load_aoi(db, aoi_id, user, write=True)
    st = await db.get(WeatherAoiState, aoi.id)
    if st is None:
        st = WeatherAoiState(aoi_id=aoi.id)
        db.add(st)
    st.monitoring = body.enabled
    await db.commit()
    n = await db.scalar(select(func.count(WeatherAlert.id)).where(WeatherAlert.aoi_id == aoi.id, WeatherAlert.status == "active")) or 0
    return AoiWeatherState(aoi_id=aoi.id, aoi_name=aoi.name, last_checked_at=st.last_checked_at, last_status=st.last_status, last_error=st.last_error,
                           alert_count=n, monitoring=st.monitoring)


@router.get("/events", response_model=list[WeatherEventOut])
async def list_events(unread: bool = False, limit: int = Query(default=50, ge=1, le=200), db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_authenticated_user)):
    """In-app notification inbox: one entry per NEW or MATERIALLY CHANGED alert (never for unchanged re-fetches)."""
    q = (select(WeatherAlertEvent).join(AreaOfInterest, AreaOfInterest.id == WeatherAlertEvent.aoi_id)
         .join(Project, Project.id == AreaOfInterest.project_id).where(access.readable_projects_clause(user)))
    if unread:
        q = q.where(WeatherAlertEvent.read_at.is_(None))
    return list((await db.execute(q.order_by(WeatherAlertEvent.created_at.desc()).limit(limit))).scalars())


@router.post("/events/read")
async def mark_events_read(body: EventsRead, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    visible = (select(WeatherAlertEvent.id).join(AreaOfInterest, AreaOfInterest.id == WeatherAlertEvent.aoi_id)
               .join(Project, Project.id == AreaOfInterest.project_id).where(access.readable_projects_clause(user)))
    cond = WeatherAlertEvent.id.in_(visible)
    if not body.all:
        cond = cond & WeatherAlertEvent.id.in_(body.ids or [])
    res = await db.execute(update(WeatherAlertEvent).where(cond, WeatherAlertEvent.read_at.is_(None)).values(read_at=func.now()))
    await db.commit()
    return {"marked_read": res.rowcount}
