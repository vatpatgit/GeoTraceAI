from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import queries
from app.analytics.service import _jsonable, run_query
from app.auth.dependencies import require_authenticated_user
from app.database import get_db
from app.models import User
from app.schemas.analytics import AnalyticsQueryRequest, AnalyticsQueryResponse
from app.services import access
from app.services.reports import build_report, report_csv, report_pdf

router = APIRouter()
reports_router = APIRouter()


@router.post("/query", response_model=AnalyticsQueryResponse)
async def query(body: AnalyticsQueryRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    """Answer a supported question (natural language or structured spec) from the stored results."""
    if not body.question and not body.spec:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide a question or a spec.")
    return await run_query(db, user, body)


@router.get("/overview")
async def overview(project_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    if project_id:
        await access.load_project(db, project_id, user)
    return _jsonable(await queries.overview(db, user, project_id))


@reports_router.get("/analyses/{analysis_id}")
async def analysis_report(analysis_id: uuid.UUID, format: str = Query("json", pattern="^(json|csv|pdf)$"), db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_authenticated_user)):
    job = await access.load_analysis(db, analysis_id, user)
    if job.status != "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Reports are generated from completed analyses.")
    rep = _jsonable(await build_report(db, job))
    stem = f"geotrace_report_{str(job.id)[:8]}"
    if format == "json":
        return Response(json.dumps(rep, indent=2, default=str), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{stem}.json"'})
    if format == "csv":
        return Response(report_csv(rep), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'})
    return Response(report_pdf(rep), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{stem}.pdf"'})
