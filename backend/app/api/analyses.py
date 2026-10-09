from __future__ import annotations

import uuid
from typing import Any

import anyio
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.auth.dependencies import require_authenticated_user, require_user_or_admin
from app.database import get_db
from app.geo.tiles import RasterStyle, render_tile, transparent_tile
from app.models import AlertRule, AnalysisEvent, AnalysisJob, ImageryAsset, Project, User
from app.models.analysis import TERMINAL_STATUSES
from app.schemas.analysis import (AnalysisCreate, AnalysisEventOut, AnalysisOut, ChangeFeatureOut, FeaturePage, ReviewUpdate)
from app.schemas.change import FeatureFilter
from app.schemas.common import Severity
from app.services import access, analyses as svc
from app.services.alert_engine import evaluate_analysis
from app.services.exports import MEDIA_TYPES, create_export

router = APIRouter()
VALID_TILE_LAYERS = ("before", "after", "score", "mask", "delta_ndvi", "ndvi_before", "ndvi_after")


def feature_filter(
    severity: list[Severity] | None = Query(None, description="repeatable"),
    category: list[str] | None = Query(None, description="repeatable"),
    review_status: list[str] | None = Query(None),
    min_area_m2: float | None = Query(None, ge=0),
    max_area_m2: float | None = Query(None, ge=0),
    min_confidence: float | None = Query(None, ge=0, le=1),
    min_magnitude: float | None = Query(None, ge=0, le=1),
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    aoi_id: uuid.UUID | None = None,
    ids: list[uuid.UUID] | None = Query(None, description="restrict to these feature ids (selection)"),
    sort: str = Query("area_desc"),
) -> FeatureFilter:
    box = None
    if bbox:
        try:
            box = [float(v) for v in bbox.split(",")]
            if len(box) != 4:
                raise ValueError
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bbox must be four comma-separated numbers.") from exc
    try:
        return FeatureFilter(severities=severity, categories=category, review_status=review_status, min_area_m2=min_area_m2,
                             max_area_m2=max_area_m2, min_confidence=min_confidence, min_magnitude=min_magnitude, bbox=box,
                             aoi_id=aoi_id, ids=ids, sort=sort)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


# --------------------------------------------------------------------------------------------------- lifecycle
@router.post("", response_model=AnalysisOut, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(body: AnalysisCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_user_or_admin)):
    """Validate the pair and enqueue processing. Returns immediately; poll ``GET /analyses/{id}``."""
    project = await access.load_project(db, body.project_id, user, write=True)
    before = await access.load_asset(db, body.before_asset_id, user)
    after = await access.load_asset(db, body.after_asset_id, user)
    job = await svc.create_analysis(db, user, project, body, before=before, after=after)
    return svc.serialize_analysis(job)


@router.get("", response_model=list[AnalysisOut])
async def list_analyses(project_id: uuid.UUID | None = None, status_: str | None = Query(None, alias="status"),
                        limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                        db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    stmt = (select(AnalysisJob).join(Project, Project.id == AnalysisJob.project_id)
            .where(access.readable_projects_clause(user)).order_by(AnalysisJob.created_at.desc()).limit(limit).offset(offset))
    if project_id:
        stmt = stmt.where(AnalysisJob.project_id == project_id)
    if status_:
        stmt = stmt.where(AnalysisJob.status == status_)
    return [svc.serialize_analysis(j) for j in (await db.execute(stmt)).scalars()]


@router.get("/{analysis_id}", response_model=AnalysisOut)
async def get_analysis(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    return svc.serialize_analysis(await access.load_analysis(db, analysis_id, user))


@router.post("/{analysis_id}/cancel", response_model=AnalysisOut)
async def cancel_analysis(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_user_or_admin)):
    job = await access.load_analysis(db, analysis_id, user, write=True)
    return svc.serialize_analysis(await svc.request_cancel(db, job))


@router.post("/{analysis_id}/retry", response_model=AnalysisOut, status_code=status.HTTP_202_ACCEPTED)
async def retry_analysis(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_user_or_admin)):
    """Re-queue a failed/cancelled analysis (idempotent: earlier partial features are discarded on start)."""
    job = await access.load_analysis(db, analysis_id, user, write=True)
    if job.status not in ("failed", "cancelled"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only failed or cancelled analyses can be retried.")
    job.error, job.cancel_requested, job.finished_at, job.locked_by = None, False, None, None
    await svc.add_event(db, job, "queued", 0.0, "Re-queued")
    await db.commit()
    await db.refresh(job)
    return svc.serialize_analysis(job)


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_user_or_admin)):
    job = await access.load_analysis(db, analysis_id, user, write=True)
    await svc.delete_analysis(db, job)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{analysis_id}/events", response_model=list[AnalysisEventOut])
