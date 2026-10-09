"""Approved analytics operations. All numbers come from parameterized SQL / PostGIS over stored results.

Each operation returns an ``OpResult``: structured ``data`` plus deterministic ``facts`` (strings with the measured values),
``caveats`` and ``references`` to real detections. Nothing here calls a model.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import Float, and_, case, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisJob, ChangeFeature, Project, Region, User
from app.services import access

SEV_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
BUILT_CATEGORIES = ("building_change",)
VEG_CATEGORIES = ("vegetation_decrease", "vegetation_increase", "vegetation_change")


@dataclass
class OpResult:
    data: dict[str, Any]
    facts: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    references: list[dict[str, Any]] = field(default_factory=list)
    headline: str = ""


def _ha(m2: float | None) -> str:
    m2 = m2 or 0.0
    if m2 >= 1e6:
        return f"{m2 / 1e6:,.2f} km2"
    if m2 >= 1e4:
        return f"{m2 / 1e4:,.1f} ha"
    return f"{m2:,.0f} m2"


def _label(c: str) -> str:
    return c.replace("_", " ")


async def get_job(db: AsyncSession, user: User, analysis_id: uuid.UUID) -> AnalysisJob:
    job = await access.load_analysis(db, analysis_id, user)
    return job


def _feature_ref(f: ChangeFeature, lon: float, lat: float, label: str | None = None) -> dict[str, Any]:
    return {"kind": "feature", "id": f.id, "label": label or f"#{f.seq} {_label(f.category)} ({_ha(f.area_m2)})",
            "centroid": [lon, lat], "analysis_id": f.analysis_id}


def _cent():
    return func.ST_X(ChangeFeature.centroid), func.ST_Y(ChangeFeature.centroid)


async def summarize_analysis(db: AsyncSession, job: AnalysisJob, n: int = 5) -> OpResult:
    F = ChangeFeature
    rows = (await db.execute(select(F.category, F.severity, func.count(), func.sum(F.area_m2), func.avg(F.magnitude), func.avg(F.confidence))
                             .where(F.analysis_id == job.id).group_by(F.category, F.severity))).all()
    total_n = sum(r[2] for r in rows)
    total_area = float(sum((r[3] or 0) for r in rows))
    by_cat: dict[str, dict] = {}
    by_sev: dict[str, dict] = {}
    for cat, sev, c, a, _m, _cf in rows:
        by_cat.setdefault(cat, {"count": 0, "area_m2": 0.0})
        by_cat[cat]["count"] += c; by_cat[cat]["area_m2"] += float(a or 0)
        by_sev.setdefault(sev, {"count": 0, "area_m2": 0.0})
        by_sev[sev]["count"] += c; by_sev[sev]["area_m2"] += float(a or 0)
    analysed = (job.summary or {}).get("analyzed_area_m2")
    top = (await db.execute(select(F, *_cent()).where(F.analysis_id == job.id).order_by(F.area_m2.desc()).limit(n))).all()
    unreviewed = await db.scalar(select(func.count()).where(F.analysis_id == job.id, F.review_status == "unreviewed").select_from(F)) or 0
    facts = [f"{total_n} change polygon(s) covering {_ha(total_area)} between {job.before_date:%Y-%m-%d} and {job.after_date:%Y-%m-%d}"
             if job.before_date and job.after_date else f"{total_n} change polygon(s) covering {_ha(total_area)} (acquisition dates unknown)"]
    if analysed:
        facts.append(f"{100 * total_area / analysed:.2f}% of the {_ha(analysed)} analysed area changed")
    for sev in ("critical", "high", "medium", "low"):
        if sev in by_sev:
            facts.append(f"{by_sev[sev]['count']} {sev}-severity detection(s), {_ha(by_sev[sev]['area_m2'])}")
    for cat, v in sorted(by_cat.items(), key=lambda kv: -kv[1]["area_m2"]):
        facts.append(f"{_label(cat)}: {v['count']} polygon(s), {_ha(v['area_m2'])}")
    facts.append(f"{unreviewed} detection(s) not yet human-reviewed")
    head = (f"The analysis '{job.name}' found {total_n} change polygon(s) totalling {_ha(total_area)}." if total_n
            else f"The analysis '{job.name}' found no change above the threshold after filtering (a valid result, not an error).")
    caveats = ["Detections are observed image differences; categories and severity are heuristic and need human verification."]
    if job.is_demo:
        caveats.insert(0, "This is DEMO data computed from synthetic imagery.")
    return OpResult(
        data={"analysis_id": str(job.id), "feature_count": total_n, "total_changed_area_m2": total_area, "analyzed_area_m2": analysed,
              "by_category": by_cat, "by_severity": by_sev, "unreviewed": unreviewed, "method": job.method,
              "before_date": job.before_date, "after_date": job.after_date},
        facts=facts, caveats=caveats, headline=head,
        references=[_feature_ref(f, x, y) for f, x, y in top] + [{"kind": "analysis", "id": job.id, "label": job.name}])


async def largest_changes(db: AsyncSession, job: AnalysisJob, n: int = 5, category: str | None = None, min_severity: str | None = None,
                          order: str = "area") -> OpResult:
    F = ChangeFeature
    q = select(F, *_cent()).where(F.analysis_id == job.id)
    if category:
        q = q.where(F.category == category)
    if min_severity:
        q = q.where(F.severity.in_([k for k, v in SEV_RANK.items() if v >= SEV_RANK[min_severity]]))
    sev_rank = case(*[(F.severity == k, v) for k, v in SEV_RANK.items()], else_=0)
    q = q.order_by(*( [sev_rank.desc(), F.area_m2.desc()] if order == "severity" else [F.area_m2.desc()])).limit(n)
    rows = (await db.execute(q)).all()
    items = [{"id": str(f.id), "seq": f.seq, "category": f.category, "severity": f.severity, "area_m2": f.area_m2, "magnitude": f.magnitude,
              "confidence": f.confidence, "centroid": [x, y]} for f, x, y in rows]
    facts = [f"#{i['seq']}: {_label(i['category'])}, {_ha(i['area_m2'])}, severity {i['severity']}" for i in items]
    scope = (f" {_label(category)}" if category else "") + (f" with severity >= {min_severity}" if min_severity else "")
    head = f"Top {len(items)}{scope} detection(s) by {'severity then ' if order == 'severity' else ''}area in '{job.name}'." if items else f"No{scope} detections in '{job.name}'."
    return OpResult(data={"items": items, "order": order}, facts=facts, headline=head,
                    caveats=["Severity is a heuristic priority tier, not a probability."], references=[_feature_ref(f, x, y) for f, x, y in rows])


async def changes_by_region(db: AsyncSession, job: AnalysisJob, region_id: uuid.UUID | None = None) -> OpResult:
    F = ChangeFeature
    inter_area = func.ST_Area(cast(func.ST_Intersection(F.geometry, Region.geometry), Geography))
    q = (select(Region.id, Region.name, func.count(F.id), func.sum(inter_area))
         .join(F, func.ST_Intersects(F.geometry, Region.geometry)).where(F.analysis_id == job.id)
         .group_by(Region.id, Region.name).order_by(func.sum(inter_area).desc()))
    if region_id:
        q = q.where(Region.id == region_id)
    rows = (await db.execute(q)).all()
    items = [{"region_id": str(r[0]), "region": r[1], "feature_count": r[2], "changed_area_m2": float(r[3] or 0)} for r in rows]
    facts = [f"{i['region']}: {i['feature_count']} polygon(s) intersect it, {_ha(i['changed_area_m2'])} of change inside the region" for i in items]
    head = (f"{len(items)} monitored region(s) contain detected change; the largest is {items[0]['region']} ({_ha(items[0]['changed_area_m2'])})."
            if items else "No detected change intersects any monitored region.")
    return OpResult(data={"regions": items}, facts=facts, headline=head,
                    caveats=["Area is measured only inside each region's boundary (geodesic)."],
                    references=[{"kind": "region", "id": uuid.UUID(i["region_id"]), "label": i["region"]} for i in items[:10]])


def _dist_text(d: float) -> str:
    return "inside" if d == 0 else f"{d:,.0f} m from"


async def near_boundary(db: AsyncSession, job: AnalysisJob, distance_m: float = 1000.0, min_severity: str = "high", region_id: uuid.UUID | None = None) -> OpResult:
    F = ChangeFeature
    q = (select(F, Region.name, Region.id, func.ST_Distance(cast(F.geometry, Geography), cast(Region.geometry, Geography)), *_cent())
         .join(Region, func.ST_DWithin(cast(F.geometry, Geography), cast(Region.geometry, Geography), distance_m))
         .where(F.analysis_id == job.id, F.severity.in_([k for k, v in SEV_RANK.items() if v >= SEV_RANK[min_severity]]))
         .order_by(F.area_m2.desc()).limit(50))
    if region_id:
        q = q.where(Region.id == region_id)
    rows = (await db.execute(q)).all()
    items = [{"id": str(r[0].id), "seq": r[0].seq, "region": r[1], "distance_m": float(r[3]), "area_m2": r[0].area_m2, "severity": r[0].severity, "centroid": [r[4], r[5]]} for r in rows]
    facts = [f"#{i['seq']} ({i['severity']}, {_ha(i['area_m2'])}) is {_dist_text(i['distance_m'])} {i['region']}" for i in items]
    head = f"{len(items)} detection(s) with severity >= {min_severity} lie within {distance_m:,.0f} m of a monitored boundary." if items else f"No detection with severity >= {min_severity} lies within {distance_m:,.0f} m of a monitored boundary."
    return OpResult(data={"items": items, "distance_m": distance_m, "min_severity": min_severity}, facts=facts, headline=head,
                    caveats=["Distances are geodesic, measured to the region polygon (0 = inside)."],
                    references=[_feature_ref(r[0], r[4], r[5]) for r in rows[:12]])


async def needs_review(db: AsyncSession, job: AnalysisJob, n: int = 10) -> OpResult:
    F = ChangeFeature
    sev_rank = case(*[(F.severity == k, v) for k, v in SEV_RANK.items()], else_=0)
    rows = (await db.execute(select(F, *_cent()).where(F.analysis_id == job.id, F.review_status == "unreviewed")
                             .order_by(sev_rank.desc(), F.area_m2.desc()).limit(n))).all()
    total = await db.scalar(select(func.count()).select_from(F).where(F.analysis_id == job.id, F.review_status == "unreviewed")) or 0
    counts = {r[0]: r[1] for r in (await db.execute(select(F.review_status, func.count()).where(F.analysis_id == job.id).group_by(F.review_status))).all()}
    facts = [f"{total} detection(s) are unreviewed ({counts.get('confirmed', 0)} confirmed, {counts.get('rejected', 0)} rejected)"]
    facts += [f"#{f.seq}: {f.severity}, {_label(f.category)}, {_ha(f.area_m2)}" for f, _, _ in rows]
    return OpResult(data={"unreviewed": total, "counts": counts, "next": [str(f.id) for f, _, _ in rows]}, facts=facts,
                    headline=f"{total} detection(s) still need human review; the highest-priority ones are listed.",
                    caveats=["Priority = severity tier then area. It orders the review queue; it does not decide what is real."],
                    references=[_feature_ref(f, x, y) for f, x, y in rows])


async def vegetation_summary(db: AsyncSession, job: AnalysisJob) -> OpResult:
    F = ChangeFeature
    rows = (await db.execute(select(F.category, func.count(), func.sum(F.area_m2), func.avg(F.delta_ndvi)).where(F.analysis_id == job.id, F.category.in_(VEG_CATEGORIES)).group_by(F.category))).all()
    ndvi = (job.summary or {}).get("ndvi")
    items = {r[0]: {"count": r[1], "area_m2": float(r[2] or 0), "mean_delta_ndvi": r[3]} for r in rows}
    facts = [f"{_label(k)}: {v['count']} polygon(s), {_ha(v['area_m2'])}, mean dNDVI {v['mean_delta_ndvi']:+.2f}" for k, v in items.items() if v["mean_delta_ndvi"] is not None]
    if ndvi:
        facts.append(f"Scene mean NDVI {ndvi['before_mean']:.2f} (before) -> {ndvi['after_mean']:.2f} (after) over valid pixels")
    caveats = ["NDVI change is a proxy for vegetation vigour; a drop can be clearing, senescence, flooding or residual cloud."]
    if not items and not ndvi:
        caveats.append("This analysis has no NDVI-based classification (imagery without red + NIR bands, or no vegetation change detected).")
    loss = items.get("vegetation_decrease", {}).get("area_m2", 0.0)
    gain = items.get("vegetation_increase", {}).get("area_m2", 0.0)
    head = (f"Vegetation decreased over {_ha(loss)} and increased over {_ha(gain)} in '{job.name}'." if items else f"No NDVI-classified vegetation change in '{job.name}'.")
    return OpResult(data={"by_category": items, "ndvi": ndvi}, facts=facts, headline=head, caveats=caveats)


async def built_up_change(db: AsyncSession, job: AnalysisJob) -> OpResult:
    F = ChangeFeature
    row = (await db.execute(select(func.count(), func.sum(F.area_m2)).where(F.analysis_id == job.id, F.category.in_(BUILT_CATEGORIES)))).one()
    n, area = row[0], float(row[1] or 0)
    supported = (job.method == "learned_siamese")
    if not supported:
        return OpResult(data={"supported": False, "built_up_area_m2": None},
                        headline=f"'{job.name}' used the '{job.method}' method, which cannot classify built-up change, so no built-up area can be reported.",
                        facts=[f"{(await db.scalar(select(func.count()).select_from(F).where(F.analysis_id == job.id))) or 0} unclassified change polygon(s) exist; none is labelled built-up"],
                        caveats=["Built-up area is only reported when the learned building-change model produced the detections, and then as a model inference."])
    return OpResult(data={"supported": True, "count": n, "built_up_area_m2": area}, facts=[f"{n} model-inferred building-change polygon(s), {_ha(area)}"],
                    headline=f"The learned model inferred building change over {_ha(area)} ({n} polygon(s)).",
                    caveats=["Model-inferred on imagery similar to its training data; not validated for this scene. Verify before use."])


async def confidence_distribution(db: AsyncSession, job: AnalysisJob) -> OpResult:
    F = ChangeFeature
    has_conf = (job.processing or {}).get("detection", {}).get("confidence_kind")
    col = F.confidence if has_conf else F.magnitude
    bins = [(0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0001)]
    out = []
    for lo, hi in bins:
        c, a = (await db.execute(select(func.count(), func.coalesce(func.sum(F.area_m2), 0.0)).where(F.analysis_id == job.id, col >= lo, col < hi))).one()
        out.append({"bin": f"{lo:.2f}-{min(hi, 1.0):.2f}", "count": c, "area_m2": float(a)})
    kind = "model score (uncalibrated probability)" if has_conf else "change magnitude (0-1)"
    return OpResult(data={"metric": kind, "bins": out}, facts=[f"{b['bin']}: {b['count']} polygon(s), {_ha(b['area_m2'])}" for b in out],
                    headline=f"Distribution of {kind} across the detections in '{job.name}'.",
                    caveats=["The baseline method has no confidence estimate; magnitude is shown instead." if not has_conf else "Model scores are not calibrated probabilities."])


async def compare_analyses(db: AsyncSession, a: AnalysisJob, b: AnalysisJob, overlap: float = 0.5) -> OpResult:
    """A = earlier run, B = later run of the same area. Classifies B's features as persistent (overlap with an A feature) or new."""
    from sqlalchemy.orm import aliased

    FA, FB = aliased(ChangeFeature), ChangeFeature
    inter = func.ST_Area(func.ST_Intersection(FB.geometry, FA.geometry))
    smaller = func.least(func.ST_Area(FB.geometry), func.ST_Area(FA.geometry))
    persistent_ids = select(FB.id).join(FA, and_(func.ST_Intersects(FB.geometry, FA.geometry), (inter / func.nullif(smaller, 0)) >= overlap)).where(FB.analysis_id == b.id, FA.analysis_id == a.id).distinct()
    n_persist = await db.scalar(select(func.count()).select_from(persistent_ids.subquery())) or 0
    totals = {}
    for key, job in (("a", a), ("b", b)):
        n, area = (await db.execute(select(func.count(), func.coalesce(func.sum(ChangeFeature.area_m2), 0.0)).where(ChangeFeature.analysis_id == job.id))).one()
        totals[key] = {"name": job.name, "count": n, "area_m2": float(area), "after_date": job.after_date}
    new_n = totals["b"]["count"] - n_persist
    new_area = float(await db.scalar(select(func.coalesce(func.sum(FB.area_m2), 0.0)).where(FB.analysis_id == b.id, FB.id.notin_(persistent_ids))) or 0)
    d_area = totals["b"]["area_m2"] - totals["a"]["area_m2"]
    facts = [f"{a.name}: {totals['a']['count']} polygon(s), {_ha(totals['a']['area_m2'])}", f"{b.name}: {totals['b']['count']} polygon(s), {_ha(totals['b']['area_m2'])}",
             f"Change in total changed area: {'+' if d_area >= 0 else '-'}{_ha(abs(d_area))}", f"{n_persist} polygon(s) in the later run overlap (>= {overlap:.0%}) an earlier detection; {new_n} are new ({_ha(new_area)})"]
    caveats = ["Runs may differ in imagery, dates, method or thresholds; compare like with like before concluding anything about real-world trends."]
    if a.method != b.method:
        caveats.insert(0, f"The two runs used different methods ({a.method} vs {b.method}).")
    return OpResult(data={"earlier": totals["a"], "later": totals["b"], "area_delta_m2": d_area, "persistent": n_persist, "new": new_n, "new_area_m2": new_area}, facts=facts,
                    headline=f"The later run has {abs(d_area) / 1e4:,.1f} ha {'more' if d_area >= 0 else 'less'} changed area; {new_n} of its {totals['b']['count']} polygon(s) are new.",
                    caveats=caveats, references=[{"kind": "analysis", "id": a.id, "label": a.name}, {"kind": "analysis", "id": b.id, "label": b.name}])


