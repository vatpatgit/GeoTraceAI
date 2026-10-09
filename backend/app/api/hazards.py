"""Live hazard alerts (earthquakes, fire hotspots, storms) matched to the caller's AOIs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.auth.dependencies import require_authenticated_user
from app.config import settings
from app.database import get_db
from app.models import AreaOfInterest, HazardAlert, Project, User
from app.providers.base import ProviderError
from app.schemas.common import ApiModel, UtcDateTime
from app.services import access
from app.services import hazards as svc

router = APIRouter()


class HazardOut(ApiModel):
    id: uuid.UUID
    aoi_id: uuid.UUID
    aoi_name: str | None = None
    kind: str
    title: str
    severity: str
    lat: float
    lon: float
    distance_km: float
    occurred_at: UtcDateTime | None
    details: dict[str, Any]
    status: str
    first_seen_at: UtcDateTime
    last_seen_at: UtcDateTime
    read_at: UtcDateTime | None


class HazardRefreshIn(BaseModel):
    force: bool = False


class ReadIn(BaseModel):
    ids: list[uuid.UUID] | None = Field(default=None, max_length=500)
    all: bool = False


def _visible_aois(user: User):
    return select(AreaOfInterest).join(Project, Project.id == AreaOfInterest.project_id).where(access.readable_projects_clause(user))


@router.get("/status")
async def hazard_status(user: User = Depends(require_authenticated_user)):
    return {
        "enabled": settings.HAZARD_FEED_PROVIDER != "none", "provider": settings.HAZARD_FEED_PROVIDER, "scheduled_refresh_minutes": max(0, settings.HAZARD_REFRESH_MINUTES),
        "kinds": {
            "earthquake": {"min_magnitude": settings.HAZARD_QUAKE_MIN_MAG, "radius_km": settings.HAZARD_QUAKE_RADIUS_KM},
            "fire": {"radius_km": settings.HAZARD_FIRE_RADIUS_KM, "note": "satellite thermal anomalies (VIIRS), not confirmed fires"},
            "storm": {"radius_km": settings.HAZARD_STORM_RADIUS_KM},
        },
        "not_supported": {"air_quality": "the feed returned no stations, so its format could not be verified", "internet_outages": "country-level data cannot be matched to an AOI"},
        "max_age_hours": settings.HAZARD_MAX_AGE_HOURS,
    }


@router.get("", response_model=list[HazardOut])
async def list_hazards(kind: str | None = Query(default=None, pattern="^(earthquake|fire|storm)$"), unread: bool = False, include_expired: bool = False,
                       limit: int = Query(default=100, ge=1, le=300), db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    """Stored alerts for AOIs the caller can read (never calls the feed)."""
    q = (select(HazardAlert, AreaOfInterest.name).join(AreaOfInterest, AreaOfInterest.id == HazardAlert.aoi_id).join(Project, Project.id == AreaOfInterest.project_id)
         .where(access.readable_projects_clause(user)))
    if not include_expired:
        q = q.where(HazardAlert.status == "active")
    if kind:
        q = q.where(HazardAlert.kind == kind)
    if unread:
        q = q.where(HazardAlert.read_at.is_(None))
    rows = (await db.execute(q.order_by(HazardAlert.last_seen_at.desc(), HazardAlert.severity.desc()).limit(limit))).all()
    return [HazardOut.model_validate({**{c: getattr(h, c) for c in HazardOut.model_fields if c != "aoi_name"}, "aoi_name": n}) for h, n in rows]


@router.post("/refresh")
async def refresh(body: HazardRefreshIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    """Fetch the live feed (shared short cache) and match it against every AOI the caller can read."""
    aois = list((await db.execute(_visible_aois(user).limit(500))).scalars())
    try:
        sm = await svc.refresh_for(db, aois, force=body.force and access.can_write_role(user))
    except ProviderError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": str(exc)}) from exc
    return {"aois": sm.aois, "new": sm.new, "updated": sm.updated, "expired": sm.expired, "active": sm.active, "cached": sm.cached, "fetched": sm.fetched, "errors": sm.errors,
            "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}


@router.post("/read")
async def mark_read(body: ReadIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    visible = (select(HazardAlert.id).join(AreaOfInterest, AreaOfInterest.id == HazardAlert.aoi_id).join(Project, Project.id == AreaOfInterest.project_id)
               .where(access.readable_projects_clause(user)))
    cond = HazardAlert.id.in_(visible)
    if not body.all:
        cond = cond & HazardAlert.id.in_(body.ids or [])
    res = await db.execute(update(HazardAlert).where(cond, HazardAlert.read_at.is_(None)).values(read_at=func.now()))
    await db.commit()
    return {"marked_read": res.rowcount}
