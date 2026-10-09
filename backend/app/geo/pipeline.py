"""End-to-end bi-temporal change-detection pipeline (pure geospatial; no database)."""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import rasterio
from shapely.geometry.base import BaseGeometry

from app.geo.config import PipelineConfig
from app.geo.detect import DetectionOutput, detect_ndvi_diff, detect_spectral_cva, ndvi_scene_means
from app.geo.errors import GeoProcessingError, PairIncompatibleError
from app.geo.polygonize import ChangeFeatureRecord, grid_area_m2, polygonize_changes
from app.geo.postprocess import clean_mask, write_mask
from app.geo.preprocess import AlignedPair, align_pair

# (stage, overall fraction 0..1, message)
PipelineProgress = Callable[[str, float, str], None]

STAGES = ("validating", "preprocessing", "detecting", "polygonizing")


class JobCancelled(Exception):
    """Raised cooperatively when a cancellation was requested."""


@dataclass
class PipelineResult:
    aligned: AlignedPair
    detection: DetectionOutput
    method_reason: str
    mask_path: str
    score_path: str
    features: list[ChangeFeatureRecord]
    summary: dict[str, Any]
    postprocess: dict[str, Any]
    polygonize: dict[str, Any]
    warnings: list[dict[str, Any]]
    timings: dict[str, float] = field(default_factory=dict)


def select_method(det_method: str, pixel_size_m: float, roles: Sequence[str], *, learned_ready: bool, trained_gsd_m: float = 2.0) -> tuple[str, str]:
    """Pick the detector. Explicit choices are honoured (and validated later); 'auto' follows documented rules."""
    if det_method != "auto":
        return det_method, f"user selected '{det_method}'"
    gsd = pixel_size_m
    rgb = {"red", "green", "blue"} <= set(roles)
    lo, hi = trained_gsd_m / 8.0, trained_gsd_m * 2.0  # scale range the checkpoint tolerates (resampled to its trained GSD)
    if learned_ready and rgb and lo <= gsd <= hi:
        return "learned_siamese", (f"auto: RGB imagery at {gsd:.2f} m is within the trained scale range ({lo:g}-{hi:g} m) "
                                   "and a trained checkpoint is available")
    reasons = []
    if not learned_ready:
        reasons.append("no trained checkpoint available")
    if not rgb:
        reasons.append("RGB bands not all present")
    if not lo <= gsd <= hi:
        reasons.append(f"{gsd:.2f} m ground resolution is outside the model's trained range ({lo:g}-{hi:g} m)")
    return "spectral_cva", "auto: spectral baseline because " + "; ".join(reasons)


