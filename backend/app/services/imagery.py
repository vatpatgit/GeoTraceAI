"""Imagery asset ingestion, serialization and previews."""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

import anyio
from fastapi import HTTPException, UploadFile, status
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.config import settings
from app.geo.errors import RasterValidationError
from app.geo.raster_io import RasterInfo, detect_band_roles, inspect_raster, valid_data_fraction
from app.geo.tiles import RasterStyle, render_preview
from app.geo.validation import footprint_polygon
from app.models import ImageryAsset, Project, User
from app.schemas.analysis import ImageryAssetOut
from app.schemas.common import Issue


async def _chunks(upload: UploadFile, size: int = 1 << 20) -> AsyncIterator[bytes]:
    while True:
        chunk = await upload.read(size)
        if not chunk:
            return
        yield chunk


def asset_path(asset: ImageryAsset) -> Path:
    return storage.resolve(asset.storage_path)


def raster_warnings(info: RasterInfo, valid_fraction: float | None, band_info: dict) -> list[Issue]:
    out: list[Issue] = []
    if band_info["needs_confirmation"]:
        out.append(Issue(level="warning", code="band_roles_assumed", message=" ".join(band_info["notes"]), details={"band_map": band_info["band_map"]}))
    elif band_info["notes"]:
        out.append(Issue(level="info", code="band_notes", message=" ".join(band_info["notes"])))
    if valid_fraction is not None and valid_fraction < 0.5:
        out.append(Issue(level="warning", code="high_nodata", message=f"{1 - valid_fraction:.0%} of this raster is NoData/masked.", details={"valid_fraction": valid_fraction}))
    if info.nodata is None and not info.has_alpha and not info.has_dataset_mask:
        out.append(Issue(level="info", code="no_nodata_defined", message="No NoData value or mask is defined; all pixels are treated as valid."))
    if info.is_rotated:
        out.append(Issue(level="warning", code="rotated_transform", message="Rotated/skewed geotransform; it will be resampled onto a north-up grid."))
    if info.gsd_m > 100:
        out.append(Issue(level="warning", code="coarse_resolution", message=f"Ground resolution is {info.gsd_m:.0f} m; small changes will not be detectable."))
    if abs(info.pixel_size_m[0] - info.pixel_size_m[1]) / max(info.pixel_size_m) > 0.1:
        out.append(Issue(level="info", code="non_square_pixels", message="Pixels are not square on the ground; they will be resampled to a square grid."))
    return out


async def ingest_upload(db: AsyncSession, user: User, project: Project, upload: UploadFile, *,
                        acquisition_start: datetime | None = None, acquisition_end: datetime | None = None,
                        band_map: dict[str, int] | None = None, kind: str = "upload", is_demo: bool = False,
                        ) -> tuple[ImageryAsset, list[Issue], bool]:
    """Persist and validate one uploaded raster. Returns (asset, warnings, reused_existing)."""
    asset_id = uuid.uuid4()
    adir = storage.asset_dir(asset_id)
    dest = adir / "original.tif"
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    try:
        size, digest = await storage.save_stream(_chunks(upload), dest, max_bytes=max_bytes)
    except storage.UploadTooLarge as exc:
        storage.remove_tree(f"imagery/{asset_id}")
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc)) from exc
    except Exception:
        storage.remove_tree(f"imagery/{asset_id}")
        raise
    return await register_raster(db, user, project, asset_id, dest, digest, size, upload.filename, kind=kind,
                                 acquisition_start=acquisition_start, acquisition_end=acquisition_end, band_map=band_map,
                                 is_demo=is_demo)


