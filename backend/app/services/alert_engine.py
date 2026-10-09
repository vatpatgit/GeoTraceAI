"""Deterministic, rule-based alert evaluation run when an analysis completes (or on demand).

Properties required by the PRD:
  * every incident links the triggering rule, analysis and feature, and stores the evidence that matched;
  * idempotent: ``UNIQUE (rule_id, feature_id)`` + ``ON CONFLICT DO NOTHING`` makes retries safe;
  * optional spatial de-duplication so a persistent change is not re-alerted on every new analysis;
  * no claim of continuous monitoring: this only evaluates *completed analyses*.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (AlertIncident, AlertRule, AnalysisJob, AreaOfInterest, ChangeFeature, Project, Region, User)
from app.services.access import is_admin

logger = logging.getLogger(__name__)

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
MAX_INCIDENTS_PER_RULE_PER_ANALYSIS = 500


def category_label(cat: str) -> str:
    return cat.replace("_", " ")


def _geog(col):
    return cast(col, Geography)


def _geom_subquery(model, row_id):
    """Geometry of a row as an in-database scalar subquery (never round-trip geometries through bind parameters)."""
    return select(model.geometry).where(model.id == row_id).scalar_subquery()


async def _owner_can_see(db: AsyncSession, rule: AlertRule, project: Project) -> bool:
    if project.visibility == "shared" or project.owner_id == rule.owner_id:
        return True
    owner = await db.get(User, rule.owner_id)
    return bool(owner and owner.is_active and is_admin(owner))


def _rule_snapshot(rule: AlertRule) -> dict[str, Any]:
    return {
        "rule_id": str(rule.id), "name": rule.name, "region_id": str(rule.region_id) if rule.region_id else None,
        "aoi_id": str(rule.aoi_id) if rule.aoi_id else None, "region_relation": rule.region_relation, "distance_m": rule.distance_m,
        "categories": rule.categories, "min_area_m2": rule.min_area_m2, "min_severity": rule.min_severity,
        "min_magnitude": rule.min_magnitude, "min_confidence": rule.min_confidence,
        "dedup_mode": rule.dedup_mode, "dedup_window_days": rule.dedup_window_days, "dedup_overlap": rule.dedup_overlap,
    }


async def evaluate_analysis(db: AsyncSession, job: AnalysisJob, *, rule_ids: list | None = None) -> dict[str, Any]:
    """Evaluate all enabled, in-scope rules against ``job``'s features. Returns counts (never raises for one bad rule)."""
    project = await db.get(Project, job.project_id)
    stmt = select(AlertRule).where(AlertRule.enabled.is_(True), or_(AlertRule.project_id.is_(None), AlertRule.project_id == job.project_id))
    if rule_ids:
        stmt = stmt.where(AlertRule.id.in_(rule_ids))
    rules = list((await db.execute(stmt)).scalars().all())
    result = {"rules_evaluated": 0, "incidents_created": 0, "suppressed_duplicates": 0, "truncated_rules": [], "errors": []}
    detected_at = job.finished_at or datetime.now(timezone.utc)

    for rule in rules:
        if project is None or not await _owner_can_see(db, rule, project):
            continue
        try:
            created, suppressed, truncated = await _evaluate_rule(db, rule, job, detected_at)
            rule.last_evaluated_at = datetime.now(timezone.utc)
            await db.commit()
            result["rules_evaluated"] += 1
            result["incidents_created"] += created
            result["suppressed_duplicates"] += suppressed
            if truncated:
                result["truncated_rules"].append(str(rule.id))
        except Exception as exc:  # one broken rule must not block others
            await db.rollback()
            logger.exception("alert rule %s failed", rule.id)
            result["errors"].append({"rule_id": str(rule.id), "error": str(exc)[:200]})
    return result


