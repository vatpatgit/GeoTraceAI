"""Analysis lifecycle: creation/validation, serialization, feature queries, review, deletion."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

import anyio
from fastapi import HTTPException, status
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import and_, asc, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.config import settings
from app.geo.config import PipelineConfig
from app.geo.errors import GeoProcessingError
from app.geo.preprocess import AlignedPair
from app.geo.raster_io import inspect_raster
from app.geo.validation import validate_pair
from app.ml.registry import learned_ready
from app.models import AnalysisEvent, AnalysisJob, AreaOfInterest, ChangeFeature, ImageryAsset, Project, User
from app.models.analysis import TERMINAL_STATUSES
from app.schemas.analysis import AnalysisCreate, AnalysisOut, ChangeFeatureOut
from app.schemas.change import FeatureFilter
from app.services.imagery import asset_path

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


# --------------------------------------------------------------------------------------------------- serialization
def serialize_analysis(job: AnalysisJob) -> AnalysisOut:
    arts = sorted((job.artifacts or {}).keys())
    return AnalysisOut(
        id=job.id, project_id=job.project_id, aoi_id=job.aoi_id, created_by=job.created_by, name=job.name,
        input_type=job.input_type, status=job.status, stage_message=job.stage_message, progress=job.progress, error=job.error,
        cancel_requested=job.cancel_requested, before_asset_id=job.before_asset_id, after_asset_id=job.after_asset_id,
        before_date=job.before_date, after_date=job.after_date, method=job.method, method_reason=job.method_reason,
        model_id=job.model_id, config=job.config or {}, summary=job.summary, warnings=job.warnings, validation=job.validation,
        processing=job.processing, artifacts=arts, bounds=job.bounds_wgs84, is_demo=job.is_demo,
        data_origin="demo" if job.is_demo else "live", created_at=job.created_at, started_at=job.started_at, finished_at=job.finished_at,
    )


async def add_event(db: AsyncSession, job: AnalysisJob, status_: str, progress: float, message: str | None) -> None:
    job.status = status_
    job.progress = progress
    job.stage_message = message
    db.add(AnalysisEvent(analysis_id=job.id, status=status_, progress=progress, message=message))


# --------------------------------------------------------------------------------------------------- creation
def effective_config(overrides: dict[str, Any] | None) -> PipelineConfig:
    try:
        cfg = PipelineConfig.from_dict(overrides)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "bad_config", "message": str(exc)}) from exc
    cfg.preprocess.max_pixels = min(cfg.preprocess.max_pixels, settings.MAX_RASTER_PIXELS)
    return cfg


def validate_assets_pair(before: ImageryAsset, after: ImageryAsset, cfg: PipelineConfig, band_map: dict[str, int] | None = None):
    """Re-inspect both files (cheap) and run the pair compatibility validation."""
    ib, ia = inspect_raster(asset_path(before)), inspect_raster(asset_path(after))
    return validate_pair(ib, ia, cfg.preprocess, band_map_override=cfg.detection.band_map or band_map)


async def create_analysis(db: AsyncSession, user: User, project: Project, body: AnalysisCreate, *,
                          before: ImageryAsset, after: ImageryAsset, is_demo: bool = False) -> AnalysisJob:
    if before.id == after.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "same_asset", "message": "Before and after must be different images."})
    cfg = effective_config(body.config)
    aoi = None
    if body.aoi_id:
        aoi = await db.get(AreaOfInterest, body.aoi_id)
        if aoi is None or aoi.project_id != project.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "AOI not found in this project")

    validation = await anyio.to_thread.run_sync(lambda: validate_assets_pair(before, after, cfg))
    if not validation.ok:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "incompatible_pair", "message": "; ".join(i.message for i in validation.errors),
            "issues": [i.__dict__ for i in validation.issues]})

    before_date = body.before_date or before.acquisition_start
    after_date = body.after_date or after.acquisition_start
    if before_date and after_date and before_date >= after_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "date_order", "message": "The before image must be earlier than the after image."})
    name = body.name or f"{before.original_filename or 'before'} -> {after.original_filename or 'after'}"

    job = AnalysisJob(
        project_id=project.id, aoi_id=body.aoi_id, created_by=user.id, name=name[:160], input_type=body.input_type,
        before_asset_id=before.id, after_asset_id=after.id, before_date=before_date, after_date=after_date,
        config=cfg.to_dict(), acquisition_params=body.acquisition_params, status="queued", progress=0.0,
        stage_message="Queued", validation=validation.to_dict(),
        warnings=[i.__dict__ for i in validation.issues if i.level != "error"], is_demo=is_demo or before.is_demo or after.is_demo,
        model_id=cfg.detection.model_id,
    )
    db.add(job)
    await db.flush()
    db.add(AnalysisEvent(analysis_id=job.id, status="queued", progress=0.0, message="Queued"))
    await db.commit()
    await db.refresh(job)
    return job


async def request_cancel(db: AsyncSession, job: AnalysisJob) -> AnalysisJob:
    if job.status in TERMINAL_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Analysis already {job.status}.")
    if job.status == "queued":
        await add_event(db, job, "cancelled", job.progress, "Cancelled before start")
        job.finished_at = datetime.now(timezone.utc)
    else:
        job.cancel_requested = True
        db.add(AnalysisEvent(analysis_id=job.id, status=job.status, progress=job.progress, message="Cancellation requested"))
    await db.commit()
    await db.refresh(job)
    return job


async def delete_analysis(db: AsyncSession, job: AnalysisJob) -> None:
    if job.status not in TERMINAL_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cancel the running analysis before deleting it.")
    jid = job.id
    await db.delete(job)
    await db.commit()
    storage.remove_tree(f"analyses/{jid}")


# --------------------------------------------------------------------------------------------------- features
def _apply_filter(stmt, analysis_id: uuid.UUID, flt: FeatureFilter, aoi_geom=None):
    stmt = stmt.where(ChangeFeature.analysis_id == analysis_id)
    if flt.severities:
        stmt = stmt.where(ChangeFeature.severity.in_(flt.severities))
    if flt.categories:
        stmt = stmt.where(ChangeFeature.category.in_(flt.categories))
    if flt.review_status:
        stmt = stmt.where(ChangeFeature.review_status.in_(flt.review_status))
    if flt.min_area_m2 is not None:
        stmt = stmt.where(ChangeFeature.area_m2 >= flt.min_area_m2)
    if flt.max_area_m2 is not None:
        stmt = stmt.where(ChangeFeature.area_m2 <= flt.max_area_m2)
    if flt.min_confidence is not None:
        stmt = stmt.where(ChangeFeature.confidence >= flt.min_confidence)
    if flt.min_magnitude is not None:
        stmt = stmt.where(ChangeFeature.magnitude >= flt.min_magnitude)
    if flt.ids:
        stmt = stmt.where(ChangeFeature.id.in_(flt.ids))
    if flt.bbox:
        stmt = stmt.where(func.ST_Intersects(ChangeFeature.geometry, func.ST_MakeEnvelope(*flt.bbox, 4326)))
    if aoi_geom is not None:
        stmt = stmt.where(func.ST_Intersects(ChangeFeature.geometry, aoi_geom))
    return stmt


def _order(flt: FeatureFilter):
    sev_rank = case(*[(ChangeFeature.severity == k, v) for k, v in SEVERITY_ORDER.items()], else_=0)
    return {
        "area_desc": [desc(ChangeFeature.area_m2)],
        "area_asc": [asc(ChangeFeature.area_m2)],
        "severity_desc": [desc(sev_rank), desc(ChangeFeature.area_m2)],
        "confidence_desc": [desc(ChangeFeature.confidence).nulls_last(), desc(ChangeFeature.area_m2)],
        "seq": [asc(ChangeFeature.seq)],
    }[flt.sort]


async def _aoi_geom(db: AsyncSession, flt: FeatureFilter):
    if not flt.aoi_id:
        return None
    if await db.get(AreaOfInterest, flt.aoi_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "AOI not found")
    return select(AreaOfInterest.geometry).where(AreaOfInterest.id == flt.aoi_id).scalar_subquery()


def _collapse(geojson_str: str) -> dict[str, Any]:
    g = json.loads(geojson_str)
    if g["type"] == "MultiPolygon" and len(g["coordinates"]) == 1:
        return {"type": "Polygon", "coordinates": g["coordinates"][0]}
    return g


_FEATURE_COLS = (
    ChangeFeature,
    func.ST_AsGeoJSON(ChangeFeature.geometry, 7).label("gj"),
    func.ST_X(ChangeFeature.centroid).label("cx"), func.ST_Y(ChangeFeature.centroid).label("cy"),
    func.ST_X(ChangeFeature.point_on_surface).label("px"), func.ST_Y(ChangeFeature.point_on_surface).label("py"),
    func.ST_XMin(ChangeFeature.geometry).label("x0"), func.ST_YMin(ChangeFeature.geometry).label("y0"),
    func.ST_XMax(ChangeFeature.geometry).label("x1"), func.ST_YMax(ChangeFeature.geometry).label("y1"),
)


def feature_out(row: Any, job: AnalysisJob) -> ChangeFeatureOut:
    f: ChangeFeature = row[0]
    det = (job.processing or {}).get("detection", {})
    return ChangeFeatureOut(
        id=f.id, analysis_id=f.analysis_id, seq=f.seq, category=f.category, category_basis=f.category_basis,
        area_m2=f.area_m2, perimeter_m=f.perimeter_m, centroid=[row.cx, row.cy], point_on_surface=[row.px, row.py],
        magnitude=f.magnitude, confidence=f.confidence, confidence_kind=det.get("confidence_kind"), delta_ndvi=f.delta_ndvi,
        severity=f.severity, severity_reasons=list(f.severity_reasons or []), distance_to_boundary_m=f.distance_to_boundary_m,
        review_status=f.review_status, review_note=f.review_note, before_date=job.before_date, after_date=job.after_date,
        bbox=[row.x0, row.y0, row.x1, row.y1], geometry=_collapse(row.gj),
    )


async def list_features(db: AsyncSession, job: AnalysisJob, flt: FeatureFilter, limit: int, offset: int) -> tuple[int, list[ChangeFeatureOut]]:
    aoi_geom = await _aoi_geom(db, flt)
    count_stmt = _apply_filter(select(func.count(ChangeFeature.id)), job.id, flt, aoi_geom)
    total = await db.scalar(count_stmt) or 0
    stmt = _apply_filter(select(*_FEATURE_COLS), job.id, flt, aoi_geom).order_by(*_order(flt)).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).all()
    return total, [feature_out(r, job) for r in rows]


async def get_feature(db: AsyncSession, job: AnalysisJob, feature_id: uuid.UUID) -> ChangeFeatureOut:
    stmt = select(*_FEATURE_COLS).where(ChangeFeature.id == feature_id, ChangeFeature.analysis_id == job.id)
    row = (await db.execute(stmt)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Feature not found")
    return feature_out(row, job)


async def all_features(db: AsyncSession, job: AnalysisJob, flt: FeatureFilter, cap: int = 200_000) -> list[Any]:
    aoi_geom = await _aoi_geom(db, flt)
    stmt = _apply_filter(select(*_FEATURE_COLS), job.id, flt, aoi_geom).order_by(*_order(flt)).limit(cap)
    return list((await db.execute(stmt)).all())


async def review_feature(db: AsyncSession, job: AnalysisJob, feature_id: uuid.UUID, user: User, review_status: str, note: str | None):
    f = await db.get(ChangeFeature, feature_id)
    if f is None or f.analysis_id != job.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Feature not found")
    f.review_status = review_status
    f.review_note = note
    f.reviewed_by = user.id
    f.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return await get_feature(db, job, feature_id)