async def history(db: AsyncSession, user: User, project_id: uuid.UUID | None) -> OpResult:
    q = (select(AnalysisJob).join(Project, Project.id == AnalysisJob.project_id).where(access.readable_projects_clause(user), AnalysisJob.status == "completed")
         .order_by(AnalysisJob.after_date.nulls_last(), AnalysisJob.created_at))
    if project_id:
        q = q.where(AnalysisJob.project_id == project_id)
    jobs = list((await db.execute(q)).scalars())
    pts = [{"analysis_id": str(j.id), "name": j.name, "after_date": j.after_date, "changed_area_m2": (j.summary or {}).get("total_changed_area_m2"),
            "feature_count": (j.summary or {}).get("feature_count"), "is_demo": j.is_demo} for j in jobs]
    if len(pts) < 2:
        return OpResult(data={"points": pts}, headline="Only one (or no) completed analysis exists, so there is no history to compare.", facts=[],
                        caveats=["A trend needs at least two completed analyses; GeoTrace does not extrapolate or invent history."])
    facts = [f"{p['name']} ({p['after_date']:%Y-%m-%d}): {_ha(p['changed_area_m2'])}, {p['feature_count']} polygon(s)" if p["after_date"] else f"{p['name']}: {_ha(p['changed_area_m2'])}" for p in pts]
    return OpResult(data={"points": pts}, facts=facts, headline=f"{len(pts)} completed analyses, ordered by their 'after' date.",
                    caveats=["Analyses may cover different areas, sensors and methods; they are listed, not statistically trended."],
                    references=[{"kind": "analysis", "id": uuid.UUID(p["analysis_id"]), "label": p["name"]} for p in pts[-8:]])


