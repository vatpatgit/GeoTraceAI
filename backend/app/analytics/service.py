"""Orchestrates a question -> approved operation -> grounded answer."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import llm, queries
from app.analytics.nl import SUGGESTIONS, QuerySpec, parse_question
from app.models import AnalysisJob, Project, Region, User
from app.schemas.analytics import AnalyticsQueryRequest, AnalyticsQueryResponse, Reference
from app.services import access


async def _default_analysis(db: AsyncSession, user: User, project_id: uuid.UUID | None) -> AnalysisJob | None:
    q = (select(AnalysisJob).join(Project, Project.id == AnalysisJob.project_id)
         .where(access.readable_projects_clause(user), AnalysisJob.status == "completed").order_by(AnalysisJob.created_at.desc()).limit(1))
    if project_id:
        q = q.where(AnalysisJob.project_id == project_id)
    return (await db.execute(q)).scalar_one_or_none()


async def _previous(db: AsyncSession, user: User, job: AnalysisJob) -> AnalysisJob | None:
    q = (select(AnalysisJob).where(AnalysisJob.project_id == job.project_id, AnalysisJob.status == "completed", AnalysisJob.id != job.id)
         .order_by(AnalysisJob.after_date.desc().nulls_last(), AnalysisJob.created_at.desc()))
    cands = list((await db.execute(q)).scalars())
    older = [c for c in cands if (c.after_date and job.after_date and c.after_date < job.after_date) or (not (c.after_date and job.after_date) and c.created_at < job.created_at)]
    return older[0] if older else None


def _refs(items: list[dict[str, Any]]) -> list[Reference]:
    out = []
    for r in items:
        try:
            out.append(Reference(kind=r["kind"], id=r["id"], label=r["label"], centroid=r.get("centroid"), analysis_id=r.get("analysis_id")))
        except (KeyError, ValidationError):
            continue
    return out


async def run_query(db: AsyncSession, user: User, req: AnalyticsQueryRequest) -> AnalyticsQueryResponse:
    regions = [(r.id, r.name) for r in (await db.execute(select(Region))).scalars()]
    notes: list[str] = []
    spec: QuerySpec | None = None
    if req.spec is not None:
        try:
            spec = QuerySpec(**req.spec)
        except ValidationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "bad_spec", "message": str(exc.errors()[0]["msg"])}) from exc
    elif req.question:
        spec, notes = parse_question(req.question, regions)
        if spec is None and llm.llm_enabled():
            raw = await llm.llm_parse(req.question, [n for _, n in regions])
            if raw:
                try:
                    name = raw.pop("region_name", None)
                    if name:
                        raw["region_id"] = next((rid for rid, n in regions if n.lower() == str(name).lower()), None)
                    spec = QuerySpec(**{k: v for k, v in raw.items() if v is not None})
                    notes.append("interpreted with the configured language model (validated against the approved operation schema)")
                except ValidationError:
                    spec = None
    if spec is None:
        return AnalyticsQueryResponse(
            question=req.question, interpreted_as={}, operation="none", understood=False, data={}, answer="I can only answer questions that map to the supported analyses of your stored results. I could not match this question to one.",
            answer_source="deterministic", measured_facts=[], caveats=[], references=[], suggestions=SUGGESTIONS)

    if spec.operation == "overview":
        data = await queries.overview(db, user, req.project_id)
        facts = [f"{data['analyses']['completed']} completed analysis(es), {data['feature_count']} polygon(s)", f"{queries._ha(data['changed_area_m2'])} changed of {queries._ha(data['analyzed_area_m2'])} analysed"]
        return AnalyticsQueryResponse(question=req.question, interpreted_as=spec.model_dump(mode="json", exclude_none=True), operation="overview", understood=True, data=data,
                                      answer=f"You have {data['analyses']['completed']} completed analysis(es) with {data['feature_count']} detected change polygon(s).", answer_source="deterministic",
                                      measured_facts=facts, caveats=["Demo data is included in these totals."] if data["has_demo"] else [], references=[])
    if spec.operation == "history":
        res = await queries.history(db, user, req.project_id)
        job = None
    else:
        aid = spec.analysis_id or req.analysis_id
        job = await queries.get_job(db, user, aid) if aid else await _default_analysis(db, user, req.project_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "no_analysis", "message": "There is no completed analysis to question yet."})
        if job.status != "completed":
            raise HTTPException(status.HTTP_409_CONFLICT, detail={"code": "not_completed", "message": "That analysis has not completed."})
        op = spec.operation
        if op == "summarize_analysis":
            res = await queries.summarize_analysis(db, job, spec.n)
        elif op == "largest_changes":
            res = await queries.largest_changes(db, job, spec.n, spec.category, spec.min_severity, spec.order)
        elif op == "changes_by_region":
            res = await queries.changes_by_region(db, job, spec.region_id)
        elif op == "near_boundary":
            res = await queries.near_boundary(db, job, spec.distance_m or 1000.0, spec.min_severity or "high", spec.region_id)
        elif op == "needs_review":
            res = await queries.needs_review(db, job, max(spec.n, 10))
        elif op == "vegetation_summary":
            res = await queries.vegetation_summary(db, job)
        elif op == "built_up_change":
            res = await queries.built_up_change(db, job)
        elif op == "confidence_distribution":
            res = await queries.confidence_distribution(db, job)
        elif op == "explain_feature":
            if not spec.feature_id:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "feature_required", "message": "explain_feature needs a feature_id."})
            res = await queries.explain_feature(db, job, spec.feature_id)
        elif op == "compare_analyses":
            other = await queries.get_job(db, user, spec.compare_to_analysis_id) if spec.compare_to_analysis_id else await _previous(db, user, job)
            if other is None:
                return AnalyticsQueryResponse(question=req.question, interpreted_as=spec.model_dump(mode="json", exclude_none=True), operation=op, understood=True, data={},
                                              answer="There is no earlier completed analysis in this project to compare with, so no comparison (or trend) can be made.", answer_source="deterministic",
                                              measured_facts=[], caveats=["GeoTrace does not invent history."], references=[])
            a, b = (other, job) if (other.after_date or other.created_at) <= (job.after_date or job.created_at) else (job, other)
            res = await queries.compare_analyses(db, a, b)
        else:  # pragma: no cover - guarded by the Literal type
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unsupported operation")

    answer, source = res.headline, "deterministic"
    if req.narrate and res.facts and llm.llm_enabled():
        narr = await llm.llm_narrate(req.question, res.headline, res.facts, res.caveats)
        if narr:
            answer, source = narr, "llm_narration"
    interp = spec.model_dump(mode="json", exclude_none=True)
    if job is not None:
        interp["analysis_name"] = job.name
    if notes:
        interp["notes"] = notes
    return AnalyticsQueryResponse(question=req.question, interpreted_as=interp, operation=spec.operation, understood=True, data=_jsonable(res.data), answer=answer, answer_source=source,
                                  measured_facts=res.facts, caveats=res.caveats, references=_refs(res.references), suggestions=[])


def _jsonable(v: Any) -> Any:
    from datetime import date, datetime

    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    return v
