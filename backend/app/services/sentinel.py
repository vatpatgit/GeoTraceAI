"""Sentinel search / scene selection / acquisition orchestration."""
from __future__ import annotations

import shutil
import uuid
from datetime import date, datetime, time, timezone
from typing import Any

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.config import settings
from app.database import async_session_maker
from app.geo import aoi as aoi_geo
from app.geo.errors import GeoProcessingError
from app.geo.polygonize import geodesic_area_m2
from app.models import AnalysisJob, AreaOfInterest, ImageryAsset, Project, SatelliteAcquisition, User
from app.providers.acquire import aoi_hash, download_scene, new_asset_path, plan_grid
from app.providers.base import ProviderError, ProviderNotConfigured, SceneRecord
from app.providers.sentinel import get_provider
from app.schemas.sentinel import SceneOut
from app.services.imagery import asset_path, register_raster

SELECTION_RULE = (
    "Within each date window: (1) keep scenes covering at least 95% of the AOI (or, if none do, the best-covering ones); "
    "(2) prefer the lowest cloud cover (differences under 5 percentage points are treated as equal); "
    "(3) break ties by being closest to the other window, i.e. the latest 'before' and the earliest 'after' scene, "
    "to keep the interval between acquisitions as short as possible."
)


def window_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (datetime.combine(start, time.min, tzinfo=timezone.utc), datetime.combine(end, time.max.replace(microsecond=0), tzinfo=timezone.utc))


def coverage_pct(footprint: dict[str, Any] | None, aoi: BaseGeometry) -> float | None:
    if not footprint:
        return None
    try:
        inter = shape(footprint).intersection(aoi)
        return float(min(100.0, 100.0 * inter.area / aoi.area)) if aoi.area else None
    except Exception:
        return None


def scene_out(s: SceneRecord, aoi: BaseGeometry) -> SceneOut:
    return SceneOut(product_id=s.product_id, collection=s.collection, provider=s.provider, acquired_at=s.acquired_at,
                    cloud_cover_pct=s.cloud_cover_pct, footprint=s.footprint, coverage_of_aoi_pct=coverage_pct(s.footprint, aoi),
                    resolution_m=s.resolution_m, platform=s.platform, processing_level=s.processing_level, properties=s.properties)


def group_scenes(records: list[SceneRecord], aoi: BaseGeometry) -> list[SceneOut]:
    """Merge the per-MGRS-tile catalogue items of ONE acquisition into one scene.

    A Sentinel-2 pass is catalogued as a separate item per 100 km tile, all with (almost) the same timestamp. For the
    user these are one acquisition: coverage is measured on the union of the tiles' footprints, cloud cover is the
    AOI-area-weighted mean of the tiles that actually intersect the AOI.
    """
    from shapely.ops import unary_union

    groups: list[list[SceneRecord]] = []
    for r in sorted(records, key=lambda x: x.acquired_at):
        for g in groups:
            if abs((g[0].acquired_at - r.acquired_at).total_seconds()) <= 60 and g[0].platform == r.platform:
                g.append(r)
                break
        else:
            groups.append([r])
    out: list[SceneOut] = []
    for g in groups:
        geoms = [shape(r.footprint) for r in g if r.footprint]
        union = unary_union(geoms) if geoms else None
        weights = []
        for r in g:
            w = shape(r.footprint).intersection(aoi).area if r.footprint else 0.0
            weights.append(w)
        cc = None
        known = [(r.cloud_cover_pct, w) for r, w in zip(g, weights) if r.cloud_cover_pct is not None and w > 0]
        if known:
            tw = sum(w for _, w in known)
            cc = sum(c * w for c, w in known) / tw if tw else sum(c for c, _ in known) / len(known)
        elif any(r.cloud_cover_pct is not None for r in g):
            vals = [r.cloud_cover_pct for r in g if r.cloud_cover_pct is not None]
            cc = sum(vals) / len(vals)
        first = g[0]
        so = scene_out(first, aoi)
        so.footprint = mapping(union) if union is not None else None
        so.coverage_of_aoi_pct = coverage_pct(so.footprint, aoi)
        so.cloud_cover_pct = cc
        so.properties = {**first.properties, "tile_ids": [r.product_id for r in g], "tile_cloud_cover_pct": [r.cloud_cover_pct for r in g]}
        out.append(so)
    return out