async def explain_feature(db: AsyncSession, job: AnalysisJob, feature_id: uuid.UUID) -> OpResult:
    F = ChangeFeature
    row = (await db.execute(select(F, *_cent()).where(F.id == feature_id, F.analysis_id == job.id))).first()
    if row is None:
        return OpResult(data={}, headline="That detection was not found in this analysis.")
    f, x, y = row
    rank = (await db.scalar(select(func.count()).select_from(F).where(F.analysis_id == job.id, F.area_m2 > f.area_m2)) or 0) + 1
    total = await db.scalar(select(func.count()).select_from(F).where(F.analysis_id == job.id)) or 1
    det = (job.processing or {}).get("detection", {})
    facts = [f"Area {f.area_m2:,.0f} m2 ({_ha(f.area_m2)}), perimeter {f.perimeter_m:,.0f} m; rank {rank} of {total} by area",
             f"Category '{_label(f.category)}' ({f.category_basis.replace('_', ' ')}); severity {f.severity}", f"Magnitude {f.magnitude:.2f} ({str(det.get('magnitude_kind', '')).replace('_', ' ')})",
             f"Location {y:.5f}, {x:.5f}", *[f"Severity rule: {r}" for r in (f.severity_reasons or [])]]
    if f.confidence is not None:
        facts.append(f"Model score {f.confidence:.2f} (uncalibrated)")
    if f.delta_ndvi is not None:
        facts.append(f"Mean dNDVI {f.delta_ndvi:+.2f}")
    if f.distance_to_boundary_m is not None:
        facts.append(f"{f.distance_to_boundary_m:,.0f} m from the nearest monitored boundary")
    facts.append(f"Review status: {f.review_status}")
    head = f"Change #{f.seq} is a {f.severity}-priority {_label(f.category)} of {_ha(f.area_m2)}."
    return OpResult(data={"feature_id": str(f.id), "seq": f.seq, "area_m2": f.area_m2, "severity": f.severity, "category": f.category}, facts=facts, headline=head,
                    caveats=["This is an observed difference between two images. It is not proof of what caused it."], references=[_feature_ref(f, x, y)])


