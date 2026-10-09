"""Runs one analysis job end to end: (acquire) -> pipeline -> persist -> alerts."""
from __future__ import annotations

import asyncio
import logging
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon, Point, Polygon, box
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.database import async_session_maker
from app.geo.config import PipelineConfig
from app.geo.errors import GeoProcessingError
from app.geo.pipeline import JobCancelled, PipelineResult, run_pipeline
from app.providers.base import ProviderError
from app.models import (AnalysisEvent, AnalysisJob, AreaOfInterest, ChangeFeature, ImageryAsset, Region)
from app.services import alert_engine
from app.services.imagery import asset_path

logger = logging.getLogger(__name__)

STAGE_TO_STATUS = {
    "validating": "validating", "acquiring": "acquiring_imagery", "preprocessing": "preprocessing",
    "detecting": "detecting_changes", "polygonizing": "polygonizing",
}
# Artifacts kept per analysis (name -> source file inside the temp work dir)
ARTIFACT_SOURCES = {
    "change_mask": "change_mask.tif",
    "change_score": "detection/change_score.tif",
    "before_aligned": "aligned/before_aligned.tif",
    "after_aligned": "aligned/after_aligned.tif",
    "valid_mask": "aligned/valid_mask.tif",
    "delta_ndvi": "detection/delta_ndvi.tif",
}


class _Progress:
    """Thread-safe bridge: pipeline (worker thread) -> DB events (event loop)."""

    def __init__(self, loop: asyncio.AbstractEventLoop, job_id):
        self.loop, self.job_id = loop, job_id
        self.cancelled = threading.Event()
        self._last = 0.0
        self._last_status = None
        self._lock = asyncio.Lock()
        self.base = 0.0  # share of the 0..0.9 range already used by imagery acquisition
        self._written = -1.0  # progress already persisted; updates arrive from a worker thread and may be reordered

    def callback(self, stage: str, frac: float, message: str) -> None:
        now = time.monotonic()
        status = STAGE_TO_STATUS.get(stage, stage)
        if status == self._last_status and now - self._last < 1.0 and frac < 0.99 and stage != "acquiring":
            return  # throttle chatty updates; always write on stage change
        self._last, self._last_status = now, status
        p = 0.1 * frac if stage == "acquiring" else self.base + (0.9 - self.base) * frac
        asyncio.run_coroutine_threadsafe(self._write(status, p, message), self.loop)

    async def _write(self, status: str, progress: float, message: str) -> None:
        async with self._lock:
            if progress < self._written:
                return  # stale update that lost the race against a later one
            self._written = progress
            await self._write_locked(status, progress, message)

    async def _write_locked(self, status: str, progress: float, message: str) -> None:
        # Conditional UPDATE: a progress write that was already in flight when the job reached a terminal state
        # must not resurrect it (read-modify-write on the ORM object would be last-writer-wins).
        async with async_session_maker() as db:
            res = await db.execute(
                update(AnalysisJob)
                .where(AnalysisJob.id == self.job_id, AnalysisJob.status.notin_(("completed", "failed", "cancelled")))
                .values(status=status, progress=round(progress, 4), stage_message=message[:300], heartbeat_at=datetime.now(timezone.utc))
            )
            if res.rowcount:
                db.add(AnalysisEvent(analysis_id=self.job_id, status=status, progress=round(progress, 4), message=message[:300]))
            await db.commit()


class _AsyncProgress:
    """Adapts the thread-oriented progress sink for callers already running on the event loop."""

    def __init__(self, inner: _Progress):
        self.inner = inner

    def callback(self, stage: str, frac: float, message: str) -> None:
        p = 0.1 * frac if stage == "acquiring" else frac
        asyncio.get_running_loop().create_task(self.inner._write(STAGE_TO_STATUS.get(stage, stage), p, message))


async def _watch_cancel(job_id, progress: _Progress) -> None:
    while True:
        await asyncio.sleep(1.5)
        async with async_session_maker() as db:
            job = await db.get(AnalysisJob, job_id)
            if job is None or job.cancel_requested:
                progress.cancelled.set()
                return
            job.heartbeat_at = datetime.now(timezone.utc)
            await db.commit()


async def _fail(job_id, code: str, message: str, details: dict | None = None) -> None:
    async with async_session_maker() as db:
        job = await db.get(AnalysisJob, job_id)
        if job is None:
            return
        job.status = "failed"
        job.error = {"code": code, "message": message, "details": details or {}}
        job.stage_message = message[:300]
        job.finished_at = datetime.now(timezone.utc)
        job.locked_by = None
        db.add(AnalysisEvent(analysis_id=job.id, status="failed", progress=job.progress, message=message[:300]))
        await db.commit()


