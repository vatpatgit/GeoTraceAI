"""On-demand ML change detection between two retrieved Sentinel-2 true-colour images (no database records are created).

The two images are the same display previews the compare map shows (8-bit RGB over one bounding box). They are written as
georeferenced GeoTIFFs and run through the real pipeline with the learned Siamese model, so alignment, tiling, thresholding,
polygonisation and geodesic areas are exactly the production code paths.
"""
from __future__ import annotations

import asyncio
import io
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from scipy import ndimage
from PIL import Image
from rasterio.transform import from_bounds
from shapely.geometry import mapping

from app.geo.config import DetectionConfig, PipelineConfig
from app.geo.errors import PairIncompatibleError
from app.geo.pipeline import run_pipeline
from app.ml.registry import get_card, learned_ready

MAX_FEATURES = 2000
SENTINEL_MODEL_ID = "oscd-s2-v1"  # fine-tuned on real Sentinel-2 pairs; preferred here when installed
_GATE = asyncio.Semaphore(1)  # one model run at a time (GPU / CPU bound)


def _disclaimer(card) -> str:
    base = "Model-inferred candidates to inspect, not confirmed change; clouds, haze, shadows and seasonal colour shifts can cause false detections."
    if card is None:
        return base
    test = (card.metrics or {}).get("test")
    if card.trained_gsd_m >= 5 and test:
        return (f"Model fine-tuned on {card.dataset} Sentinel-2 urban-change pairs; F1 {test['f1']:.2f} on {test['num_samples']} held-out {card.dataset} scenes "
                f"(not validated on this area). {base}")
    return (f"The model ({card.dataset}) was trained on higher-resolution imagery and is not validated on Sentinel-2. {base}")


def _write_rgb_tiff(png: bytes, bbox: tuple[float, float, float, float], path: Path, bad: np.ndarray | None = None, crs: str = "EPSG:4326") -> tuple[int, float]:
    """PNG (RGBA) -> 3-band uint8 GeoTIFF over ``bbox`` expressed in ``crs``; fully transparent pixels become nodata (0). Returns (width, valid share)."""
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    arr = np.asarray(im)
    rgb = arr[..., :3].copy()
    valid = arr[..., 3] > 0
    if bad is not None:
        valid = valid & ~bad
    rgb[~valid] = 0
    rgb[valid & (rgb.sum(axis=2) == 0)] = 1  # keep real (dark) pixels distinct from nodata
    h, w = valid.shape
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w, count=3, dtype="uint8", crs=crs, nodata=0,
                       transform=from_bounds(*bbox, w, h), compress="deflate") as dst:
        dst.write(np.moveaxis(rgb, 2, 0))
        dst.descriptions = ("red", "green", "blue")
    return w, float(valid.mean())


