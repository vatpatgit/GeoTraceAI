"""Sentinel-2 discovery and acquisition (server-side credentials only)."""
from __future__ import annotations

import logging
import uuid
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from shapely.geometry import mapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_authenticated_user, require_user_or_admin
from app.config import settings
from app.database import get_db
from app.geo import aoi as aoi_geo
from app.geo.config import PipelineConfig
from app.models import AnalysisEvent, AnalysisJob, User
from app.providers.base import ProviderError, ProviderNotConfigured
from app.providers.registry import provider_status
from app.providers.sentinel import get_provider
from app.schemas.sentinel import (AcquireRequest, AcquireResponse, MlChangesRequest, PreviewRequest, ProviderStatus, SceneOut, SentinelSearchRequest,
                                  SentinelSearchResponse)
from app.services import access
from app.services import sentinel as svc
from app.services.analyses import effective_config

logger = logging.getLogger(__name__)
router = APIRouter()


def _provider_or_503(imagery: bool = False):
    p = get_provider()
    if p is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "provider_not_configured", "message": "Sentinel integration is disabled on this server."})
    if imagery and not getattr(p, "imagery_configured", getattr(p, "_process", None) is not None):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail={
            "code": "provider_not_configured",
            "message": "Imagery retrieval is not configured on this server (no Sentinel OAuth client credentials). Catalogue search is available; "
                       "upload GeoTIFFs instead, or ask an administrator to configure SENTINEL_HUB_CLIENT_ID / SECRET."})
    return p


def _raise(exc: ProviderError):
    headers = {"Retry-After": str(int(exc.retry_after))} if exc.retry_after else None
    raise HTTPException(exc.status, detail={"code": exc.code, "message": str(exc)}, headers=headers) from exc


@router.get("/status", response_model=list[ProviderStatus])
async def status_(refresh: bool = False, user: User = Depends(require_authenticated_user)):
    return await provider_status(force=refresh)


@router.post("/search", response_model=SentinelSearchResponse)
async def search(body: SentinelSearchRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    """Discover Sentinel-2 L2A scenes intersecting the AOI in a *before* and an *after* window (no imagery is downloaded)."""
    provider = _provider_or_503()
    try:
        aoi, km2, _ = await svc.resolve_aoi(db, user, aoi_id=body.aoi_id, bbox=body.bbox, center=body.center, radius_m=body.radius_m, geometry=body.geometry)
    except aoi_geo.AoiError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "message": str(exc), "details": exc.details}) from exc
    bw, aw = svc.window_bounds(body.before.start, body.before.end), svc.window_bounds(body.after.start, body.after.end)
    try:
        before, after = await svc.search_windows(provider, aoi, bw, aw, max_cloud=body.max_cloud_cover_pct, limit=body.limit, collection=body.collection)
    except ProviderError as exc:
        _raise(exc)
    warnings: list[str] = []
    if not before:
        warnings.append("No Sentinel-2 L2A scene matched the BEFORE window and cloud limit. Widen the dates or raise the cloud limit.")
    if not after:
        warnings.append("No Sentinel-2 L2A scene matched the AFTER window and cloud limit. Widen the dates or raise the cloud limit.")
    sb, sa = svc.select_scene(before, "before"), svc.select_scene(after, "after")
    for label, sc in (("before", sb), ("after", sa)):
        if sc and (sc.coverage_of_aoi_pct or 100) < 95:
            warnings.append(f"The best {label} scene covers only {sc.coverage_of_aoi_pct:.0f}% of the AOI.")
    if getattr(provider, "imagery_configured", True) is False:
        warnings.append("Imagery retrieval is not configured on this server; you can search but not acquire.")
    return SentinelSearchResponse(provider=provider.name, aoi_geometry=mapping(aoi), aoi_area_km2=km2, before=before, after=after,
                                  suggested_before=sb.product_id if sb else None, suggested_after=sa.product_id if sa else None,
                                  suggestion_rule=svc.SELECTION_RULE, warnings=warnings)