async def analysis_events(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    await access.load_analysis(db, analysis_id, user)
    rows = (await db.execute(select(AnalysisEvent).where(AnalysisEvent.analysis_id == analysis_id).order_by(AnalysisEvent.id))).scalars()
    return [AnalysisEventOut.model_validate(r) for r in rows]


# --------------------------------------------------------------------------------------------------- features
@router.get("/{analysis_id}/features")
async def list_features(
    analysis_id: uuid.UUID,
    flt: FeatureFilter = Depends(feature_filter),
    limit: int = Query(100, ge=1, le=20000),
    offset: int = Query(0, ge=0),
    format: str = Query("json", pattern="^(json|geojson)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_authenticated_user),
):
    """Paginated, server-side filtered features. ``format=geojson`` returns a lightweight FeatureCollection for map rendering."""
    job = await access.load_analysis(db, analysis_id, user)
    total, items = await svc.list_features(db, job, flt, limit, offset)
    if format == "geojson":
        feats = [{
            "type": "Feature", "id": str(f.id), "geometry": f.geometry,
            "properties": {"id": str(f.id), "seq": f.seq, "category": f.category, "severity": f.severity, "area_m2": f.area_m2,
                           "confidence": f.confidence, "magnitude": f.magnitude, "review_status": f.review_status,
                           "centroid": f.centroid},
        } for f in items]
        return JSONResponse({"type": "FeatureCollection", "features": feats, "total": total, "returned": len(feats),
                             "truncated": total > offset + len(feats), "is_demo": job.is_demo}, media_type="application/geo+json")
    return FeaturePage(total=total, limit=limit, offset=offset, items=items)


@router.get("/{analysis_id}/features/{feature_id}", response_model=ChangeFeatureOut)
async def get_feature(analysis_id: uuid.UUID, feature_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_authenticated_user)):
    job = await access.load_analysis(db, analysis_id, user)
    return await svc.get_feature(db, job, feature_id)


@router.patch("/{analysis_id}/features/{feature_id}/review", response_model=ChangeFeatureOut)
async def review_feature(analysis_id: uuid.UUID, feature_id: uuid.UUID, body: ReviewUpdate, db: AsyncSession = Depends(get_db),
                         user: User = Depends(require_user_or_admin)):
    job = await access.load_analysis(db, analysis_id, user, write=True)
    return await svc.review_feature(db, job, feature_id, user, body.review_status, body.review_note)


# --------------------------------------------------------------------------------------------------- exports
async def _do_export(db: AsyncSession, user: User, analysis_id: uuid.UUID, fmt: str, flt: FeatureFilter):
    job = await access.load_analysis(db, analysis_id, user)
    scope = "selected" if flt.ids else ("filtered" if flt.model_dump(exclude_none=True, exclude={"sort"}) else "all")
    if flt.aoi_id and scope != "selected":
        scope = "aoi"
    before = await db.get(ImageryAsset, job.before_asset_id) if job.before_asset_id else None
    after = await db.get(ImageryAsset, job.after_asset_id) if job.after_asset_id else None
    rec, path = await create_export(db, user, job, fmt, flt, scope, before, after)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in job.name)[:60] or "analysis"
    return FileResponse(path, media_type=MEDIA_TYPES[fmt], filename=f"geotrace_{safe_name}_{str(job.id)[:8]}.{fmt}",
                        headers={"X-Feature-Count": str(rec.feature_count), "X-Export-Id": str(rec.id), "Cache-Control": "no-store"})


@router.get("/{analysis_id}/export")
async def export_get(analysis_id: uuid.UUID, format: str = Query("geojson", pattern="^(geojson|gpkg|csv)$"),
                     flt: FeatureFilter = Depends(feature_filter), db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_authenticated_user)):
    return await _do_export(db, user, analysis_id, format, flt)


@router.post("/{analysis_id}/export")
async def export_post(analysis_id: uuid.UUID, body: dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_authenticated_user)):
    """Body: ``{"format": "geojson|gpkg|csv", "filters": {...FeatureFilter...}}`` (use for long id selections)."""
    fmt = body.get("format", "geojson")
    if fmt not in MEDIA_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "format must be geojson, gpkg or csv")
    try:
        flt = FeatureFilter(**(body.get("filters") or {}))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return await _do_export(db, user, analysis_id, fmt, flt)