async def _boundaries(db: AsyncSession, bounds_hint: Polygon | None) -> list[tuple[str, str, Any]]:
    """Monitored region polygons (to measure proximity). Limited to those near the imagery footprint."""
    from geoalchemy2.shape import to_shape
    from sqlalchemy import func

    q = select(Region.id, Region.name, Region.geometry)
    if bounds_hint is not None:
        q = q.where(func.ST_DWithin(Region.geometry, func.ST_GeomFromText(bounds_hint.wkt, 4326), 1.0))
    rows = (await db.execute(q.limit(200))).all()
    return [(str(r.id), r.name, to_shape(r.geometry)) for r in rows]


def _display_stretch(aligned_path: str, dtype_is_u8: bool, count: int) -> list[tuple[float, float]]:
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling

    if dtype_is_u8:
        return [(0.0, 255.0)] * count
    with rasterio.open(aligned_path) as ds:
        scale = max(1.0, (ds.width * ds.height / 500_000) ** 0.5)
        shape = (max(1, int(ds.height / scale)), max(1, int(ds.width / scale)))
        arr = ds.read(out_shape=(ds.count, *shape), resampling=Resampling.nearest, masked=False).astype("float32")
        with rasterio.open(Path(aligned_path).with_name("valid_mask.tif")) as vm:
            valid = vm.read(1, out_shape=shape, resampling=Resampling.nearest) > 0
    out = []
    for i in range(count):
        vals = arr[i][valid]
        if vals.size == 0:
            out.append((0.0, 1.0))
            continue
        lo, hi = np.percentile(vals, [2, 98])
        out.append((float(lo), float(hi if hi > lo else lo + 1)))
    return out


def _joint_stretch(res: PipelineResult) -> dict[str, Any]:
    """One display stretch per band shared by BOTH dates so the before/after slider compares like with like."""
    import numpy as np
    import rasterio

    a = res.aligned
    with rasterio.open(a.before_path) as ds:
        u8 = ds.dtypes[0] == "uint8"
    sb = _display_stretch(a.before_path, u8, len(a.roles))
    sa = _display_stretch(a.after_path, u8, len(a.roles))
    joint = [(min(x[0], y[0]), max(x[1], y[1])) for x, y in zip(sb, sa)]
    return {"roles": a.roles, "stretch": joint, "dtype_uint8": u8}


async def execute_analysis(job_id) -> None:
    loop = asyncio.get_running_loop()
    progress = _Progress(loop, job_id)
    workdir: Path | None = None
    watcher: asyncio.Task | None = None
    try:
        async with async_session_maker() as db:
            job = await db.get(AnalysisJob, job_id)
            if job is None:
                return
            before = await db.get(ImageryAsset, job.before_asset_id) if job.before_asset_id else None
            after = await db.get(ImageryAsset, job.after_asset_id) if job.after_asset_id else None
            aoi_poly = None
            if job.aoi_id:
                from geoalchemy2.shape import to_shape
                aoi = await db.get(AreaOfInterest, job.aoi_id)
                aoi_poly = to_shape(aoi.geometry) if aoi else None
            cfg = PipelineConfig.from_dict(job.config)
            input_type = job.input_type
            # features from an earlier attempt are removed so a retry is idempotent
            await db.execute(delete(ChangeFeature).where(ChangeFeature.analysis_id == job_id))
            job.error = None
            await db.commit()

        watcher = asyncio.create_task(_watch_cancel(job_id, progress))
        if before is None or after is None:
            if input_type == "sentinel":
                from app.services.sentinel import acquire_for_job
                await progress._write("acquiring_imagery", 0.0, "Contacting the imagery provider")
                before, after = await acquire_for_job(job_id, _AsyncProgress(progress))
                progress.base = 0.1
            else:
                await _fail(job_id, "missing_imagery", "The before/after imagery for this analysis is no longer available.")
                return

        async with async_session_maker() as db:
            fp = None
            from geoalchemy2.shape import to_shape
            if before is not None:
                fp = to_shape(before.footprint)
            boundaries = await _boundaries(db, fp)

        workdir = storage.new_workdir(f"an-{str(job_id)[:8]}")
        t0 = time.perf_counter()
        res: PipelineResult = await asyncio.to_thread(
            run_pipeline, asset_path(before), asset_path(after), workdir, cfg,
            aoi_wgs84=aoi_poly, boundaries=boundaries, progress=progress.callback, cancel_check=progress.cancelled.is_set,
        )
        stretch = await asyncio.to_thread(_joint_stretch, res)
        await _persist(job_id, res, stretch, workdir, time.perf_counter() - t0)
    except JobCancelled:
        async with async_session_maker() as db:
            job = await db.get(AnalysisJob, job_id)
            if job is not None:
                job.status, job.stage_message = "cancelled", "Cancelled by user"
                job.finished_at = datetime.now(timezone.utc)
                job.locked_by = None
                db.add(AnalysisEvent(analysis_id=job.id, status="cancelled", progress=job.progress, message="Cancelled by user"))
                await db.commit()
    except ProviderError as exc:
        logger.info("analysis %s: provider error %s", job_id, exc.code)
        await _fail(job_id, exc.code, str(exc))
    except GeoProcessingError as exc:
        logger.info("analysis %s failed: %s", job_id, exc)
        await _fail(job_id, exc.code, str(exc), exc.details)
    except Exception as exc:
        logger.exception("analysis %s crashed", job_id)
        await _fail(job_id, "internal_error", "An unexpected error occurred while processing this analysis.",
                    {"type": type(exc).__name__})
    finally:
        if watcher:
            watcher.cancel()
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)


