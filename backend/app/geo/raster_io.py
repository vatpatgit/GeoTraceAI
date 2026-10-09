"""Raster inspection: content sniffing, metadata extraction and band-role detection."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import rasterio.enums
from pyproj import CRS, Geod, Transformer
from rasterio.errors import RasterioIOError
from rasterio.warp import transform_bounds

from app.geo.errors import RasterValidationError

# Classic TIFF, BigTIFF in both byte orders. Extension alone is never trusted.
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")
_GEOD = Geod(ellps="WGS84")

# Recognised optical roles. SCL / mask roles are auxiliary (never fed to change detectors as spectral bands).
OPTICAL_ROLES = ("blue", "green", "red", "red_edge", "nir", "swir1", "swir2")
AUX_ROLES = ("scl", "cloud_mask", "data_mask", "alpha")

_BAND_NAME_PATTERNS: list[tuple[str, str]] = [
    (r"^(b0?2|blue)$", "blue"),
    (r"^(b0?3|green)$", "green"),
    (r"^(b0?4|red)$", "red"),
    (r"^(b0?5|b0?6|b0?7|red_?edge\d?|rededge\d?)$", "red_edge"),
    (r"^(b0?8|b8a|nir\d?|near_?infrared)$", "nir"),
    (r"^(b11|swir1?)$", "swir1"),
    (r"^(b12|swir2)$", "swir2"),
    (r"^(scl|scene_?classification)$", "scl"),
    (r"^(cloud_?mask|clm|cloud|cld)$", "cloud_mask"),
    (r"^(datamask|data_?mask|valid_?mask)$", "data_mask"),
    (r"^(alpha)$", "alpha"),
]


@dataclass
class RasterInfo:
    path: str
    driver: str
    width: int
    height: int
    count: int
    dtypes: list[str]
    crs_wkt: str | None
    crs_epsg: int | None
    crs_name: str | None
    is_geographic: bool
    bounds: tuple[float, float, float, float]  # left, bottom, right, top in native CRS
    bounds_wgs84: tuple[float, float, float, float]  # minx, miny, maxx, maxy
    transform: tuple[float, float, float, float, float, float]  # affine a,b,c,d,e,f
    pixel_size: tuple[float, float]  # native CRS units (x, y) magnitudes
    pixel_size_m: tuple[float, float]  # approximate ground size in metres at the centre
    nodata: float | None
    band_descriptions: list[str | None]
    has_alpha: bool
    has_dataset_mask: bool
    is_rotated: bool
    block_shape: tuple[int, int]
    overview_levels: list[int]
    tags: dict[str, str] = field(default_factory=dict)
    size_bytes: int = 0
    megapixels: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # JSON friendliness
        for key in ("bounds", "bounds_wgs84", "transform", "pixel_size", "pixel_size_m", "block_shape"):
            d[key] = list(d[key])
        return d

    @property
    def gsd_m(self) -> float:
        """Nominal ground sample distance in metres (mean of x/y)."""
        return float(sum(self.pixel_size_m) / 2.0)


def sniff_tiff(path: str | Path) -> None:
    """Raise unless the file starts with a TIFF/BigTIFF signature."""
    p = Path(path)
    try:
        with p.open("rb") as fh:
            head = fh.read(4)
    except OSError as exc:  # pragma: no cover - filesystem failure
        raise RasterValidationError(f"Cannot read file: {exc}", code="unreadable_file") from exc
    if head not in _TIFF_MAGIC:
        raise RasterValidationError(
            "File content is not a TIFF/GeoTIFF (signature mismatch); the extension alone is not accepted.",
            code="not_a_tiff",
        )


def _pixel_size_m(crs: CRS | None, transform: rasterio.Affine, width: int, height: int, geographic: bool) -> tuple[float, float]:
    px, py = abs(transform.a), abs(transform.e)
    if crs is None:
        return (px, py)
    if not geographic:
        try:
            factor = crs.axis_info[0].unit_conversion_factor or 1.0
        except (IndexError, AttributeError):  # pragma: no cover
            factor = 1.0
        return (px * factor, py * factor)
    # Geographic: measure on the ellipsoid at the raster centre.
    cx = transform.c + transform.a * width / 2.0
    cy = transform.f + transform.e * height / 2.0
    _, _, dx = _GEOD.inv(cx, cy, cx + px, cy)
    _, _, dy = _GEOD.inv(cx, cy, cx, cy + py)
    return (abs(dx), abs(dy))


def detect_band_roles(descriptions: list[str | None], count: int, tags: dict[str, str] | None = None) -> dict[str, Any]:
    """Infer which band index (1-based) plays which spectral role.

    Returns {"band_map": {role: index}, "source": "descriptions|count_heuristic|unknown",
             "needs_confirmation": bool, "notes": [...]}.
    Only descriptions are trusted automatically; a bare 3-band image is assumed RGB (flagged), a bare 4-band
    image is ambiguous (RGB+NIR vs BGR+NIR) and always needs confirmation.
    """
    band_map: dict[str, int] = {}
    notes: list[str] = []
    for idx, desc in enumerate(descriptions, start=1):
        if not desc:
            continue
        key = re.sub(r"[\s\-]+", "_", desc.strip().lower())
        for pattern, role in _BAND_NAME_PATTERNS:
            if re.match(pattern, key):
                band_map.setdefault(role, idx)
                break
    if len(band_map) >= 2 and any(r in band_map for r in ("red", "green", "blue", "nir")):
        return {"band_map": band_map, "source": "descriptions", "needs_confirmation": False, "notes": notes}

    if count >= 3:
        band_map = {"red": 1, "green": 2, "blue": 3}
        notes.append("No band descriptions found; assuming bands 1-3 are red, green, blue.")
        needs = True
        if count == 4:
            notes.append("A 4th band is present and its role (usually NIR) is unknown; confirm the band mapping.")
        elif count > 4:
            notes.append(f"{count} bands present without descriptions; only bands 1-3 are used as RGB unless you confirm a mapping.")
        return {"band_map": band_map, "source": "count_heuristic", "needs_confirmation": needs, "notes": notes}
    if count == 1:
        notes.append("Single-band raster: only an intensity-difference method is possible (no colour or NDVI).")
        return {"band_map": {"gray": 1}, "source": "count_heuristic", "needs_confirmation": False, "notes": notes}
    notes.append(f"{count}-band raster with no descriptions; band roles unknown.")
    return {"band_map": {}, "source": "unknown", "needs_confirmation": True, "notes": notes}


def inspect_raster(path: str | Path, *, max_pixels: int | None = None) -> RasterInfo:
    """Open a raster and extract everything needed to validate it. Never reads full pixel data."""
    p = Path(path)
    if not p.is_file():
        raise RasterValidationError(f"File not found: {p.name}", code="missing_file")
    sniff_tiff(p)
    try:
        with rasterio.open(p) as src:
            if src.driver != "GTiff":
                raise RasterValidationError(f"Unsupported raster driver {src.driver!r}; expected GTiff.", code="bad_driver")
            if src.width < 2 or src.height < 2:
                raise RasterValidationError("Raster is smaller than 2x2 pixels.", code="too_small")
            if src.count < 1:
                raise RasterValidationError("Raster has no bands.", code="no_bands")
            if max_pixels and src.width * src.height > max_pixels:
                raise RasterValidationError(
                    f"Raster has {src.width * src.height / 1e6:.1f} MP which exceeds the configured limit of {max_pixels / 1e6:.0f} MP.",
                    code="too_large",
                    details={"megapixels": src.width * src.height / 1e6, "limit_megapixels": max_pixels / 1e6},
                )
            if src.crs is None:
                raise RasterValidationError(
                    "Raster has no coordinate reference system. GeoTrace needs georeferenced GeoTIFFs.",
                    code="no_crs",
                )
            transform = src.transform
            if transform.is_identity:
                raise RasterValidationError(
                    "Raster has an identity geotransform (no georeferencing).",
                    code="no_geotransform",
                )
            crs = CRS.from_user_input(src.crs.to_wkt())
            geographic = bool(crs.is_geographic)
            is_rotated = abs(transform.b) > 1e-12 or abs(transform.d) > 1e-12
            bounds = tuple(src.bounds)
            try:
                bounds_wgs84 = tuple(transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21))
            except Exception as exc:  # pragma: no cover - degenerate projection
                raise RasterValidationError(f"Cannot compute WGS84 footprint: {exc}", code="bad_footprint") from exc
            if not all(math.isfinite(v) for v in bounds_wgs84):
                raise RasterValidationError("Raster footprint is not representable in WGS84.", code="bad_footprint")
            descs = list(src.descriptions)
            alpha = any(ci.name == "alpha" for ci in src.colorinterp)
            masks = src.mask_flag_enums
            has_dataset_mask = any(
                rasterio.enums.MaskFlags.per_dataset in flags or rasterio.enums.MaskFlags.alpha in flags for flags in masks
            )
            epsg = None
            try:
                epsg = crs.to_epsg()
            except Exception:  # pragma: no cover
                epsg = None
            info = RasterInfo(
                path=str(p),
                driver=src.driver,
                width=src.width,
                height=src.height,
                count=src.count,
                dtypes=list(src.dtypes),
                crs_wkt=src.crs.to_wkt(),
                crs_epsg=epsg,
                crs_name=crs.name,
                is_geographic=geographic,
                bounds=bounds,  # type: ignore[arg-type]
                bounds_wgs84=bounds_wgs84,  # type: ignore[arg-type]
                transform=(transform.a, transform.b, transform.c, transform.d, transform.e, transform.f),
                pixel_size=(abs(transform.a), abs(transform.e)),
                pixel_size_m=_pixel_size_m(crs, transform, src.width, src.height, geographic),
                nodata=src.nodata,
                band_descriptions=descs,
                has_alpha=alpha,
                has_dataset_mask=has_dataset_mask,
                is_rotated=is_rotated,
                block_shape=tuple(src.block_shapes[0]) if src.block_shapes else (0, 0),  # type: ignore[arg-type]
                overview_levels=list(src.overviews(1)) if src.count else [],
                tags=dict(src.tags()),
                size_bytes=p.stat().st_size,
                megapixels=src.width * src.height / 1e6,
            )
            return info
    except RasterValidationError:
        raise
    except RasterioIOError as exc:
        raise RasterValidationError(f"Raster could not be opened by GDAL: {exc}", code="gdal_open_failed") from exc


def valid_data_fraction(path: str | Path, *, sample_pixels: int = 1_000_000) -> float:
    """Estimate the fraction of valid (non-NoData / alpha-masked) pixels from a decimated read."""
    with rasterio.open(path) as src:
        scale = max(1.0, math.sqrt(src.width * src.height / sample_pixels))
        out_shape = (max(1, int(src.height / scale)), max(1, int(src.width / scale)))
        mask = src.dataset_mask(out_shape=out_shape)
    return float(np.count_nonzero(mask) / mask.size)


def geodesic_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    _, _, d = _GEOD.inv(lon1, lat1, lon2, lat2)
    return float(d)


def utm_crs_for_lonlat(lon: float, lat: float) -> CRS:
    """Pick the analysis CRS (UTM zone, or UPS in the polar caps) for a location."""
    if lat >= 84.0:
        return CRS.from_epsg(32661)
    if lat <= -80.0:
        return CRS.from_epsg(32761)
    zone = int((lon + 180.0) // 6.0) + 1
    zone = min(max(zone, 1), 60)
    return CRS.from_epsg((32600 if lat >= 0 else 32700) + zone)


def lonlat_transformer(src_crs: CRS | str, dst_crs: CRS | str = "EPSG:4326") -> Transformer:
    return Transformer.from_crs(src_crs, dst_crs, always_xy=True)
