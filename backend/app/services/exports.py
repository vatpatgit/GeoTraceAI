"""Export stored analysis results (GeoJSON / GeoPackage / CSV) honouring the same filters as the map."""
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anyio
from fastapi import HTTPException, status
from shapely.geometry import shape
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.geo.exports import write_geojson, write_geopackage
from app.geo.polygonize import orient_rfc7946
from app.models import AnalysisExport, AnalysisJob, ImageryAsset, User
from app.schemas.change import FeatureFilter
from app.services.analyses import _collapse, all_features

MEDIA_TYPES = {"geojson": "application/geo+json", "gpkg": "application/geopackage+sqlite3", "csv": "text/csv"}
EXT = {"geojson": "geojson", "gpkg": "gpkg", "csv": "csv"}


def _source_label(asset: ImageryAsset | None) -> str | None:
    if asset is None:
        return None
    if asset.source_provider:
        return f"{asset.source_provider}:{asset.source_product_id}"
    return f"{asset.kind}:{asset.original_filename or asset.id}:sha256={asset.sha256[:12]}"


def _asset_record(role: str, a: ImageryAsset | None) -> dict[str, Any] | None:
    if a is None:
        return None
    return {
        "role": role, "asset_id": str(a.id), "kind": a.kind, "filename": a.original_filename, "sha256": a.sha256,
        "provider": a.source_provider, "product_id": a.source_product_id,
        "acquisition_start": a.acquisition_start.isoformat() if a.acquisition_start else None,
        "acquisition_end": a.acquisition_end.isoformat() if a.acquisition_end else None,
        "cloud_cover_pct": a.cloud_cover_pct, "pixel_size_m": a.pixel_size_m, "crs_epsg": a.crs_epsg,
        "width": a.width, "height": a.height, "band_map": a.band_map,
    }


def rows_from_db(db_rows, job: AnalysisJob, before: ImageryAsset | None, after: ImageryAsset | None) -> list[dict[str, Any]]:
    det = (job.processing or {}).get("detection", {})
    out = []
    for r in db_rows:
        f = r[0]
        geom = orient_rfc7946(shape(_collapse(r.gj)))
        out.append({
            "id": str(f.id), "feature_id": str(f.id), "analysis_id": str(job.id), "geometry": geom,
            "category": f.category, "category_basis": f.category_basis, "area_m2": f.area_m2, "perimeter_m": f.perimeter_m,
            "centroid_lon": r.cx, "centroid_lat": r.cy, "magnitude": f.magnitude, "magnitude_kind": det.get("magnitude_kind"),
            "confidence": f.confidence, "confidence_kind": det.get("confidence_kind"), "severity": f.severity,
            "severity_basis": "heuristic_priority_not_a_probability", "before_date": job.before_date, "after_date": job.after_date,
            "detection_method": job.method, "model_id": job.model_id, "review_status": f.review_status,
            "distance_to_boundary_m": f.distance_to_boundary_m, "before_source": _source_label(before),
            "after_source": _source_label(after), "is_demo": job.is_demo,
        })
    return out


def analysis_metadata(job: AnalysisJob, flt: FeatureFilter, scope: str, count: int) -> dict[str, Any]:
    return {
        "analysis_id": str(job.id), "analysis_name": job.name, "project_id": str(job.project_id), "status": job.status,
        "method": job.method, "method_reason": job.method_reason, "model_id": job.model_id,
        "before_date": job.before_date, "after_date": job.after_date, "crs": "EPSG:4326", "feature_count": count,
        "scope": scope, "filters": flt.model_dump(mode="json", exclude_none=True), "summary": job.summary,
        "config": job.config, "is_demo": job.is_demo,
        "data_origin": "DEMO: synthetic / seeded data, not real satellite imagery" if job.is_demo else "live",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Detections are observed image differences. Categories, severity and any model score are heuristic or "
                      "model-inferred and require human verification; severity is not a calibrated probability.",
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["feature_id", "analysis_id", "category", "category_basis", "area_m2", "perimeter_m", "centroid_lon", "centroid_lat",
              "magnitude", "confidence", "severity", "review_status", "before_date", "after_date", "detection_method", "model_id",
              "distance_to_boundary_m", "before_source", "after_source", "is_demo", "geometry_wkt"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        rec = {k: ("" if r.get(k) is None else r.get(k)) for k in fields}
        rec["geometry_wkt"] = r["geometry"].wkt
        for k in ("before_date", "after_date"):
            if hasattr(r.get(k), "isoformat"):
                rec[k] = r[k].isoformat()
        w.writerow(rec)
    with path.open("w", encoding="utf-8", newline="") as fh:  # csv writes its own 

        fh.write(buf.getvalue())


async def create_export(db: AsyncSession, user: User, job: AnalysisJob, fmt: str, flt: FeatureFilter, scope: str,
                        before: ImageryAsset | None, after: ImageryAsset | None) -> tuple[AnalysisExport, Path]:
    if job.status != "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Results can be exported once the analysis has completed.")
    db_rows = await all_features(db, job, flt)
    rows = rows_from_db(db_rows, job, before, after)
    export_id = uuid.uuid4()
    rel_dir = storage.analysis_dir(job.id) / "exports"
    rel_dir.mkdir(parents=True, exist_ok=True)
    path = rel_dir / f"{export_id}.{EXT[fmt]}"
    meta = analysis_metadata(job, flt, scope, len(rows))
    try:
        if fmt == "geojson":
            await anyio.to_thread.run_sync(lambda: write_geojson(path, rows, meta))
        elif fmt == "gpkg":
            imagery = [x for x in (_asset_record("before", before), _asset_record("after", after)) if x]
            await anyio.to_thread.run_sync(lambda: write_geopackage(path, rows, analysis=meta, imagery=imagery))
        else:
            await anyio.to_thread.run_sync(lambda: _write_csv(path, rows))
    except Exception as exc:
        path.unlink(missing_ok=True)
        rec = AnalysisExport(id=export_id, analysis_id=job.id, created_by=user.id, format=fmt, scope=scope,
                             filters=flt.model_dump(mode="json", exclude_none=True), status="failed", error=str(exc)[:500])
        db.add(rec)
        await db.commit()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Export failed: {exc}") from exc
    rec = AnalysisExport(id=export_id, analysis_id=job.id, created_by=user.id, format=fmt, scope=scope,
                         filters=flt.model_dump(mode="json", exclude_none=True), status="completed", feature_count=len(rows),
                         size_bytes=path.stat().st_size, storage_path=storage.relative(path))
    db.add(rec)
    await db.commit()
    return rec, path