def run_pipeline(
    before_path: str | Path,
    after_path: str | Path,
    work_dir: str | Path,
    cfg: PipelineConfig | None = None,
    *,
    aoi_wgs84: dict | BaseGeometry | None = None,
    boundaries: Sequence[tuple[str, str, BaseGeometry]] | None = None,
    progress: PipelineProgress | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> PipelineResult:
    cfg = cfg or PipelineConfig()
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}

    def emit(stage: str, frac: float, msg: str) -> None:
        if cancel_check and cancel_check():
            raise JobCancelled()
        if progress:
            progress(stage, frac, msg)

    # Stage windows within the overall 0..1 progress.
    def sub(stage: str, lo: float, hi: float):
        return lambda f, m: emit(stage, lo + (hi - lo) * max(0.0, min(1.0, f)), m)

    t0 = time.perf_counter()
    emit("validating", 0.0, "Validating inputs")
    emit("preprocessing", 0.05, "Aligning rasters")
    aligned = align_pair(before_path, after_path, work / "aligned", cfg.preprocess, aoi_wgs84=aoi_wgs84,
                         band_map=cfg.detection.band_map, progress=sub("preprocessing", 0.05, 0.35))
    timings["preprocess_s"] = time.perf_counter() - t0

    # --- detection ---------------------------------------------------------------------------------------------
    from app.ml.registry import learned_ready  # lazy: torch is optional for the baseline path
    from app.ml.registry import get_card

    _card = get_card(cfg.detection.model_id)
    method, reason = select_method(cfg.detection.method, aligned.pixel_size_m, aligned.roles,
                                   learned_ready=learned_ready(cfg.detection.model_id), trained_gsd_m=_card.trained_gsd_m if _card else 2.0)
    emit("detecting", 0.36, f"Detecting changes ({method})")
    t1 = time.perf_counter()
    det_dir = work / "detection"
    if method == "spectral_cva":
        detection = detect_spectral_cva(aligned, cfg.detection, det_dir, sub("detecting", 0.36, 0.72))
    elif method == "ndvi_diff":
        detection = detect_ndvi_diff(aligned, cfg.detection, det_dir, sub("detecting", 0.36, 0.72))
    elif method == "learned_siamese":
        from app.ml.detector import detect_learned
        detection = detect_learned(aligned, cfg.detection, det_dir, sub("detecting", 0.36, 0.72), cancel_check=cancel_check)
    else:  # pragma: no cover - guarded by config validation
        raise PairIncompatibleError(f"Unknown detection method {method!r}", code="bad_config")
    timings["detect_s"] = time.perf_counter() - t1

    # --- post-processing + polygons ---------------------------------------------------------------------------
    emit("polygonizing", 0.74, "Cleaning change mask")
    t2 = time.perf_counter()
    with rasterio.open(aligned.valid_mask_path) as ds:
        valid = ds.read(1).astype(bool)
    with rasterio.open(detection.score_path) as ds:
        score = ds.read(1)
    mask, pp_report = clean_mask(score, valid, detection.score_threshold, cfg.postprocess, aligned.pixel_size_m)
    mask_path = write_mask(work / "change_mask.tif", mask, valid, aligned)
    emit("polygonizing", 0.82, "Extracting polygons")
    records, poly_stats = polygonize_changes(mask, score, aligned, detection, cfg.postprocess, cfg.severity,
                                             boundaries=boundaries)
    timings["postprocess_s"] = time.perf_counter() - t2

    grid_m2 = grid_area_m2(aligned)
    analyzed_m2 = grid_m2 * float(valid.mean())
    changed_m2 = float(sum(r.area_m2 for r in records))
    summary = {
        "feature_count": len(records),
        "total_changed_area_m2": changed_m2,
        "analyzed_area_m2": analyzed_m2,
        "changed_fraction": (changed_m2 / analyzed_m2) if analyzed_m2 else 0.0,
        "by_category": dict(Counter(r.category for r in records)),
        "by_severity": dict(Counter(r.severity for r in records)),
        "area_by_category_m2": _sum_by(records, "category"),
        "area_by_severity_m2": _sum_by(records, "severity"),
        "mean_magnitude": float(np.mean([r.magnitude for r in records])) if records else None,
        "valid_fraction": aligned.valid_fraction,
        "method": detection.method,
        "pixel_size_m": aligned.pixel_size_m,
        "grid": {"width": aligned.width, "height": aligned.height, "crs_epsg": aligned.crs_epsg},
        "ndvi": ndvi_scene_means(aligned),
    }
    warnings = list(aligned.warnings)
    if poly_stats.get("truncated"):
        warnings.append({"level": "warning", "code": "features_truncated",
                         "message": f"{poly_stats['dropped_components']} smaller components were dropped to respect the "
                                    f"{cfg.postprocess.max_features}-feature limit.", "details": poly_stats})
    if not records:
        warnings.append({"level": "info", "code": "no_change_detected",
                         "message": "No change exceeded the threshold after filtering. This is a valid result, not an error.",
                         "details": pp_report.to_dict()})
    emit("polygonizing", 0.95, "Finalising")
    return PipelineResult(aligned=aligned, detection=detection, method_reason=reason, mask_path=str(mask_path),
                          score_path=detection.score_path, features=records, summary=summary,
                          postprocess=pp_report.to_dict(), polygonize=poly_stats, warnings=warnings, timings=timings)


def _sum_by(records: Sequence[ChangeFeatureRecord], attr: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in records:
        out[getattr(r, attr)] = out.get(getattr(r, attr), 0.0) + r.area_m2
    return out
