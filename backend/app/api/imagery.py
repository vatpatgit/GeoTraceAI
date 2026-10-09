from __future__ import annotations

import json
import uuid
from datetime import datetime

import anyio
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.auth.dependencies import require_authenticated_user, require_user_or_admin
from app.database import get_db
from app.geo.config import DetectionConfig, PreprocessConfig
from app.geo.errors import GeoProcessingError
from app.geo.pipeline import select_method
from app.geo.raster_io import inspect_raster
from app.geo.tiles import render_tile
from app.geo.validation import validate_pair
from app.ml.registry import get_card, learned_ready
from app.models import AnalysisJob, AreaOfInterest, ImageryAsset, User
from app.schemas.analysis import AssetMlChangesRequest, ImageryAssetOut, ImageryUpdate, PairValidateRequest, PairValidationOut
from app.schemas.common import Issue
from app.services import access
from app.services.imagery import asset_path, asset_style, asset_to_out, ingest_upload

router = APIRouter()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid datetime {value!r}; use ISO-8601.") from exc


@router.post("/upload", response_model=ImageryAssetOut, status_code=status.HTTP_201_CREATED)
async def upload_imagery(
    response: Response,
    file: UploadFile = File(..., description="A GeoTIFF"),
    project_id: uuid.UUID = Form(...),
    acquisition_date: str | None = Form(default=None, description="ISO-8601 date/time the imagery was acquired"),
    band_map: str | None = Form(default=None, description='JSON {"red":1,"green":2,"blue":3,"nir":4}'),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user_or_admin),
):
    """Stream a GeoTIFF to storage, verify its *content* (not its extension), inspect georeferencing and register it."""
    project = await access.load_project(db, project_id, user, write=True)
    bm = None
    if band_map:
        try:
            bm = {str(k): int(v) for k, v in json.loads(band_map).items()}
        except (ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "band_map must be a JSON object of role -> 1-based band index.") from exc
    when = _parse_dt(acquisition_date)
    asset, warnings, reused = await ingest_upload(db, user, project, file, acquisition_start=when, band_map=bm)
    if reused:
        response.status_code = status.HTTP_200_OK
        warnings = [Issue(level="info", code="already_uploaded", message="This exact file was already uploaded to the project; the existing asset was reused.")] + warnings
    return asset_to_out(asset, warnings)


@router.get("", response_model=list[ImageryAssetOut])
async def list_assets(project_id: uuid.UUID = Query(...), db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_authenticated_user)):
    await access.load_project(db, project_id, user)
    rows = (await db.execute(select(ImageryAsset).where(ImageryAsset.project_id == project_id).order_by(ImageryAsset.created_at.desc()))).scalars()
    return [asset_to_out(a) for a in rows]


@router.get("/{asset_id}", response_model=ImageryAssetOut)
async def get_asset(asset_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    return asset_to_out(await access.load_asset(db, asset_id, user))


@router.patch("/{asset_id}", response_model=ImageryAssetOut)
async def update_asset(asset_id: uuid.UUID, body: ImageryUpdate, db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_user_or_admin)):
    a = await access.load_asset(db, asset_id, user, write=True)
    data = body.model_dump(exclude_unset=True)
    if "band_map" in data and data["band_map"] is not None:
        bm = {k: int(v) for k, v in data["band_map"].items()}
        if any(v < 1 or v > a.band_count for v in bm.values()):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Band indexes must be within 1..{a.band_count}.")
        a.band_map, a.band_map_confirmed = bm, True
    if "acquisition_start" in data:
        a.acquisition_start = data["acquisition_start"]
        a.acquisition_end = data.get("acquisition_end") or data["acquisition_start"]
    await db.commit()
    await db.refresh(a)
    return asset_to_out(a)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(asset_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_user_or_admin)):
    a = await access.load_asset(db, asset_id, user, write=True)
    in_use = await db.scalar(select(AnalysisJob.id).where(
        (AnalysisJob.before_asset_id == a.id) | (AnalysisJob.after_asset_id == a.id)).limit(1))
    if in_use:
        raise HTTPException(status.HTTP_409_CONFLICT, "This imagery is referenced by an analysis; delete the analysis first.")
    aid = a.id
    await db.delete(a)
    await db.commit()
    storage.remove_tree(f"imagery/{aid}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{asset_id}/download")