@router.post("/acquire", response_model=AcquireResponse, status_code=status.HTTP_202_ACCEPTED)
async def acquire(body: AcquireRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_user_or_admin)):
    """Queue an analysis whose first stage retrieves the selected (or automatically selected) scenes. Returns immediately."""
    project = await access.load_project(db, body.project_id, user, write=True)
    provider = _provider_or_503(imagery=True)
    try:
        aoi, km2, aoi_row = await svc.resolve_aoi(db, user, aoi_id=body.aoi_id, geometry=body.aoi_geometry)
    except aoi_geo.AoiError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "message": str(exc), "details": exc.details}) from exc
    cfg = effective_config(body.config)
    try:
        if body.auto_select:
            bw, aw = svc.window_bounds(body.before.start, body.before.end), svc.window_bounds(body.after.start, body.after.end)
            if bw[1] >= aw[0]:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "windows_overlap", "message": "The before window must end before the after window starts."})
            before_list, after_list = await svc.search_windows(provider, aoi, bw, aw, max_cloud=body.max_cloud_cover_pct, limit=50, collection="sentinel-2-l2a")
            sb, sa = svc.select_scene(before_list, "before"), svc.select_scene(after_list, "after")
            if sb is None or sa is None:
                missing = " and ".join(n for n, s in (("before", sb), ("after", sa)) if s is None)
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
                    "code": "no_suitable_scene", "message": f"No suitable scene was found for the {missing} window (cloud cover <= {body.max_cloud_cover_pct:.0f}%). "
                    "Adjust the dates or cloud limit instead of accepting an arbitrary scene."})
            scenes = {"before": sb, "after": sa}
        else:
            rb = await provider.get_scene(body.before_product_id)
            ra = await provider.get_scene(body.after_product_id)
            scenes = {"before": svc.scene_out(rb, aoi), "after": svc.scene_out(ra, aoi)}
    except ProviderError as exc:
        _raise(exc)
    sb, sa = scenes["before"], scenes["after"]
    if sb.acquired_at >= sa.acquired_at:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "date_order", "message": "The before scene must be acquired earlier than the after scene."})

    params = {
        "provider": provider.name, "aoi_geometry": mapping(aoi), "aoi_area_km2": km2, "pixel_size_m": body.pixel_size_m,
        "max_cloud_cover_pct": body.max_cloud_cover_pct, "selection": "automatic" if body.auto_select else "manual",
        "selection_rule": svc.SELECTION_RULE if body.auto_select else None,
        "scenes": {k: {"product_id": v.product_id, "collection": v.collection, "acquired_at": v.acquired_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                       "cloud_cover_pct": v.cloud_cover_pct, "coverage_of_aoi_pct": v.coverage_of_aoi_pct, "properties": v.properties}
                   for k, v in scenes.items()},
    }
    # The analysis grid is the acquisition grid (metric, 10 m): keep the working resolution consistent with what is fetched.
    cfg.preprocess.pixel_size_m = float(body.pixel_size_m)
    job = AnalysisJob(
        project_id=project.id, aoi_id=body.aoi_id, created_by=user.id, input_type="sentinel",
        name=(body.name or f"Sentinel-2 {sb.acquired_at:%Y-%m-%d} -> {sa.acquired_at:%Y-%m-%d}")[:160],
        before_date=sb.acquired_at, after_date=sa.acquired_at, config=cfg.to_dict(), acquisition_params=params,
        status="queued", progress=0.0, stage_message="Queued", model_id=cfg.detection.model_id,
        warnings=[{"level": "info", "code": "provider_data", "message": "Imagery retrieved from the Sentinel provider; cloud masking uses the Sentinel-2 scene classification (SCL).", "details": {}}],
    )
    db.add(job)
    await db.flush()
    db.add(AnalysisEvent(analysis_id=job.id, status="queued", progress=0.0, message="Queued (imagery will be retrieved first)"))
    await db.commit()
    return AcquireResponse(analysis_id=job.id, status="queued", before_product_id=sb.product_id, after_product_id=sa.product_id,
                           message="Analysis queued. Scenes are retrieved first, then change detection runs.")


def _is_blank(png: bytes) -> bool:
    """True when the PNG is fully transparent (the provider found no pixels), so callers never display an empty overlay as imagery."""
    import io

    from PIL import Image

    try:
        im = Image.open(io.BytesIO(png))
        return im.mode in ("RGBA", "LA") and im.getchannel("A").getextrema()[1] == 0
    except Exception:
        return False


@router.post("/preview")
async def preview(body: PreviewRequest, user: User = Depends(require_authenticated_user)):
    """True-colour preview PNG of one scene over a small box (consumes a little provider quota; on demand only)."""
    provider = _provider_or_503(imagery=True)
    minx, miny, maxx, maxy = body.bbox
    if not (maxx > minx and maxy > miny) or (maxx - minx) > 0.5 or (maxy - miny) > 0.5:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "bad_bbox", "message": "bbox must be at most 0.5 x 0.5 degrees."})
    height = max(64, min(2048, int(body.width * (maxy - miny) / (maxx - minx))))
    try:
        png = await provider.process_preview_png(bbox_wgs84=(minx, miny, maxx, maxy), acquired_at=body.acquired_at, width=body.width, height=height)
    except ProviderError as exc:
        _raise(exc)
    if _is_blank(png):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "no_data", "message": "The provider returned no image data for this area and date. Try a nearby date."})
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@router.post("/ml-changes")
async def ml_changes(body: MlChangesRequest, user: User = Depends(require_authenticated_user)):
    """Run the learned change-detection model on two retrieved Sentinel-2 images of one box and return the changed areas as GeoJSON."""
    from app.geo.errors import PairIncompatibleError
    from app.services.quick_changes import detect_between

    provider = _provider_or_503(imagery=True)
    minx, miny, maxx, maxy = body.bbox
    if not (maxx > minx and maxy > miny) or (maxx - minx) > 0.5 or (maxy - miny) > 0.5:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "bad_bbox", "message": "bbox must be at most 0.5 x 0.5 degrees."})
    try:
        return await detect_between(provider, (minx, miny, maxx, maxy), body.before_at, body.after_at, model_id=body.model_id, width=body.width)
    except ProviderError as exc:
        _raise(exc)
    except PairIncompatibleError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": getattr(exc, "code", "ml_failed"), "message": str(exc)}) from exc