async def _persist(job_id, res: PipelineResult, stretch: dict, workdir: Path, elapsed: float) -> None:
    from pyproj import Transformer
    from shapely.geometry import MultiPolygon

    adir = storage.analysis_dir(job_id)
    artifacts: dict[str, str] = {}
    for name, rel in ARTIFACT_SOURCES.items():
        src = workdir / rel
        if src.exists():
            dst = adir / f"{name}.tif"
            shutil.move(str(src), dst)
            artifacts[name] = storage.relative(dst)
    a = res.aligned
    # footprint of the analysed grid in WGS84
    import rasterio
    from rasterio.warp import transform_bounds
    with rasterio.open(adir / "valid_mask.tif") as ds:
        bounds = list(transform_bounds(ds.crs, "EPSG:4326", *ds.bounds))

    async with async_session_maker() as db:
        job = await db.get(AnalysisJob, job_id)
        job.status, job.progress, job.stage_message = "polygonizing", 0.92, f"Saving {len(res.features)} features"
        db.add(AnalysisEvent(analysis_id=job.id, status="polygonizing", progress=0.92, message=job.stage_message))
        for r in res.features:
            geom = r.geometry if isinstance(r.geometry, MultiPolygon) else MultiPolygon([r.geometry])
            db.add(ChangeFeature(
                analysis_id=job_id, seq=r.index, geometry=from_shape(geom, srid=4326),
                centroid=from_shape(Point(r.centroid_lon, r.centroid_lat), srid=4326),
                point_on_surface=from_shape(Point(r.point_lon, r.point_lat), srid=4326),
                category=r.category, category_basis=r.category_basis, area_m2=r.area_m2, perimeter_m=r.perimeter_m,
                pixel_count=r.pixel_count, magnitude=r.magnitude, magnitude_max=r.magnitude_max, confidence=r.confidence,
                delta_ndvi=r.delta_ndvi, severity=r.severity, severity_reasons=r.severity_reasons,
                distance_to_boundary_m=r.distance_to_boundary_m,
                nearest_region_id=_uuid_or_none(r.nearest_boundary_id) if r.distance_to_boundary_m is not None else None,
            ))
        await db.flush()
        det = res.detection.to_dict()
        det.pop("score_path", None)
        det.pop("delta_ndvi_path", None)
        job.method, job.method_reason = res.detection.method, res.method_reason
        job.model_id = (res.detection.details or {}).get("model_id", job.model_id) if res.detection.method == "learned_siamese" else None
        job.summary = res.summary
        job.warnings = res.warnings
        job.validation = a.validation
        job.processing = {
            "detection": {**det, "score_threshold": res.detection.score_threshold},
            "postprocess": res.postprocess, "polygonize": res.polygonize, "timings": {**res.timings, "total_s": round(elapsed, 2)},
            "grid": {"width": a.width, "height": a.height, "pixel_size_m": a.pixel_size_m, "crs_epsg": a.crs_epsg, "roles": a.roles,
                     "valid_fraction": a.valid_fraction, "transform": list(a.transform)},
            "registration": a.registration, "resampling": a.resampling, "display": stretch,
        }
        job.artifacts = artifacts
        job.bounds_wgs84 = bounds
        await db.commit()

    # alerts
    async with async_session_maker() as db:
        job = await db.get(AnalysisJob, job_id)
        job.status, job.progress, job.stage_message = "evaluating_alerts", 0.96, "Evaluating alert rules"
        db.add(AnalysisEvent(analysis_id=job.id, status="evaluating_alerts", progress=0.96, message=job.stage_message))
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()
        alert_summary = await alert_engine.evaluate_analysis(db, job)
        job = await db.get(AnalysisJob, job_id)
        job.summary = {**(job.summary or {}), "alerts": alert_summary}
        job.status, job.progress = "completed", 1.0
        job.stage_message = f"Completed: {len(res.features)} change polygon(s)"
        job.finished_at = datetime.now(timezone.utc)
        job.locked_by = None
        db.add(AnalysisEvent(analysis_id=job.id, status="completed", progress=1.0, message=job.stage_message))
        await db.commit()


def _uuid_or_none(v):
    import uuid
    try:
        return uuid.UUID(str(v)) if v else None
    except ValueError:
        return None