async def download_original(asset_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    a = await access.load_asset(db, asset_id, user)
    return FileResponse(asset_path(a), media_type="image/tiff", filename=a.original_filename or f"{a.id}.tif")


@router.get("/{asset_id}/tiles/{z}/{x}/{y}.png")
async def asset_tile(asset_id: uuid.UUID, z: int, x: int, y: int, db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_authenticated_user)):
    if not (0 <= z <= 24 and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tile out of range")
    a = await access.load_asset(db, asset_id, user)
    style = asset_style(a)
    png = await anyio.to_thread.run_sync(lambda: render_tile(str(asset_path(a)), z, x, y, style))
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/validate-pair", response_model=PairValidationOut)
async def validate_pair_endpoint(body: PairValidateRequest, db: AsyncSession = Depends(get_db),
                                 user: User = Depends(require_authenticated_user)):
    """Pre-flight: report every adaptation/incompatibility *before* processing so the user can confirm the pair."""
    before = await access.load_asset(db, body.before_asset_id, user)
    after = await access.load_asset(db, body.after_asset_id, user)
    cfg = PreprocessConfig()
    try:
        ib, ia = await anyio.to_thread.run_sync(lambda: (inspect_raster(asset_path(before)), inspect_raster(asset_path(after))))
        v = validate_pair(ib, ia, cfg, band_map_override=body.band_map)
    except GeoProcessingError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "message": str(exc)}) from exc
    issues = [Issue(**i.__dict__) for i in v.issues]
    if body.aoi_id:
        aoi = await db.get(AreaOfInterest, body.aoi_id)
        if aoi is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "AOI not found")
    roles = v.bands.get("common_roles", [])
    ready = learned_ready(None)
    method, reason = select_method("auto", v.suggested_pixel_size_m or max(ib.gsd_m, ia.gsd_m), roles, learned_ready=ready,
                                   trained_gsd_m=(get_card(None).trained_gsd_m if get_card(None) else 2.0))
    return PairValidationOut(ok=v.ok, issues=issues, analysis_crs_epsg=v.analysis_crs_epsg, overlap=v.overlap,
                             resolution=v.resolution, bands=v.bands, suggested_pixel_size_m=v.suggested_pixel_size_m,
                             model_available=ready, suggested_method=method, suggested_method_reason=reason)


def _bbox_param(raw: str) -> tuple[float, float, float, float]:
    try:
        w, s, e, n = (float(v) for v in raw.split(","))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "bad_bbox", "message": "bbox must be 'west,south,east,north'."}) from exc
    return w, s, e, n


@router.get("/{asset_id}/render")
async def render_asset_png(asset_id: uuid.UUID, bbox: str = Query(description="west,south,east,north (WGS84)"), width: int = Query(default=1536, ge=256, le=2048),
                           db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    """One georeferenced RGBA PNG of the asset over a lon/lat box, in Web-Mercator pixel space (for MapLibre / Cesium image overlays)."""
    from app.geo.errors import PairIncompatibleError
    from app.services.upload_compare import render_asset

    a = await access.load_asset(db, asset_id, user)
    box = _bbox_param(bbox)
    try:
        png, size = await anyio.to_thread.run_sync(lambda: render_asset(str(asset_path(a)), asset_style(a), box, width))
    except PairIncompatibleError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "message": str(exc)}) from exc
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=600", "X-Image-Size": f"{size[0]}x{size[1]}"})


@router.post("/ml-changes")
async def ml_changes_for_assets(body: AssetMlChangesRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    """Run the learned change-detection model on two uploaded images over a common box; changed areas come back as GeoJSON."""
    from app.geo.errors import PairIncompatibleError
    from app.services.upload_compare import detect_between_assets

    before = await access.load_asset(db, body.before_asset_id, user)
    after = await access.load_asset(db, body.after_asset_id, user)
    box = _bbox_param(",".join(str(v) for v in body.bbox))
    try:
        return await detect_between_assets((str(asset_path(before)), asset_style(before)), (str(asset_path(after)), asset_style(after)), box,
                                           width=body.width, model_id=body.model_id)
    except PairIncompatibleError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "message": str(exc)}) from exc


@router.post("/plain-ml-changes")
async def plain_ml_changes(before: UploadFile = File(...), after: UploadFile = File(...), pixel_size_m: float | None = Form(default=None, gt=0, le=1000),
                           model_id: str | None = Form(default=None), user: User = Depends(require_authenticated_user)):
    """ML change detection between two ordinary images (PNG / JPEG / WebP / BMP / GIF). Nothing is stored; results are in image pixel coordinates."""
    from app.config import settings
    from app.geo.errors import PairIncompatibleError
    from app.services.plain_compare import detect_plain

    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    blobs = []
    for f in (before, after):
        data = await f.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail={"code": "too_large", "message": f"Images may be at most {settings.MAX_UPLOAD_MB} MB."})
        blobs.append(data)
    try:
        return await detect_plain(blobs[0], blobs[1], pixel_size_m=pixel_size_m, model_id=model_id)
    except PairIncompatibleError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "message": str(exc)}) from exc