# --------------------------------------------------------------------------------------------------- rasters
def analysis_tile_style(job: AnalysisJob, layer: str, false_color: bool = False) -> tuple[str, RasterStyle] | None:
    arts = job.artifacts or {}
    proc = job.processing or {}
    roles: list[str] = (proc.get("grid") or {}).get("roles", [])
    if layer in ("before", "after"):
        key = f"{layer}_aligned"
        if key not in arts:
            return None
        disp = proc.get("display") or {}
        stretch = disp.get("stretch")
        if false_color and all(r in roles for r in ("nir", "red", "green")):
            sel = ["nir", "red", "green"]
        elif all(r in roles for r in ("red", "green", "blue")):
            sel = ["red", "green", "blue"]
        else:
            sel = None
        mask = storage.resolve(arts["valid_mask"]) if "valid_mask" in arts else None
        if sel:
            bands = [roles.index(r) + 1 for r in sel]
            st = [tuple(stretch[roles.index(r)]) for r in sel] if stretch else None
            return arts[key], RasterStyle(mode="rgb", bands=bands, stretch=st, mask_path=str(mask) if mask else None)
        b = 1
        st = [tuple(stretch[0])] if stretch else None
        return arts[key], RasterStyle(mode="gray", bands=[b], stretch=st, mask_path=str(mask) if mask else None)
    if layer in ("ndvi_before", "ndvi_after"):
        key = "before_aligned" if layer == "ndvi_before" else "after_aligned"
        if key not in arts or "red" not in roles or "nir" not in roles:
            return None
        mask = storage.resolve(arts["valid_mask"]) if "valid_mask" in arts else None
        return arts[key], RasterStyle(mode="ndvi", bands=[roles.index("red") + 1, roles.index("nir") + 1], mask_path=str(mask) if mask else None)
    if layer == "score" and "change_score" in arts:
        return arts["change_score"], RasterStyle(mode="score", bands=[1])
    if layer == "mask" and "change_mask" in arts:
        return arts["change_mask"], RasterStyle(mode="mask", bands=[1])
    if layer == "delta_ndvi" and "delta_ndvi" in arts:
        return arts["delta_ndvi"], RasterStyle(mode="delta", bands=[1])
    return None


@router.get("/{analysis_id}/tiles/{layer}/{z}/{x}/{y}.png")
async def analysis_tile(analysis_id: uuid.UUID, layer: str, z: int, x: int, y: int, false_color: bool = False,
                        db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    if layer not in VALID_TILE_LAYERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown layer; use one of {VALID_TILE_LAYERS}")
    if not (0 <= z <= 24 and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tile out of range")
    job = await access.load_analysis(db, analysis_id, user)
    if job.status != "completed":
        return Response(transparent_tile(), media_type="image/png", headers={"Cache-Control": "no-store"})
    got = analysis_tile_style(job, layer, false_color)
    if got is None:
        return Response(transparent_tile(), media_type="image/png", headers={"Cache-Control": "no-store"})
    rel, style = got
    path = str(storage.resolve(rel))
    png = await anyio.to_thread.run_sync(lambda: render_tile(path, z, x, y, style))
    return Response(png, media_type="image/png", headers={
        "Cache-Control": "private, max-age=3600", "ETag": f'"{job.id}-{layer}-{int(job.finished_at.timestamp()) if job.finished_at else 0}"'})


@router.get("/{analysis_id}/features/{feature_id}/chip/{layer}.png")
async def feature_chip(analysis_id: uuid.UUID, feature_id: uuid.UUID, layer: str, size: int = Query(320, ge=64, le=1024),
                       pad: float = Query(1.0, ge=0.1, le=10.0), false_color: bool = False, db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_authenticated_user)):
    """A square before/after image crop centred on a feature (evidence thumbnail). ``pad`` = extra margin as a multiple of the
    feature size (min. 120 m on a side so tiny changes still show context)."""
    from app.geo.tiles import lonlat_to_3857, render_bounds

    if layer not in ("before", "after", "score", "mask"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "layer must be before, after, score or mask")
    job = await access.load_analysis(db, analysis_id, user)
    feat = await svc.get_feature(db, job, feature_id)
    got = analysis_tile_style(job, layer, false_color) if job.status == "completed" else None
    if got is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagery for this analysis is not available")
    rel, style = got
    x0, y0 = lonlat_to_3857(feat.bbox[0], feat.bbox[1])
    x1, y1 = lonlat_to_3857(feat.bbox[2], feat.bbox[3])
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    half = max(abs(x1 - x0), abs(y1 - y0)) / 2 * (1 + pad)
    half = max(half, 60.0)  # >= 120 m wide
    bounds = (cx - half, cy - half, cx + half, cy + half)
    path = str(storage.resolve(rel))
    png = await anyio.to_thread.run_sync(lambda: render_bounds(path, bounds, (size, size), style))
    return Response(png or transparent_tile(), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{analysis_id}/artifacts/{name}")
async def download_artifact(analysis_id: uuid.UUID, name: str, db: AsyncSession = Depends(get_db),
                            user: User = Depends(require_authenticated_user)):
    job = await access.load_analysis(db, analysis_id, user)
    rel = (job.artifacts or {}).get(name)
    if not rel:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    return FileResponse(storage.resolve(rel), media_type="image/tiff", filename=f"{name}_{str(job.id)[:8]}.tif")


@router.post("/{analysis_id}/evaluate-alerts")
async def reevaluate_alerts(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_user_or_admin)):
    """Evaluate (new) rules against an already-completed analysis. Idempotent: existing incidents are never duplicated."""
    job = await access.load_analysis(db, analysis_id, user, write=True)
    if job.status != "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Analysis has not completed.")
    return await evaluate_analysis(db, job)