async def overview(db: AsyncSession, user: User, project_id: uuid.UUID | None = None) -> dict[str, Any]:
    """Cross-analysis dashboard numbers (all from stored results)."""
    base = (select(AnalysisJob).join(Project, Project.id == AnalysisJob.project_id).where(access.readable_projects_clause(user)))
    if project_id:
        base = base.where(AnalysisJob.project_id == project_id)
    jobs = list((await db.execute(base.order_by(AnalysisJob.created_at))).scalars())
    done = [j for j in jobs if j.status == "completed"]
    ids = [j.id for j in done]
    F = ChangeFeature
    sev, cat = {}, {}
    if ids:
        sev = {r[0]: {"count": r[1], "area_m2": float(r[2] or 0)} for r in (await db.execute(select(F.severity, func.count(), func.sum(F.area_m2)).where(F.analysis_id.in_(ids)).group_by(F.severity))).all()}
        cat = {r[0]: {"count": r[1], "area_m2": float(r[2] or 0)} for r in (await db.execute(select(F.category, func.count(), func.sum(F.area_m2)).where(F.analysis_id.in_(ids)).group_by(F.category))).all()}
    return {
        "analyses": {"total": len(jobs), "completed": len(done), "running": sum(1 for j in jobs if j.status not in ("completed", "failed", "cancelled")), "failed": sum(1 for j in jobs if j.status == "failed")},
        "analyzed_area_m2": sum((j.summary or {}).get("analyzed_area_m2") or 0 for j in done),
        "changed_area_m2": sum((j.summary or {}).get("total_changed_area_m2") or 0 for j in done),
        "feature_count": sum((j.summary or {}).get("feature_count") or 0 for j in done),
        "by_severity": sev, "by_category": cat,
        "series": [{"analysis_id": str(j.id), "name": j.name, "date": (j.after_date or j.created_at), "changed_area_m2": (j.summary or {}).get("total_changed_area_m2"),
                    "feature_count": (j.summary or {}).get("feature_count"), "analyzed_area_m2": (j.summary or {}).get("analyzed_area_m2"), "method": j.method, "is_demo": j.is_demo,
                    "ndvi": (j.summary or {}).get("ndvi")} for j in done],
        "has_demo": any(j.is_demo for j in jobs),
    }
