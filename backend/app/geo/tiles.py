"""On-the-fly Web-Mercator raster rendering (XYZ tiles and single-image previews).

Used by both the MapLibre 2D map and the Cesium globe so both show the *same* pixels over the *same* extent.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Sequence

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds
from rasterio.transform import from_bounds as transform_from_bounds

WORLD = 20037508.342789244
TILE = 256


def tile_bounds_3857(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    n = 2 ** z
    size = 2 * WORLD / n
    minx = -WORLD + x * size
    maxy = WORLD - y * size
    return (minx, maxy - size, minx + size, maxy)


def lonlat_to_3857(lon: float, lat: float) -> tuple[float, float]:
    x = lon * WORLD / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) * WORLD / math.pi
    return x, y


@lru_cache(maxsize=1)
def transparent_tile(size: int = TILE) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (size, size), (0, 0, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


@dataclass
class RasterStyle:
    mode: str = "rgb"  # rgb | gray | score | mask | delta
    bands: Sequence[int] = (1, 2, 3)
    stretch: Sequence[tuple[float, float]] | None = None  # per-band (lo, hi); None => derive from dtype
    mask_path: str | None = None  # optional validity raster (>0 = valid) applied as alpha
    score_nodata: float = -1.0
    opacity: float = 1.0
    extra: dict = field(default_factory=dict)


# key colours of a perceptual "inferno-like" ramp (score 0..1)
_RAMP = np.array([[0.0, 0, 0, 4], [0.25, 87, 16, 110], [0.5, 188, 55, 84], [0.75, 249, 142, 9], [1.0, 252, 255, 164]], dtype=np.float32)


def _ramp(values: np.ndarray) -> np.ndarray:
    v = np.clip(values, 0.0, 1.0)
    out = np.empty(v.shape + (3,), dtype=np.float32)
    for c in range(3):
        out[..., c] = np.interp(v, _RAMP[:, 0], _RAMP[:, c + 1])
    return out


_NDVI_RAMP = np.array([[-0.2, 139, 69, 19], [0.0, 190, 160, 110], [0.2, 230, 217, 168], [0.4, 166, 205, 96], [0.6, 102, 170, 70], [0.9, 11, 102, 35]], dtype=np.float32)


def _ndvi_color(ndvi: np.ndarray) -> np.ndarray:
    out = np.empty(ndvi.shape + (3,), dtype=np.float32)
    for c in range(3):
        out[..., c] = np.interp(ndvi, _NDVI_RAMP[:, 0], _NDVI_RAMP[:, c + 1])
    return out


def _default_stretch(dtype: str, n: int) -> list[tuple[float, float]]:
    if dtype == "uint8":
        return [(0.0, 255.0)] * n
    if dtype == "uint16":
        return [(0.0, 3000.0)] * n  # typical reflectance*10000 display range; overridden by stored stretch when known
    return [(0.0, 0.3)] * n


def _read(src_path: str, bounds: tuple[float, float, float, float], size: tuple[int, int], indexes: Sequence[int],
          resampling: Resampling):
    """Warp ``indexes`` onto the exact tile grid (EPSG:3857 ``bounds``); returns (data, valid) or None if disjoint."""
    w, h = size
    with rasterio.open(src_path) as src:
        sb = transform_bounds(src.crs, "EPSG:3857", *src.bounds, densify_pts=21)
        if sb[0] >= bounds[2] or sb[2] <= bounds[0] or sb[1] >= bounds[3] or sb[3] <= bounds[1]:
            return None
        has_alpha = any(ci.name == "alpha" for ci in src.colorinterp)
        with WarpedVRT(src, crs="EPSG:3857", transform=transform_from_bounds(*bounds, w, h), width=w, height=h,
                       resampling=resampling, add_alpha=not has_alpha) as vrt:
            data = vrt.read(list(indexes))
            if has_alpha:
                valid = vrt.read(src.count) > 0
            else:
                valid = vrt.read(vrt.count) > 0  # the alpha band added by the VRT (footprint + NoData aware)
    return data, valid


def render_bounds(path: str, bounds: tuple[float, float, float, float], size: tuple[int, int], style: RasterStyle) -> bytes | None:
    """Render ``path`` over ``bounds`` (EPSG:3857) as an RGBA PNG; None => fully transparent."""
    w, h = size
    if style.mode == "ndvi":
        got = _read(path, bounds, size, list(style.bands[:2]), Resampling.bilinear)  # (red, nir)
    elif style.mode in ("mask", "score", "gray"):
        res = Resampling.nearest if style.mode == "mask" else Resampling.bilinear
        got = _read(path, bounds, size, [style.bands[0]], res)
    else:
        got = _read(path, bounds, size, style.bands, Resampling.bilinear)
    if got is None:
        return None
    data, valid = got
    if style.mask_path:
        mg = _read(style.mask_path, bounds, size, [1], Resampling.nearest)
        if mg is None:
            return None
        valid &= (mg[0][0] > 0) & mg[1]

    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    if style.mode == "rgb":
        stretch = list(style.stretch) if style.stretch else _default_stretch("uint8", len(style.bands))
        rgb = np.empty((h, w, 3), dtype=np.float32)
        for c in range(3):
            lo, hi = stretch[c] if c < len(stretch) else stretch[-1]
            rgb[..., c] = np.clip((data[c].astype(np.float32) - lo) / max(hi - lo, 1e-9), 0, 1) * 255
        rgba[..., :3] = rgb.astype(np.uint8)
        rgba[..., 3] = (valid * 255 * style.opacity).astype(np.uint8)
    elif style.mode == "gray":
        lo, hi = (style.stretch[0] if style.stretch else (0.0, 255.0))
        g = (np.clip((data[0].astype(np.float32) - lo) / max(hi - lo, 1e-9), 0, 1) * 255).astype(np.uint8)
        rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = g
        rgba[..., 3] = (valid * 255 * style.opacity).astype(np.uint8)
    elif style.mode == "score":
        s = data[0].astype(np.float32)
        ok = valid & (s > style.score_nodata + 1e-6)
        col = _ramp(s)
        rgba[..., :3] = col.astype(np.uint8)
        alpha = np.clip(s * 1.6, 0, 1) * 0.9 * style.opacity
        rgba[..., 3] = np.where(ok, alpha * 255, 0).astype(np.uint8)
    elif style.mode == "mask":
        on = valid & (data[0] == 1)
        rgba[..., 0], rgba[..., 1], rgba[..., 2] = 239, 68, 68
        rgba[..., 3] = np.where(on, 150 * style.opacity, 0).astype(np.uint8)
    elif style.mode == "ndvi":
        red, nir = data[0].astype(np.float32), data[1].astype(np.float32)
        den = nir + red
        nd = np.where(np.abs(den) > 1e-6, (nir - red) / np.where(np.abs(den) > 1e-6, den, 1.0), 0.0)
        rgba[..., :3] = _ndvi_color(nd).astype(np.uint8)
        rgba[..., 3] = (valid * 255 * style.opacity).astype(np.uint8)
    elif style.mode == "delta":  # signed dNDVI: red = loss, green = gain
        d = data[0].astype(np.float32)
        ok = valid & np.isfinite(d)
        mag = np.clip(np.abs(d) / 0.6, 0, 1)
        rgba[..., 0] = np.where(d < 0, 230, 40)
        rgba[..., 1] = np.where(d < 0, 60, 200)
        rgba[..., 2] = 60
        rgba[..., 3] = np.where(ok, mag * 220 * style.opacity, 0).astype(np.uint8)
    else:
        raise ValueError(f"unknown style mode {style.mode}")
    if not rgba[..., 3].any():
        return None
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG", compress_level=3)
    return buf.getvalue()


def render_tile(path: str, z: int, x: int, y: int, style: RasterStyle) -> bytes:
    png = render_bounds(path, tile_bounds_3857(z, x, y), (TILE, TILE), style)
    return png if png is not None else transparent_tile()


def render_preview(path: str, style: RasterStyle, max_dim: int = 1024) -> tuple[bytes, list[list[float]]] | None:
    """Single Web-Mercator image of the whole raster + its four lon/lat corners (TL, TR, BR, BL) for MapLibre image sources."""
    with rasterio.open(path) as src:
        left, bottom, right, top = transform_bounds(src.crs, "EPSG:3857", *src.bounds, densify_pts=21)
    w_m, h_m = right - left, top - bottom
    scale = max_dim / max(w_m, h_m)
    size = (max(2, int(round(w_m * scale))), max(2, int(round(h_m * scale))))
    png = render_bounds(path, (left, bottom, right, top), size, style)
    if png is None:
        return None
    lon_l, lat_b, lon_r, lat_t = transform_bounds("EPSG:3857", "EPSG:4326", left, bottom, right, top)
    corners = [[lon_l, lat_t], [lon_r, lat_t], [lon_r, lat_b], [lon_l, lat_b]]
    return png, corners
