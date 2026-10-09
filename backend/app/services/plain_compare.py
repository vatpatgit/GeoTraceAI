"""ML change detection between two ordinary (non-georeferenced) images: PNG, JPEG, WebP, BMP or GIF.

Such files carry no coordinates, so nothing here pretends to know where on Earth they are: the pair is assumed to show the same area, framed
identically. Results are returned in IMAGE PIXEL coordinates (x right, y down, original image size). Areas in m2 are only reported when the
caller states the ground size of a pixel. Internally the images are written as temporary metric rasters and run through the same pipeline and
model as every other comparison, then mapped back to pixels.
"""
from __future__ import annotations

import asyncio
import io
from typing import Any

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform

from app.geo.errors import PairIncompatibleError
from app.ml.registry import get_card
from app.services.quick_changes import detect_from_images
from app.services.upload_compare import choose_model, model_disclaimer

PLAIN_FORMATS = {"PNG", "JPEG", "MPO", "WEBP", "BMP", "GIF"}
MAX_PIXELS = 40_000_000
MAX_SIDE = 2048
ASPECT_TOLERANCE = 0.03
_TO_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)


def decode_image(data: bytes, which: str) -> np.ndarray:
    """Decode by CONTENT (not file name). Returns RGBA uint8 (H, W, 4)."""
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format
        probe.verify()
        im = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise PairIncompatibleError(f"The {which} file is not a readable image (PNG, JPEG, WebP, BMP or GIF).", code="not_an_image") from exc
    if fmt not in PLAIN_FORMATS:
        raise PairIncompatibleError(f"The {which} image format '{fmt}' is not supported here (use PNG, JPEG, WebP, BMP or GIF, or a GeoTIFF).", code="unsupported_format")
    if im.width * im.height > MAX_PIXELS:
        raise PairIncompatibleError(f"The {which} image is {im.width}x{im.height} px; the limit is {MAX_PIXELS // 1_000_000} megapixels.", code="image_too_large")
    im = ImageOps.exif_transpose(im).convert("RGBA")
    return np.asarray(im)


def _png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr, "RGBA").save(buf, "PNG")
    return buf.getvalue()


def _fraction_buckets(areas_px: np.ndarray, total_px: float) -> list[dict[str, Any]]:
    edges = [("< 0.05% of image", 0.0, 0.0005), ("0.05 – 0.2%", 0.0005, 0.002), ("0.2 – 1%", 0.002, 0.01), ("1 – 5%", 0.01, 0.05), ("> 5%", 0.05, float("inf"))]
    fr = areas_px / total_px
    return [{"label": lab, "count": int(((fr >= lo) & (fr < hi)).sum()), "area_m2": 0.0} for lab, lo, hi in edges]


async def detect_plain(before_bytes: bytes, after_bytes: bytes, *, pixel_size_m: float | None, model_id: str | None) -> dict[str, Any]:
    a = decode_image(before_bytes, "before")
    b = decode_image(after_bytes, "after")
    warnings: list[str] = []
    (h0, w0), (h1, w1) = a.shape[:2], b.shape[:2]
    if abs((w0 / h0) / (w1 / h1) - 1) > ASPECT_TOLERANCE:
        raise PairIncompatibleError(f"The images have different proportions ({w0}x{h0} vs {w1}x{h1}). They must show the same area framed the same way.", code="size_mismatch")
    if (h0, w0) != (h1, w1):
        b = np.asarray(Image.fromarray(b, "RGBA").resize((w0, h0), Image.LANCZOS))
        warnings.append(f"The after image ({w1}x{h1}) was resized to match the before image ({w0}x{h0}).")
    scale = min(1.0, MAX_SIDE / max(h0, w0))
    if scale < 1.0:
        size = (max(64, int(round(w0 * scale))), max(64, int(round(h0 * scale))))
        a = np.asarray(Image.fromarray(a, "RGBA").resize(size, Image.LANCZOS))
        b = np.asarray(Image.fromarray(b, "RGBA").resize(size, Image.LANCZOS))
        warnings.append(f"Images larger than {MAX_SIDE}px were reduced for the model ({w0}x{h0} -> {size[0]}x{size[1]}); results are mapped back to full size.")
    H, W = a.shape[:2]
    scale_x, scale_y = W / w0, H / h0

    known = pixel_size_m is not None
    if known:
        px_eff = pixel_size_m / scale_x  # ground metres per processed pixel
        model, reason = choose_model(px_eff, model_id)
    else:
        model, reason = choose_model(2.0, model_id)  # no ground scale given: show the model the pixels as it was trained (1:1)
        card0 = get_card(model)
        px_eff = card0.trained_gsd_m if card0 else 2.0
        reason = "ground size of a pixel not provided: the image is shown to the model at its native pixel scale. " + reason
    bad = (a[..., 3] == 0) | (b[..., 3] == 0)
    bounds = (0.0, -H * px_eff, W * px_eff, 0.0)
    result = await detect_from_images([_png(a), _png(b)], bad, bounds=bounds, crs="EPSG:3857", px_m=px_eff, model_id=model)

    def to_pixels(x, y, z=None):
        X, Y = _TO_3857.transform(np.asarray(x), np.asarray(y))
        return (X / px_eff / scale_x, -Y / px_eff / scale_y)

    feats, areas = [], []
    for f in result["features"]:
        g = shp_transform(to_pixels, shape(f["geometry"]))
        if g.is_empty:
            continue
        areas.append(g.area)
        p = dict(f["properties"])
        p.pop("point", None)
        c = g.representative_point()
        p.update({"area_px": round(g.area, 1), "point": [round(c.x, 1), round(c.y, 1)]})
        if not known:
            p["area_m2"] = None
        feats.append({"type": "Feature", "id": f["id"], "geometry": mapping(g), "properties": p})
    areas_a = np.array(areas, dtype=float)
    total_px = float(w0 * h0)
    meta = result["metadata"]
    meta["disclaimer"] = model_disclaimer(get_card(model)) or meta["disclaimer"]
    meta.update({
        "source": "uploaded images (not georeferenced)", "image_size": [w0, h0], "pixel_size_known": known, "pixel_size_m": pixel_size_m,
        "model_choice_reason": reason, "feature_count": len(feats), "returned": len(feats), "warnings": list(meta.get("warnings", [])) + warnings,
        "total_changed_px": round(float(areas_a.sum()), 1) if areas_a.size else 0.0,
    })
    meta["stats"] = {
        "analyzed_area_m2": round(total_px * (pixel_size_m or 0) ** 2, 1) if known else 0.0,
        "changed_fraction": round(float(areas_a.sum()) / total_px, 5) if areas_a.size else 0.0,
        "largest_m2": round(float(areas_a.max()) * (pixel_size_m or 0) ** 2, 1) if (known and areas_a.size) else 0.0,
        "median_m2": 0.0,
        "size_classes": _fraction_buckets(areas_a, total_px),
    }
    if not known:
        meta["total_changed_area_m2"] = None
        meta["warnings"].append("No pixel size was given, so areas are shown as a share of the image, not in square metres.")
    return {"type": "FeatureCollection", "features": feats, "metadata": meta}