async def _evaluate_rule(db: AsyncSession, rule: AlertRule, job: AnalysisJob, detected_at: datetime) -> tuple[int, int, bool]:
    F = ChangeFeature
    conds = [F.analysis_id == job.id, F.area_m2 >= rule.min_area_m2]
    if SEVERITY_RANK[rule.min_severity] > 0:
        conds.append(F.severity.in_([k for k, v in SEVERITY_RANK.items() if v >= SEVERITY_RANK[rule.min_severity]]))
    if rule.categories:
        conds.append(F.category.in_(rule.categories))
    if rule.min_magnitude is not None:
        conds.append(F.magnitude >= rule.min_magnitude)
    if rule.min_confidence is not None:
        conds.append(F.confidence.is_not(None))  # a method without a confidence cannot satisfy a confidence rule
        conds.append(F.confidence >= rule.min_confidence)

    scope_geoms: list[tuple[str, str, Any]] = []
    if rule.region_id:
        region = await db.get(Region, rule.region_id)
        if region is None:
            return 0, 0, False
        scope_geoms.append(("region", region.name, _geom_subquery(Region, region.id)))
    if rule.aoi_id:
        aoi = await db.get(AreaOfInterest, rule.aoi_id)
        if aoi is None:
            return 0, 0, False
        scope_geoms.append(("aoi", aoi.name, _geom_subquery(AreaOfInterest, aoi.id)))
    dist_exprs = []
    for kind, name, geom in scope_geoms:
        if rule.region_relation == "within_distance" and rule.distance_m:
            conds.append(func.ST_DWithin(_geog(F.geometry), _geog(geom), rule.distance_m))
        else:
            conds.append(func.ST_Intersects(F.geometry, geom))
        dist_exprs.append(func.ST_Distance(_geog(F.geometry), _geog(geom)))

    order = [F.area_m2.desc()]
    cols = [F, func.ST_X(F.centroid).label("cx"), func.ST_Y(F.centroid).label("cy")]
    if dist_exprs:
        cols.append(dist_exprs[0].label("scope_distance_m"))
    q = select(*cols).where(and_(*conds)).order_by(*order).limit(MAX_INCIDENTS_PER_RULE_PER_ANALYSIS + 1)
    rows = (await db.execute(q)).all()
    truncated = len(rows) > MAX_INCIDENTS_PER_RULE_PER_ANALYSIS
    rows = rows[:MAX_INCIDENTS_PER_RULE_PER_ANALYSIS]

    created = suppressed = 0
    window_start = datetime.now(timezone.utc) - timedelta(days=rule.dedup_window_days)
    for row in rows:
        f: ChangeFeature = row[0]
        if rule.dedup_mode == "spatial" and await _is_recent_duplicate(db, rule, f, window_start, job.id):
            suppressed += 1
            continue
        distance = getattr(row, "scope_distance_m", None)
        evidence = {
            "rule": _rule_snapshot(rule),
            "matched": {
                "area_m2": f.area_m2, "severity": f.severity, "category": f.category, "category_basis": f.category_basis,
                "magnitude": f.magnitude, "confidence": f.confidence, "distance_to_scope_m": distance,
                "scope": [{"kind": k, "name": n} for k, n, _ in scope_geoms], "severity_reasons": f.severity_reasons,
            },
            "analysis": {"id": str(job.id), "name": job.name, "method": job.method, "model_id": job.model_id,
                         "before_date": job.before_date.isoformat() if job.before_date else None,
                         "after_date": job.after_date.isoformat() if job.after_date else None, "is_demo": job.is_demo},
            "notice": "Observed image difference matched a configured rule; not a verified event.",
        }
        scope_txt = f" within scope '{scope_geoms[0][1]}'" if scope_geoms else ""
        title = f"{f.severity.upper()}: {category_label(f.category)} ({f.area_m2:,.0f} m2){scope_txt}"
        window = (f" between {job.before_date:%Y-%m-%d} and {job.after_date:%Y-%m-%d}" if job.before_date and job.after_date else "")
        conf_txt = f", model score {f.confidence:.2f} (uncalibrated)" if f.confidence is not None else ""
        message = (f"{f.area_m2:,.0f} m2 of {category_label(f.category)} ({f.category_basis.replace('_', ' ')}){window}{scope_txt}; "
                   f"severity {f.severity}{conf_txt}. Triggered by rule '{rule.name}'. Requires human verification.")
        stmt = pg_insert(AlertIncident).values(
            rule_id=rule.id, analysis_id=job.id, feature_id=f.id, severity=f.severity, category=f.category, status="open",
            title=title[:200], message=message, evidence=evidence, detected_at=detected_at,
        ).on_conflict_do_nothing(constraint="uq_alert_incident_rule_feature").returning(AlertIncident.id)
        inserted = (await db.execute(stmt)).first()
        if inserted:
            created += 1
    return created, suppressed, truncated


async def _is_recent_duplicate(db: AsyncSession, rule: AlertRule, f: ChangeFeature, since: datetime, current_analysis) -> bool:
    """True if this rule already raised an incident for a substantially overlapping feature from another analysis recently."""
    G2 = ChangeFeature
    from sqlalchemy.orm import aliased

    other = aliased(G2)
    mine = _geom_subquery(ChangeFeature, f.id)
    inter_area = func.ST_Area(func.ST_Intersection(mine, other.geometry))
    smaller = func.least(func.ST_Area(mine), func.ST_Area(other.geometry))
    q = (select(AlertIncident.id)
         .join(other, other.id == AlertIncident.feature_id)
         .where(AlertIncident.rule_id == rule.id, AlertIncident.created_at >= since, other.analysis_id != current_analysis,
                func.ST_Intersects(mine, other.geometry), (inter_area / func.nullif(smaller, 0)) >= rule.dedup_overlap)
         .limit(1))
    return (await db.execute(q)).first() is not None
