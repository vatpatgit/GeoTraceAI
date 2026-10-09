"""Alert rules (CRUD) and incidents (list / acknowledge / resolve)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_authenticated_user, require_user_or_admin
from app.database import get_db
from app.models import (AlertIncident, AlertRule, AnalysisJob, AreaOfInterest, ChangeFeature, Project, Region, User)
from app.schemas.alert import (AlertRuleCreate, AlertRuleOut, AlertRuleUpdate, IncidentOut, IncidentPage, IncidentUpdate)
from app.services import access

router = APIRouter()


# ------------------------------------------------------------------------------------------------- rules
async def _rule_out(db: AsyncSession, r: AlertRule) -> AlertRuleOut:
    n = await db.scalar(select(func.count(AlertIncident.id)).where(AlertIncident.rule_id == r.id)) or 0
    return AlertRuleOut(id=r.id, owner_id=r.owner_id, name=r.name, enabled=r.enabled, project_id=r.project_id, region_id=r.region_id,
                        aoi_id=r.aoi_id, region_relation=r.region_relation, distance_m=r.distance_m, categories=r.categories,
                        min_area_m2=r.min_area_m2, min_severity=r.min_severity, min_magnitude=r.min_magnitude,
                        min_confidence=r.min_confidence, dedup_mode=r.dedup_mode, dedup_window_days=r.dedup_window_days,
                        dedup_overlap=r.dedup_overlap, created_at=r.created_at, updated_at=r.updated_at,
                        last_evaluated_at=r.last_evaluated_at, incident_count=n)


async def _check_scope(db: AsyncSession, user: User, data: dict) -> None:
    if data.get("region_id") and await db.get(Region, data["region_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Region not found")
    if data.get("project_id"):
        await access.load_project(db, data["project_id"], user)
    if data.get("aoi_id"):
        aoi = await db.get(AreaOfInterest, data["aoi_id"])
        if aoi is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "AOI not found")
        await access.load_project(db, aoi.project_id, user)


@router.get("/rules", response_model=list[AlertRuleOut])
async def list_rules(db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    stmt = select(AlertRule).order_by(AlertRule.created_at.desc())
    if not access.is_admin(user):
        stmt = stmt.where(AlertRule.owner_id == user.id)
    return [await _rule_out(db, r) for r in (await db.execute(stmt)).scalars()]


@router.post("/rules", response_model=AlertRuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(body: AlertRuleCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_user_or_admin)):
    data = body.model_dump()
    await _check_scope(db, user, data)
    rule = AlertRule(owner_id=user.id, **data)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return await _rule_out(db, rule)


async def _load_rule(db: AsyncSession, rule_id: uuid.UUID, user: User) -> AlertRule:
    rule = await db.get(AlertRule, rule_id)
    if rule is None or not (access.is_admin(user) or rule.owner_id == user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert rule not found")
    return rule


@router.patch("/rules/{rule_id}", response_model=AlertRuleOut)
async def update_rule(rule_id: uuid.UUID, body: AlertRuleUpdate, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_user_or_admin)):
    rule = await _load_rule(db, rule_id, user)
    data = body.model_dump(exclude_unset=True)
    await _check_scope(db, user, data)
    for k, v in data.items():
        setattr(rule, k, v)
    if rule.region_relation == "within_distance" and not (rule.distance_m and (rule.region_id or rule.aoi_id)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "within_distance needs distance_m and a region or AOI.")
    await db.commit()
    await db.refresh(rule)
    return await _rule_out(db, rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_user_or_admin)):
    rule = await _load_rule(db, rule_id, user)
    await db.delete(rule)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------------------------------------- incidents
def _incident_select(user: User):
    stmt = (select(AlertIncident, AlertRule.name, AnalysisJob.name, AnalysisJob.is_demo, ChangeFeature.area_m2, ChangeFeature.confidence,
                   func.ST_X(ChangeFeature.centroid), func.ST_Y(ChangeFeature.centroid),
                   func.ST_XMin(ChangeFeature.geometry), func.ST_YMin(ChangeFeature.geometry),
                   func.ST_XMax(ChangeFeature.geometry), func.ST_YMax(ChangeFeature.geometry), AlertRule.region_id)
            .join(AlertRule, AlertRule.id == AlertIncident.rule_id)
            .join(AnalysisJob, AnalysisJob.id == AlertIncident.analysis_id)
            .join(ChangeFeature, ChangeFeature.id == AlertIncident.feature_id))
    if not access.is_admin(user):
        stmt = stmt.where(AlertRule.owner_id == user.id)
    return stmt


def _incident_out(row) -> IncidentOut:
    i: AlertIncident = row[0]
    return IncidentOut(id=i.id, rule_id=i.rule_id, rule_name=row[1], analysis_id=i.analysis_id, analysis_name=row[2], feature_id=i.feature_id,
                       severity=i.severity, category=i.category, status=i.status, title=i.title, message=i.message, evidence=i.evidence,
                       area_m2=row[4], confidence=row[5], centroid=[row[6], row[7]], bbox=[row[8], row[9], row[10], row[11]],
                       region_id=row[12], detected_at=i.detected_at, created_at=i.created_at, acknowledged_at=i.acknowledged_at,
                       resolved_at=i.resolved_at, resolution_note=i.resolution_note, is_demo=bool(row[3]))


@router.get("", response_model=IncidentPage)
@router.get("/", response_model=IncidentPage, include_in_schema=False)
async def list_incidents(
    status_: list[str] | None = Query(None, alias="status"),
    severity: list[str] | None = Query(None),
    category: list[str] | None = Query(None),
    rule_id: uuid.UUID | None = None,
    analysis_id: uuid.UUID | None = None,
    region_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_authenticated_user),
):
    stmt = _incident_select(user)
    if status_:
        stmt = stmt.where(AlertIncident.status.in_(status_))
    if severity:
        stmt = stmt.where(AlertIncident.severity.in_(severity))
    if category:
        stmt = stmt.where(AlertIncident.category.in_(category))
    if rule_id:
        stmt = stmt.where(AlertIncident.rule_id == rule_id)
    if analysis_id:
        stmt = stmt.where(AlertIncident.analysis_id == analysis_id)
    if region_id:
        stmt = stmt.where(AlertRule.region_id == region_id)
    if since:
        stmt = stmt.where(AlertIncident.detected_at >= since)
    if until:
        stmt = stmt.where(AlertIncident.detected_at <= until)
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    open_n = await db.scalar(select(func.count()).select_from(stmt.where(AlertIncident.status == "open").order_by(None).subquery())) or 0
    sev_rank = func.array_position(["critical", "high", "medium", "low"], AlertIncident.severity)
    rows = (await db.execute(stmt.order_by(AlertIncident.created_at.desc(), sev_rank).limit(limit).offset(offset))).all()
    return IncidentPage(total=total, open=open_n, limit=limit, offset=offset, items=[_incident_out(r) for r in rows])


@router.get("/stats")
async def incident_stats(db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    base = _incident_select(user).order_by(None).subquery()
    by_status = {r[0]: r[1] for r in (await db.execute(select(base.c.status, func.count()).group_by(base.c.status))).all()}
    by_sev = {r[0]: r[1] for r in (await db.execute(select(base.c.severity, func.count()).where(base.c.status != "resolved").group_by(base.c.severity))).all()}
    return {"by_status": by_status, "unresolved_by_severity": by_sev, "unresolved": sum(v for k, v in by_status.items() if k != "resolved")}


@router.get("/{incident_id}", response_model=IncidentOut)
async def get_incident(incident_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    row = (await db.execute(_incident_select(user).where(AlertIncident.id == incident_id))).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    return _incident_out(row)


@router.patch("/{incident_id}", response_model=IncidentOut)
async def update_incident(incident_id: uuid.UUID, body: IncidentUpdate, db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_user_or_admin)):
    row = (await db.execute(_incident_select(user).where(AlertIncident.id == incident_id))).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    inc: AlertIncident = row[0]
    now = datetime.now(timezone.utc)
    if body.status == "acknowledged":
        inc.status, inc.acknowledged_by, inc.acknowledged_at = "acknowledged", user.id, now
    elif body.status == "resolved":
        inc.status, inc.resolved_by, inc.resolved_at, inc.resolution_note = "resolved", user.id, now, body.resolution_note
        if inc.acknowledged_at is None:
            inc.acknowledged_by, inc.acknowledged_at = user.id, now
    else:  # reopen
        inc.status, inc.resolved_by, inc.resolved_at = "open", None, None
    await db.commit()
    row = (await db.execute(_incident_select(user).where(AlertIncident.id == incident_id))).first()
    return _incident_out(row)