async def detect_between(provider: Any, bbox: tuple[float, float, float, float], before_at: datetime, after_at: datetime,
                         *, model_id: str | None, width: int) -> dict[str, Any]:
    """Sentinel-2: fetch both previews + cloud/shadow masks from the provider, then run the model."""
    model_id = model_id or (SENTINEL_MODEL_ID if learned_ready(SENTINEL_MODEL_ID) else None)
    height = max(64, min(2048, int(width * (bbox[3] - bbox[1]) / (bbox[2] - bbox[0]))))
    kw = dict(bbox_wgs84=bbox, width=width, height=height)
    pngs = await asyncio.gather(*[provider.process_preview_png(acquired_at=t, **kw) for t in (before_at, after_at)])
    masks = await asyncio.gather(*[provider.process_badmask_png(acquired_at=t, **kw) for t in (before_at, after_at)])
    bad = np.zeros((height, width), dtype=bool)
    for m in masks:  # a pixel that is cloud / shadow / cirrus / no-data in EITHER image cannot be compared
        bad |= np.asarray(Image.open(io.BytesIO(m)).convert("RGBA").resize((width, height)))[..., 3] > 0
    # grow the mask: cloud edges are hazy and cloud shadows sit next to the cloud
    bad = ndimage.binary_dilation(bad, iterations=max(2, width // 150))
    mid_lat = (bbox[1] + bbox[3]) / 2
    px_m = max((bbox[2] - bbox[0]) * 111_320 * float(np.cos(np.radians(mid_lat))) / width, (bbox[3] - bbox[1]) * 110_574 / height)
    return await detect_from_images(pngs, bad, bounds=bbox, crs="EPSG:4326", px_m=px_m, model_id=model_id)


async def detect_from_images(pngs: list[bytes], bad: np.ndarray, *, bounds: tuple[float, float, float, float], crs: str, px_m: float,
                             model_id: str | None) -> dict[str, Any]:
    """Run the learned model on two RGBA PNGs rendered over the SAME ``bounds`` (in ``crs``) and the same pixel grid."""
    if not learned_ready(model_id):
        raise PairIncompatibleError("No trained change-detection model is installed on this server (see ML/scripts/export_for_backend.py).",
                                    code="model_unavailable")
    with tempfile.TemporaryDirectory(prefix="gt_quick_") as tmp:
        tmp_path = Path(tmp)
        paths, valid = [], []
        for name, png in zip(("before", "after"), pngs):
            p = tmp_path / f"{name}.tif"
            _, v = _write_rgb_tiff(png, bounds, p, bad, crs)
            paths.append(p)
            valid.append(v)
        if min(valid) < 0.05:  # after cloud/shadow masking
            raise PairIncompatibleError("One of the images has (almost) no valid data over the compared area.", code="no_data")
        cfg = PipelineConfig(detection=DetectionConfig(method="learned_siamese", model_id=model_id, band_map={"red": 1, "green": 2, "blue": 3}))
        async with _GATE:
            result = await asyncio.to_thread(run_pipeline, paths[0], paths[1], tmp_path / "work", cfg)

    card = get_card(model_id)
    records = sorted(result.features, key=lambda r: -r.area_m2)[:MAX_FEATURES]
    features = [{
        "type": "Feature", "id": r.index, "geometry": mapping(r.geometry),
        "properties": {"id": r.index, "point": [round(r.point_lon, 6), round(r.point_lat, 6)], "area_m2": round(r.area_m2, 1), "score": None if r.confidence is None else round(r.confidence, 3),
                       "magnitude": round(r.magnitude, 3), "severity": r.severity},
    } for r in records]
    areas = np.array([r.area_m2 for r in result.features], dtype=float)
    analysed = float(result.summary.get("analyzed_area_m2") or 0.0)
    buckets = [("< 500 m²", 0, 500), ("500 m² – 0.2 ha", 500, 2_000), ("0.2 – 1 ha", 2_000, 10_000), ("1 – 5 ha", 10_000, 50_000), ("> 5 ha", 50_000, float("inf"))]
    stats = {
        "analyzed_area_m2": round(analysed, 1),
        "changed_fraction": round(float(areas.sum()) / analysed, 5) if analysed else 0.0,
        "largest_m2": round(float(areas.max()), 1) if areas.size else 0.0,
        "median_m2": round(float(np.median(areas)), 1) if areas.size else 0.0,
        "size_classes": [{"label": lab, "count": int(((areas >= lo) & (areas < hi)).sum()), "area_m2": round(float(areas[(areas >= lo) & (areas < hi)].sum()), 1)} for lab, lo, hi in buckets],
    }
    return {
        "type": "FeatureCollection", "features": features,
        "metadata": {
            "stats": stats,
            "model_id": card.id if card else model_id, "model_name": card.name if card else None, "input_pixel_size_m": round(px_m, 2),
            "model_fed_at_m": card.trained_gsd_m if card else None, "masked_cloud_pct": round(100 * float(bad.mean()), 1), "feature_count": len(result.features), "returned": len(features),
            "total_changed_area_m2": round(sum(r.area_m2 for r in result.features), 1),
            "warnings": [w.get("message") for w in result.warnings if w.get("level") != "info"],
            "notes": list(result.detection.notes),
            "disclaimer": _disclaimer(card),
            "timings_s": {k: round(v, 1) for k, v in result.timings.items()},
        },
    }