def select_scene(scenes: list[SceneOut], role: str) -> SceneOut | None:
    """Documented automatic selection rule (see SELECTION_RULE)."""
    if not scenes:
        return None
    full = [s for s in scenes if (s.coverage_of_aoi_pct or 0) >= 95.0]
    pool = full or sorted(scenes, key=lambda s: -(s.coverage_of_aoi_pct or 0))[: max(1, len(scenes) // 2)]
    best_cc = min((s.cloud_cover_pct if s.cloud_cover_pct is not None else 100.0) for s in pool)
    pool = [s for s in pool if (s.cloud_cover_pct if s.cloud_cover_pct is not None else 100.0) <= best_cc + 5.0]
    return max(pool, key=lambda s: s.acquired_at) if role == "before" else min(pool, key=lambda s: s.acquired_at)


async def resolve_aoi(db: AsyncSession, user: User, *, aoi_id=None, bbox=None, center=None, radius_m=None, geometry=None):
    """Returns (shapely polygon WGS84, area_km2, aoi_row|None). Validates size/shape."""
    row = None
    try:
        if aoi_id:
            row = await db.get(AreaOfInterest, aoi_id)
            if row is None:
                raise aoi_geo.AoiError("AOI not found")
            from app.services import access
            await access.load_project(db, row.project_id, user)
            poly = to_shape(row.geometry)
        elif bbox:
            poly = aoi_geo.bbox_polygon(bbox)
        elif center:
            poly = aoi_geo.circle_polygon(center[0], center[1], radius_m)
        else:
            poly = aoi_geo.polygon_from_geojson(geometry)
        poly, km2 = aoi_geo.finalize_aoi(poly, max_km2=settings.MAX_AOI_KM2)
    except aoi_geo.AoiError:
        raise
    return poly, km2, row


async def search_windows(provider, aoi: BaseGeometry, before: tuple[datetime, datetime], after: tuple[datetime, datetime], *,
                         max_cloud: float, limit: int, collection: str):
    gj = mapping(aoi)
    # Over-fetch: each acquisition is catalogued once per tile, and tile-level cloud cover can exceed the limit while the
    # AOI-weighted mean does not (the cloud limit is re-applied to the grouped scene below).
    b = await provider.search(gj, before[0], before[1], max_cloud_pct=max_cloud, limit=min(limit * 3, 100), collection=collection)
    a = await provider.search(gj, after[0], after[1], max_cloud_pct=max_cloud, limit=min(limit * 3, 100), collection=collection)
    gb = [s for s in group_scenes(b, aoi) if s.cloud_cover_pct is None or s.cloud_cover_pct <= max_cloud][:limit]
    ga = [s for s in group_scenes(a, aoi) if s.cloud_cover_pct is None or s.cloud_cover_pct <= max_cloud][:limit]
    return gb, ga


# ---------------------------------------------------------------------------------------------- job stage
async def acquire_for_job(job_id: uuid.UUID, progress) -> tuple[ImageryAsset, ImageryAsset]:
    """Executed inside the analysis job ('acquiring_imagery'): retrieve both scenes (reusing earlier downloads) and register them.

    Idempotent: a scene already retrieved for the same user/AOI/resolution is reused (no repeat of billable provider calls).
    """
    provider = get_provider()
    if provider is None:
        raise ProviderNotConfigured("Sentinel integration is disabled on this server.")
    async with async_session_maker() as db:
        job = await db.get(AnalysisJob, job_id)
        params = job.acquisition_params or {}
        user = await db.get(User, job.created_by)
        project = await db.get(Project, job.project_id)
    aoi_gj = params["aoi_geometry"]
    ps = float(params.get("pixel_size_m", 10.0))
    plan = plan_grid(aoi_gj, ps)
    ahash = aoi_hash(aoi_gj, ps)
    assets: dict[str, ImageryAsset] = {}
    for idx, role in enumerate(("before", "after")):
        sc = params["scenes"][role]
        acquired = datetime.fromisoformat(sc["acquired_at"].replace("Z", "+00:00"))

        def report(f: float, msg: str, _i=idx, _role=role) -> None:
            progress.callback("acquiring", (_i + f) / 2.0, f"{_role.title()} scene: {msg}")

        async with async_session_maker() as db:
            acq = await db.scalar(select(SatelliteAcquisition).where(
                SatelliteAcquisition.provider == provider.name, SatelliteAcquisition.product_id == sc["product_id"],
                SatelliteAcquisition.created_by == user.id, SatelliteAcquisition.aoi_id.is_(None) | (SatelliteAcquisition.aoi_id == job.aoi_id)))
            reuse = None
            if acq and acq.status == "ready" and acq.asset_id and (acq.request_params or {}).get("aoi_hash") == ahash:
                reuse = await db.get(ImageryAsset, acq.asset_id)
                if reuse is not None and not asset_path(reuse).is_file():
                    reuse = None
            if reuse is not None:
                assets[role] = reuse
                report(1.0, "reused earlier download")
                continue
            if acq is None:
                acq = SatelliteAcquisition(project_id=project.id, created_by=user.id, aoi_id=job.aoi_id, provider=provider.name,
                                           collection=sc.get("collection", "sentinel-2-l2a"), product_id=sc["product_id"],
                                           acquired_at=acquired, cloud_cover_pct=sc.get("cloud_cover_pct"),
                                           properties=sc.get("properties"), request_params={"aoi_hash": ahash, "pixel_size_m": ps})
                db.add(acq)
            acq.status, acq.error = "downloading", None
            acq.request_params = {"aoi_hash": ahash, "pixel_size_m": ps}
            await db.commit()
            acq_id = acq.id

        asset_id, dest = new_asset_path()
        try:
            meta = await download_scene(provider, plan, acquired, dest, progress=report, cancel_check=progress.inner.cancelled.is_set, tags={
                "provider": provider.name, "product_id": sc["product_id"], "acquired_at": acquired.isoformat(), "role": role})
            digest = storage.sha256_file(dest)
            async with async_session_maker() as db:
                user = await db.get(User, job.created_by)
                project = await db.get(Project, job.project_id)
                asset, _, _ = await register_raster(
                    db, user, project, asset_id, dest, digest, dest.stat().st_size, f"{sc['product_id']}.tif", kind="sentinel",
                    acquisition_start=acquired, source_provider=provider.name, source_product_id=sc["product_id"],
                    cloud_cover_pct=sc.get("cloud_cover_pct"), dedupe=False,
                    extra_provenance={"collection": sc.get("collection"), "aoi_hash": ahash, "retrieval": meta, "scene": sc,
                                      "processing": "Sentinel Hub Process API, reflectance x10000 (UINT16), bands B02,B03,B04,B08,SCL,dataMask",
                                      "attribution": "Contains modified Copernicus Sentinel data"})
                acq = await db.get(SatelliteAcquisition, acq_id)
                acq.status, acq.asset_id = "ready", asset.id
                await db.commit()
                assets[role] = asset
        except Exception as exc:
            storage.remove_tree(f"imagery/{asset_id}")
            async with async_session_maker() as db:
                acq = await db.get(SatelliteAcquisition, acq_id)
                if acq:
                    acq.status, acq.error = "failed", str(exc)[:500]
                    await db.commit()
            raise
    async with async_session_maker() as db:
        job = await db.get(AnalysisJob, job_id)
        job.before_asset_id, job.after_asset_id = assets["before"].id, assets["after"].id
        await db.commit()
    return assets["before"], assets["after"]
