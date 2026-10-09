"""Alignment: warp a before/after pair onto one common metric grid, window by window.

Large rasters are never fully loaded: ``WarpedVRT`` + block-wise reads keep memory bounded by one block.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window
from shapely.geometry import shape, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform

from app.geo.config import PreprocessConfig
from app.geo.errors import PairIncompatibleError
from app.geo.raster_io import RasterInfo, detect_band_roles, inspect_raster
from app.geo.registration import estimate_shift
from app.geo.validation import PairValidation, choose_analysis_crs, footprint_polygon, validate_pair
from app.geo.writers import write_geotiff, default_profile

OPTICAL_ORDER = ("blue", "green", "red", "red_edge", "nir", "swir1", "swir2", "gray")
BLOCK_ROWS = 512
ProgressFn = Callable[[float, str], None]


@dataclass
class AlignedPair:
    before_path: str
    after_path: str
    valid_mask_path: str
    crs_wkt: str
    crs_epsg: int | None
    transform: tuple[float, float, float, float, float, float]
    width: int
    height: int
    pixel_size_m: float
    roles: list[str]  # band order of both aligned rasters (1-based index = position + 1)
    valid_fraction: float
    cloud_masked_fraction: float
    registration: dict[str, Any]
    warnings: list[dict[str, Any]] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)
    resampling: dict[str, str] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)

    @property
    def affine(self) -> Affine:
        return Affine(*self.transform)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["transform"] = list(self.transform)
        return d


def _resampling_for(src_gsd_m: float, dst_gsd_m: float) -> Resampling:
    # Down-sampling by >=1.5x needs area averaging (bilinear aliases); otherwise bilinear.
    return Resampling.average if dst_gsd_m / max(src_gsd_m, 1e-9) >= 1.5 else Resampling.bilinear


def _band_selection(info: RasterInfo, band_map: dict[str, int] | None) -> dict[str, int]:
    detected = detect_band_roles(info.band_descriptions, info.count)
    return dict(band_map) if band_map else dict(detected["band_map"])


def _aux_band(info: RasterInfo, role: str) -> int | None:
    detected = detect_band_roles(info.band_descriptions, info.count)
    return detected["band_map"].get(role) if detected["source"] == "descriptions" else None


def _make_vrt(src: rasterio.DatasetReader, info: RasterInfo, crs: CRS, transform: Affine, width: int, height: int,
              resampling: Resampling) -> tuple[WarpedVRT, bool]:
    """Return (vrt, alpha_added). If the source already has an alpha band we use it instead of adding one."""
    kwargs: dict[str, Any] = dict(crs=crs.to_wkt(), transform=transform, width=width, height=height, resampling=resampling)
    if info.nodata is not None:
        kwargs["src_nodata"] = info.nodata
    if info.has_alpha:
        return WarpedVRT(src, **kwargs), False
    kwargs["add_alpha"] = True
    return WarpedVRT(src, **kwargs), True


def _grid_for(overlap_geom: BaseGeometry, pixel_size: float) -> tuple[Affine, int, int]:
    minx, miny, maxx, maxy = overlap_geom.bounds
    # Snap to the pixel lattice so repeated analyses of the same area share an aligned grid.
    left = math.floor(minx / pixel_size) * pixel_size
    top = math.ceil(maxy / pixel_size) * pixel_size
    right = math.ceil(maxx / pixel_size) * pixel_size
    bottom = math.floor(miny / pixel_size) * pixel_size
    width = max(1, int(round((right - left) / pixel_size)))
    height = max(1, int(round((top - bottom) / pixel_size)))
    return Affine(pixel_size, 0, left, 0, -pixel_size, top), width, height


def align_pair(
    before_path: str | Path,
    after_path: str | Path,
    out_dir: str | Path,
    config: PreprocessConfig | None = None,
    *,
    aoi_wgs84: dict | BaseGeometry | None = None,
    band_map: dict[str, int] | None = None,
    progress: ProgressFn | None = None,
) -> AlignedPair:
    """Validate and warp both rasters to a shared grid. Raises ``PairIncompatibleError`` on blocking problems."""
    cfg = config or PreprocessConfig()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = progress or (lambda f, m: None)

    info_b, info_a = inspect_raster(before_path), inspect_raster(after_path)
    validation: PairValidation = validate_pair(info_b, info_a, cfg, band_map_override=band_map)
    if not validation.ok:
        raise PairIncompatibleError(
            "; ".join(i.message for i in validation.errors),
            details={"issues": [asdict(i) for i in validation.issues]},
        )
    warnings = [asdict(i) for i in validation.issues if i.level in ("warning", "info")]

    crs = choose_analysis_crs(info_b, info_a)
    inter = footprint_polygon(info_b, crs).intersection(footprint_polygon(info_a, crs))
    if aoi_wgs84 is not None:
        aoi = shape(aoi_wgs84) if isinstance(aoi_wgs84, dict) else aoi_wgs84
        to_crs = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        aoi_crs = shp_transform(to_crs.transform, aoi)
        clipped = inter.intersection(aoi_crs)
        if clipped.is_empty:
            raise PairIncompatibleError("The area of interest does not intersect the common footprint of the two images.",
                                        code="aoi_outside_imagery")
        inter = clipped
        warnings.append({"level": "info", "code": "aoi_clip", "message": "Analysis restricted to the area of interest.", "details": {}})
    else:
        aoi_crs = None

    pixel_size = float(cfg.pixel_size_m or validation.suggested_pixel_size_m)
    transform, width, height = _grid_for(inter, pixel_size)
    if width * height > cfg.max_pixels:
        side_km = math.sqrt(cfg.max_pixels) * pixel_size / 1000.0
        raise PairIncompatibleError(
            f"The common area would be {width * height / 1e6:.0f} MP at {pixel_size:g} m; the limit is "
            f"{cfg.max_pixels / 1e6:.0f} MP. Reduce the area of interest to about {side_km:.0f} km x {side_km:.0f} km.",
            code="too_many_pixels",
            details={"width": width, "height": height, "limit": cfg.max_pixels},
        )

    mb = _band_selection(info_b, band_map)
    ma = _band_selection(info_a, band_map)
    roles = [r for r in OPTICAL_ORDER if r in mb and r in ma]
    if not roles:
        raise PairIncompatibleError("No spectral bands in common between the two rasters.", code="no_common_bands")

    scl_b, scl_a = _aux_band(info_b, "scl"), _aux_band(info_a, "scl")
    dm_b, dm_a = _aux_band(info_b, "data_mask"), _aux_band(info_a, "data_mask")
    res_b = _resampling_for(info_b.gsd_m, pixel_size)
    res_a = _resampling_for(info_a.gsd_m, pixel_size)

    before_out = out / "before_aligned.tif"
    after_out = out / "after_aligned.tif"
    mask_out = out / "valid_mask.tif"

    prof_b = default_profile(count=len(roles), dtype=info_b.dtypes[0], width=width, height=height, crs=crs.to_wkt(), transform=transform)
    prof_a = default_profile(count=len(roles), dtype=info_a.dtypes[0], width=width, height=height, crs=crs.to_wkt(), transform=transform)
    prof_m = default_profile(count=1, dtype="uint8", width=width, height=height, crs=crs.to_wkt(), transform=transform, nodata=None)

    valid_px = 0
    cloud_px = 0
    total_px = 0
    n_blocks = math.ceil(height / BLOCK_ROWS)
    report(0.02, "Aligning rasters")

    with rasterio.open(before_path) as sb, rasterio.open(after_path) as sa:
        vb, add_b = _make_vrt(sb, info_b, crs, transform, width, height, res_b)
        va, add_a = _make_vrt(sa, info_a, crs, transform, width, height, res_a)
        vb_scl = va_scl = vb_dm = va_dm = None
        if scl_b:
            vb_scl, _ = _make_vrt(sb, info_b, crs, transform, width, height, Resampling.nearest)
        if scl_a:
            va_scl, _ = _make_vrt(sa, info_a, crs, transform, width, height, Resampling.nearest)
        if dm_b:
            vb_dm, _ = _make_vrt(sb, info_b, crs, transform, width, height, Resampling.nearest)
        if dm_a:
            va_dm, _ = _make_vrt(sa, info_a, crs, transform, width, height, Resampling.nearest)
        try:
            with rasterio.open(before_out, "w", **prof_b) as db, rasterio.open(after_out, "w", **prof_a) as da, \
                    rasterio.open(mask_out, "w", **prof_m) as dm:
                for i, role in enumerate(roles, start=1):
                    db.set_band_description(i, role)
                    da.set_band_description(i, role)
                for bi in range(n_blocks):
                    r0 = bi * BLOCK_ROWS
                    win = Window(0, r0, width, min(BLOCK_ROWS, height - r0))
                    data_b = vb.read([mb[r] for r in roles], window=win)
                    data_a = va.read([ma[r] for r in roles], window=win)
                    alpha_b = vb.read(vb.count, window=win) if add_b else vb.read(_alpha_index(info_b), window=win)
                    alpha_a = va.read(va.count, window=win) if add_a else va.read(_alpha_index(info_a), window=win)
                    valid = (alpha_b > 0) & (alpha_a > 0)
                    block_total = valid.size
                    cloud = np.zeros(valid.shape, dtype=bool)
                    if vb_scl is not None:
                        cloud |= np.isin(vb_scl.read(scl_b, window=win), cfg.cloud_scl_invalid)
                    if va_scl is not None:
                        cloud |= np.isin(va_scl.read(scl_a, window=win), cfg.cloud_scl_invalid)
                    in_aoi = np.ones(valid.shape, dtype=bool)
                    if aoi_crs is not None:
                        in_aoi = geometry_mask([mapping(aoi_crs)], out_shape=valid.shape,
                                               transform=rasterio.windows.transform(win, transform), invert=True)
                    footprint_valid = valid & in_aoi
                    # provider data-mask band (0 = no data): treated as invalid footprint, not as cloud
                    if vb_dm is not None:
                        footprint_valid &= vb_dm.read(dm_b, window=win) > 0
                    if va_dm is not None:
                        footprint_valid &= va_dm.read(dm_a, window=win) > 0
                    final = footprint_valid & ~cloud
                    data_b[:, ~final] = 0
                    data_a[:, ~final] = 0
                    db.write(data_b, window=win)
                    da.write(data_a, window=win)
                    dm.write(final.astype(np.uint8)[np.newaxis], window=win)
                    valid_px += int(final.sum())
                    cloud_px += int((cloud & footprint_valid).sum())
                    total_px += int(footprint_valid.sum()) if aoi_crs is not None else block_total
                    report(0.02 + 0.8 * (bi + 1) / n_blocks, "Aligning rasters")
        finally:
            for v in (vb, va, vb_scl, va_scl, vb_dm, va_dm):
                if v is not None:
                    v.close()

    # overviews for fast rendering
    for p in (before_out, after_out, mask_out):
        _build_overviews(p, Resampling.nearest if p == mask_out else Resampling.average)

    valid_fraction = valid_px / max(width * height, 1)
    if valid_px == 0:
        raise PairIncompatibleError("No valid pixels remain after alignment (all NoData / masked).", code="no_valid_pixels")
    if valid_fraction < 0.25:
        warnings.append({"level": "warning", "code": "small_valid_area",
                         "message": f"Only {valid_fraction:.0%} of the aligned grid is valid after masking.", "details": {}})
    if scl_b or scl_a:
        warnings.append({"level": "info", "code": "cloud_masked",
                         "message": f"{cloud_px / max(total_px, 1):.1%} of the footprint was masked using the Sentinel-2 scene classification.",
                         "details": {"scl_invalid_classes": list(cfg.cloud_scl_invalid)}})
    else:
        warnings.append({"level": "info", "code": "cloud_not_assessed",
                         "message": "No cloud/quality mask is available for these inputs; cloud, shadow and haze contamination was NOT assessed.",
                         "details": {}})

    report(0.88, "Checking registration")
    registration = _check_registration(before_out, after_out, mask_out, roles, cfg)
    if registration.get("reliable") and registration["magnitude_px"] > cfg.registration_warn_px:
        warnings.append({
            "level": "warning", "code": "possible_misregistration",
            "message": f"The images appear offset by about {registration['magnitude_px']:.1f} px "
                       f"({registration['magnitude_px'] * pixel_size:.0f} m). Residual misregistration produces false change along edges.",
            "details": registration,
        })
    elif not registration.get("reliable"):
        warnings.append({"level": "info", "code": "registration_unverified",
                         "message": "Registration could not be verified (insufficient texture/correlation).", "details": registration})

    report(1.0, "Alignment complete")
    return AlignedPair(
        before_path=str(before_out), after_path=str(after_out), valid_mask_path=str(mask_out),
        crs_wkt=crs.to_wkt(), crs_epsg=crs.to_epsg(), transform=(transform.a, transform.b, transform.c, transform.d, transform.e, transform.f),
        width=width, height=height, pixel_size_m=pixel_size, roles=roles,
        valid_fraction=valid_fraction, cloud_masked_fraction=cloud_px / max(total_px, 1),
        registration=registration, warnings=warnings, validation=validation.to_dict(),
        resampling={"before": res_b.name, "after": res_a.name},
        source={"before_crs": info_b.crs_epsg, "after_crs": info_a.crs_epsg, "before_gsd_m": info_b.gsd_m, "after_gsd_m": info_a.gsd_m},
    )


def _alpha_index(info: RasterInfo) -> int:
    # Source alpha is, by GDAL convention, the last band when present.
    return info.count


def _build_overviews(path: Path, resampling: Resampling) -> None:
    with rasterio.open(path, "r+") as ds:
        if min(ds.width, ds.height) < 512:
            return
        levels, f = [], 2
        while min(ds.width, ds.height) // f >= 128 and len(levels) < 6:
            levels.append(f)
            f *= 2
        if levels:
            ds.build_overviews(levels, resampling)


def _gray_for_registration(path: str, roles: list[str], out_shape: tuple[int, int]) -> np.ndarray:
    pick = [i + 1 for i, r in enumerate(roles) if r in ("green", "red", "gray", "nir")] or [1]
    with rasterio.open(path) as ds:
        arr = ds.read(pick, out_shape=(len(pick), *out_shape), resampling=Resampling.average).astype(np.float32)
    return arr.mean(axis=0)


def _check_registration(before_path, after_path, mask_path, roles, cfg: PreprocessConfig) -> dict[str, Any]:
    with rasterio.open(before_path) as ds:
        h, w = ds.height, ds.width
    step = max(1, int(math.ceil(max(h, w) / 1024)))
    shape = (max(8, h // step), max(8, w // step))
    if min(shape) < 32:
        return {"reliable": False, "reason": "image too small", "dx_px": 0.0, "dy_px": 0.0, "magnitude_px": 0.0, "peak": 0.0}
    a = _gray_for_registration(str(before_path), roles, shape)
    b = _gray_for_registration(str(after_path), roles, shape)
    with rasterio.open(mask_path) as ds:
        v = ds.read(1, out_shape=shape, resampling=Resampling.nearest) > 0
    est = estimate_shift(a, b, v, max_dim=1024)
    scale = h / shape[0]
    dx, dy = est.dx_px * scale, est.dy_px * scale
    return {
        "reliable": bool(est.peak >= cfg.registration_min_peak),
        "dx_px": float(dx), "dy_px": float(dy), "magnitude_px": float(math.hypot(dx, dy)),
        "peak": est.peak, "method": "phase_correlation_on_edges",
    }