async def register_raster(db: AsyncSession, user: User, project: Project, asset_id: uuid.UUID, dest: Path, digest: str, size: int,
                          filename: str | None, *, kind: str, acquisition_start: datetime | None = None,
                          acquisition_end: datetime | None = None, band_map: dict[str, int] | None = None, is_demo: bool = False,
                          source_provider: str | None = None, source_product_id: str | None = None,
                          cloud_cover_pct: float | None = None, extra_provenance: dict | None = None,
                          dedupe: bool = True) -> tuple[ImageryAsset, list[Issue], bool]:
    """Validate a raster that is already stored at ``dest`` (= storage/imagery/<asset_id>/original.tif) and register it."""
    # Idempotent re-upload: same bytes in the same project => reuse the existing validated asset.
    existing = await db.scalar(select(ImageryAsset).where(
        ImageryAsset.project_id == project.id, ImageryAsset.sha256 == digest, ImageryAsset.created_by == user.id)) if dedupe else None
    if existing is not None:
        storage.remove_tree(f"imagery/{asset_id}")
        info = await anyio.to_thread.run_sync(inspect_raster, asset_path(existing))
        bi = detect_band_roles(info.band_descriptions, info.count)
        return existing, raster_warnings(info, None, bi), True

    try:
        info: RasterInfo = await anyio.to_thread.run_sync(lambda: inspect_raster(dest, max_pixels=settings.MAX_RASTER_PIXELS * 4))
        valid_fraction = await anyio.to_thread.run_sync(valid_data_fraction, dest)
    except RasterValidationError as exc:
        storage.remove_tree(f"imagery/{asset_id}")
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "message": str(exc), "details": exc.details}) from exc

    bi = detect_band_roles(info.band_descriptions, info.count)
    chosen_map = dict(band_map) if band_map else bi["band_map"]
    warnings = raster_warnings(info, valid_fraction, bi if not band_map else {**bi, "needs_confirmation": False, "notes": []})
    footprint = footprint_polygon(info, "EPSG:4326")
    if not footprint.is_valid:
        footprint = footprint.buffer(0)

    display = storage.sanitize_filename(filename)
    asset = ImageryAsset(
        id=asset_id, project_id=project.id, created_by=user.id, kind=kind,
        original_filename=display, storage_path=storage.relative(dest),
        sha256=digest, size_bytes=size, width=info.width, height=info.height, band_count=info.count,
        dtype=info.dtypes[0], crs_epsg=info.crs_epsg, crs_wkt=info.crs_wkt, pixel_size_m=info.gsd_m, nodata=info.nodata,
        footprint=from_shape(footprint, srid=4326), band_descriptions=info.band_descriptions, band_map=chosen_map,
        band_map_confirmed=bool(band_map) or not bi["needs_confirmation"],
        acquisition_start=acquisition_start, acquisition_end=acquisition_end or acquisition_start,
        source_provider=source_provider, source_product_id=source_product_id, cloud_cover_pct=cloud_cover_pct,
        raster_info={**info.to_dict(), "path": None, "valid_fraction": valid_fraction, "band_detection": bi},
        provenance={"registered_by": str(user.id), "registered_at": datetime.utcnow().isoformat() + "Z", "sha256": digest,
                    "original_filename": display, "size_bytes": size, **(extra_provenance or {})},
        is_demo=is_demo,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset, warnings, False


def asset_style(asset: ImageryAsset) -> RasterStyle:
    bm = asset.band_map or {}
    if all(r in bm for r in ("red", "green", "blue")):
        bands = [bm["red"], bm["green"], bm["blue"]]
        return RasterStyle(mode="rgb", bands=bands, stretch=_display_stretch(asset, bands))
    return RasterStyle(mode="gray", bands=[bm.get("gray", bm.get("nir", 1))], stretch=_display_stretch(asset, [bm.get("gray", 1)])[:1])


def _display_stretch(asset: ImageryAsset, bands: list[int]) -> list[tuple[float, float]]:
    """2-98 percentile display stretch from an overview-sized read (cheap, cached in raster_info)."""
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling

    if asset.dtype == "uint8":
        return [(0.0, 255.0)] * len(bands)
    cache = (asset.raster_info or {}).get("display_stretch", {})
    key = ",".join(map(str, bands))
    if key in cache:
        return [tuple(v) for v in cache[key]]
    with rasterio.open(asset_path(asset)) as src:
        scale = max(1.0, (src.width * src.height / 500_000) ** 0.5)
        shape = (max(1, int(src.height / scale)), max(1, int(src.width / scale)))
        arr = src.read(bands, out_shape=(len(bands), *shape), resampling=Resampling.nearest, masked=True)
    out = []
    for i in range(len(bands)):
        vals = arr[i].compressed()
        if vals.size == 0:
            out.append((0.0, 1.0))
            continue
        lo, hi = np.percentile(vals, [2, 98])
        out.append((float(lo), float(hi if hi > lo else lo + 1)))
    return out


async def render_asset_preview(asset: ImageryAsset) -> tuple[bytes, list[list[float]]] | None:
    style = asset_style(asset)
    return await anyio.to_thread.run_sync(lambda: render_preview(str(asset_path(asset)), style, max_dim=1400))


def asset_to_out(asset: ImageryAsset, warnings: list[Issue] | None = None) -> ImageryAssetOut:
    fp = to_shape(asset.footprint)
    minx, miny, maxx, maxy = fp.bounds
    bd = (asset.raster_info or {}).get("band_detection") or {}
    return ImageryAssetOut(
        id=asset.id, project_id=asset.project_id, kind=asset.kind, original_filename=asset.original_filename,
        size_bytes=asset.size_bytes, width=asset.width, height=asset.height, band_count=asset.band_count, dtype=asset.dtype,
        crs_epsg=asset.crs_epsg, pixel_size_m=asset.pixel_size_m, nodata=asset.nodata, footprint=mapping(fp),
        bounds=[minx, miny, maxx, maxy], band_descriptions=asset.band_descriptions, band_map=asset.band_map,
        band_map_confirmed=asset.band_map_confirmed, band_notes=list(bd.get("notes", [])),
        acquisition_start=asset.acquisition_start, acquisition_end=asset.acquisition_end, cloud_cover_pct=asset.cloud_cover_pct,
        source_provider=asset.source_provider, source_product_id=asset.source_product_id, sha256=asset.sha256,
        is_demo=asset.is_demo, warnings=warnings or [], created_at=asset.created_at,
    )
