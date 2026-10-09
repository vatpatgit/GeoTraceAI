"""Side-by-side comparison + ML change detection for two uploaded GeoTIFFs of the same area (no job / database records are created)."""
from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from pyproj import Transformer
from rasterio.warp import transform_bounds

from app.geo.errors import PairIncompatibleError
from app.geo.tiles import RasterStyle, render_bounds, transparent_tile
from app.ml.registry import get_card, learned_ready
from app.services.quick_changes import SENTINEL_MODEL_ID, detect_from_images

MAX_SIDE = 2048
AERIAL_MODEL_ID = "levir-cd-v1"  # trained on 0.5-2 m aerial imagery
HIRES_LIMIT_M = 5.0  # finer than this => the aerial-trained model; coarser => the Sentinel-2 fine-tune


def model_disclaimer(card) -> str | None:
    """Disclaimer for user-supplied imagery (not Sentinel-2 specific); None keeps the caller's default."""
    if card is None:
        return None
    base = "Model-inferred candidates to inspect, not confirmed change; clouds, haze, shadows and seasonal colour shifts can cause false detections."
    test = (card.metrics or {}).get("test")
    if card.trained_gsd_m < 5:
        f1 = f" (F1 {test['f1']:.2f} on {test['num_samples']} held-out {card.dataset} tiles)" if test else ""
        return f"The model was trained on 0.5-2 m aerial building-change imagery ({card.dataset}){f1}; results on other sensors, regions and seasons are not validated. {base}"
    return None


def grid_for(bbox: tuple[float, float, float, float], width: int) -> tuple[tuple[float, float, float, float], tuple[int, int], float]:
    """Web-Mercator bounds of a lon/lat box, the pixel size of an image of ``width`` px over it, and the ground metres per pixel."""
    if not (bbox[2] > bbox[0] and bbox[3] > bbox[1]):
        raise PairIncompatibleError("bbox must be [west, south, east, north] with positive extent.", code="bad_bbox")
    if bbox[0] < -180 or bbox[2] > 180 or bbox[1] <= -85 or bbox[3] >= 85:
        raise PairIncompatibleError("bbox is outside the valid WGS84 / Web-Mercator range.", code="bad_bbox")
    left, bottom, right, top = transform_bounds("EPSG:4326", "EPSG:3857", *bbox)
    width = max(64, min(MAX_SIDE, int(width)))
    height = max(64, min(MAX_SIDE, int(round(width * (top - bottom) / (right - left)))))
    mid_lat = (bbox[1] + bbox[3]) / 2
    px_m = max((right - left) / width, (top - bottom) / height) * math.cos(math.radians(mid_lat))
    return (left, bottom, right, top), (width, height), px_m


def render_asset(path: str, style: RasterStyle, bbox: tuple[float, float, float, float], width: int) -> tuple[bytes, tuple[int, int]]:
    bounds, size, _ = grid_for(bbox, width)
    png = render_bounds(path, bounds, size, style)
    return (png if png is not None else transparent_tile()), size


def choose_model(px_m: float, requested: str | None = None) -> tuple[str | None, str]:
    if requested:
        return requested, "chosen by the caller"
    if px_m <= HIRES_LIMIT_M and learned_ready(AERIAL_MODEL_ID):
        return AERIAL_MODEL_ID, f"{px_m:.1f} m/px is high resolution: using the model trained on 0.5-2 m aerial imagery"
    if learned_ready(SENTINEL_MODEL_ID):
        return SENTINEL_MODEL_ID, f"{px_m:.1f} m/px is medium resolution: using the model fine-tuned on Sentinel-2 (10 m) pairs"
    return None, "no trained model installed"


async def detect_between_assets(before: tuple[str, RasterStyle], after: tuple[str, RasterStyle], bbox: tuple[float, float, float, float], *,
                                width: int, model_id: str | None) -> dict[str, Any]:
    import anyio

    bounds, size, px_m = grid_for(bbox, width)
    model, reason = choose_model(px_m, model_id)

    def _render() -> list[bytes]:
        out = []
        for path, style in (before, after):
            png = render_bounds(path, bounds, size, style)
            out.append(png if png is not None else transparent_tile())
        return out

    pngs = await anyio.to_thread.run_sync(_render)
    bad = np.zeros((size[1], size[0]), dtype=bool)  # no cloud mask for user imagery: only no-data (transparent) pixels are excluded
    for p in pngs:
        bad |= np.asarray(Image.open(io.BytesIO(p)).convert("RGBA").resize(size))[..., 3] == 0
    result = await detect_from_images(pngs, bad, bounds=bounds, crs="EPSG:3857", px_m=px_m, model_id=model)
    result["metadata"]["model_choice_reason"] = reason
    result["metadata"]["source"] = "uploaded GeoTIFFs"
    card = get_card(model)
    result["metadata"]["disclaimer"] = model_disclaimer(card) or result["metadata"]["disclaimer"]
    if card is not None and card.trained_gsd_m < 5 and px_m > 4:
        result["metadata"]["warnings"].append("This model was trained on higher-resolution imagery than the images you supplied.")
    return result
