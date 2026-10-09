"""Bi-temporal raster-pair compatibility validation.

Produces user-presentable issues. Errors block processing; warnings are surfaced and persisted but allow it.
Nothing is silently "fixed": every adaptation the pipeline will make (reprojection, resampling, cropping) is
reported here first.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from pyproj import CRS, Transformer
from shapely.geometry import Polygon, box
from shapely.ops import transform as shp_transform

from app.geo.config import PreprocessConfig
from app.geo.raster_io import RasterInfo, detect_band_roles, utm_crs_for_lonlat


@dataclass
class Issue:
    level: str  # error | warning | info
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PairValidation:
    ok: bool
    issues: list[Issue]
    analysis_crs_epsg: int | None
    analysis_crs_wkt: str | None
    overlap: dict[str, Any]
    resolution: dict[str, Any]
    bands: dict[str, Any]
    suggested_pixel_size_m: float | None

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["errors"] = [asdict(i) for i in self.errors]
        d["warnings"] = [asdict(i) for i in self.warnings]
        return d


def footprint_polygon(info: RasterInfo, dst_crs: CRS | str, *, densify: int = 21) -> Polygon:
    """Raster footprint as a polygon in ``dst_crs`` (edges densified so reprojection curvature is respected)."""
    from rasterio.transform import Affine

    t = Affine(*info.transform)
    pts: list[tuple[float, float]] = []
    w, h = info.width, info.height
    for i in range(densify + 1):
        f = i / densify
        pts.append(t @ (f * w, 0))
    for i in range(1, densify + 1):
        f = i / densify
        pts.append(t @ (w, f * h))
    for i in range(1, densify + 1):
        f = i / densify
        pts.append(t @ ((1 - f) * w, h))
    for i in range(1, densify):
        f = i / densify
        pts.append(t @ (0, (1 - f) * h))
    poly = Polygon(pts)
    tr = Transformer.from_crs(CRS.from_wkt(info.crs_wkt), CRS.from_user_input(dst_crs), always_xy=True)
    return shp_transform(tr.transform, poly)


def choose_analysis_crs(before: RasterInfo, after: RasterInfo) -> CRS:
    """Metric projected CRS for analysis: reuse the shared one if both inputs agree, else UTM at the overlap centre."""
    cb, ca = CRS.from_wkt(before.crs_wkt), CRS.from_wkt(after.crs_wkt)
    if cb == ca and cb.is_projected and _is_metre_crs(cb):
        return cb
    bb, ab = before.bounds_wgs84, after.bounds_wgs84
    minx, miny = max(bb[0], ab[0]), max(bb[1], ab[1])
    maxx, maxy = min(bb[2], ab[2]), min(bb[3], ab[3])
    if minx >= maxx or miny >= maxy:  # no overlap: centre of the union (the error is reported by the caller)
        minx, miny = min(bb[0], ab[0]), min(bb[1], ab[1])
        maxx, maxy = max(bb[2], ab[2]), max(bb[3], ab[3])
    return utm_crs_for_lonlat((minx + maxx) / 2.0, (miny + maxy) / 2.0)


def _is_metre_crs(crs: CRS) -> bool:
    try:
        return abs((crs.axis_info[0].unit_conversion_factor or 1.0) - 1.0) < 1e-9
    except (IndexError, AttributeError):
        return False


def _dtype_family(info: RasterInfo) -> str:
    return info.dtypes[0] if info.dtypes else "unknown"


def validate_pair(
    before: RasterInfo,
    after: RasterInfo,
    config: PreprocessConfig | None = None,
    *,
    before_valid_fraction: float | None = None,
    after_valid_fraction: float | None = None,
    band_map_override: dict[str, int] | None = None,
) -> PairValidation:
    cfg = config or PreprocessConfig()
    issues: list[Issue] = []

    analysis_crs = choose_analysis_crs(before, after)
    fb = footprint_polygon(before, analysis_crs)
    fa = footprint_polygon(after, analysis_crs)
    inter = fb.intersection(fa)
    area_b, area_a, area_i = fb.area, fa.area, inter.area
    frac_b = area_i / area_b if area_b else 0.0
    frac_a = area_i / area_a if area_a else 0.0
    min_frac = min(frac_b, frac_a)
    overlap = {
        "area_m2": area_i,
        "fraction_of_before": frac_b,
        "fraction_of_after": frac_a,
        "bounds_analysis_crs": list(inter.bounds) if not inter.is_empty else None,
    }
    if not inter.is_empty:
        tr = Transformer.from_crs(analysis_crs, "EPSG:4326", always_xy=True)
        overlap["bounds_wgs84"] = list(shp_transform(tr.transform, box(*inter.bounds)).bounds)

    if inter.is_empty or area_i <= 0:
        issues.append(Issue("error", "no_overlap", "The before and after rasters do not overlap geographically.",
                            {"before_bounds_wgs84": list(before.bounds_wgs84), "after_bounds_wgs84": list(after.bounds_wgs84)}))
    elif min_frac < cfg.min_overlap_fraction:
        issues.append(Issue("error", "insufficient_overlap",
                            f"Only {min_frac:.1%} of the smaller image overlaps the other (minimum {cfg.min_overlap_fraction:.0%}).",
                            overlap))
    elif min_frac < 0.90:
        issues.append(Issue("warning", "partial_overlap",
                            f"The images overlap partially; analysis is restricted to the common area "
                            f"({frac_b:.0%} of 'before', {frac_a:.0%} of 'after').", overlap))

    cb, ca = CRS.from_wkt(before.crs_wkt), CRS.from_wkt(after.crs_wkt)
    if cb != ca:
        issues.append(Issue("warning", "crs_mismatch",
                            f"Different coordinate systems ({before.crs_name} vs {after.crs_name}); both will be reprojected to "
                            f"{analysis_crs.name}.", {"before": before.crs_epsg, "after": after.crs_epsg}))
    elif cb.is_geographic or not _is_metre_crs(cb):
        issues.append(Issue("info", "reproject_to_metric",
                            f"Inputs use {before.crs_name}; they will be reprojected to {analysis_crs.name} so that areas and "
                            "pixel sizes are metric.", {}))

    gb, ga = before.gsd_m, after.gsd_m
    ratio = max(gb, ga) / max(min(gb, ga), 1e-9)
    suggested_ps = cfg.pixel_size_m or max(gb, ga)
    resolution = {"before_gsd_m": gb, "after_gsd_m": ga, "ratio": ratio, "target_pixel_size_m": suggested_ps}
    if ratio > 4.0:
        issues.append(Issue("warning", "resolution_mismatch_large",
                            f"Ground resolutions differ by {ratio:.1f}x ({gb:.2f} m vs {ga:.2f} m). The finer image will be "
                            "down-sampled; detections will be unreliable at the finer scale.", resolution))
    elif ratio > 1.25:
        issues.append(Issue("warning", "resolution_mismatch",
                            f"Ground resolutions differ ({gb:.2f} m vs {ga:.2f} m); both are resampled to {suggested_ps:.2f} m.",
                            resolution))
    if before.is_rotated or after.is_rotated:
        issues.append(Issue("warning", "rotated_transform",
                            "A raster has a rotated/skewed geotransform; it will be resampled onto a north-up grid.", {}))

    # Bands
    rb = detect_band_roles(before.band_descriptions, before.count)
    ra = detect_band_roles(after.band_descriptions, after.count)
    mb = dict(band_map_override) if band_map_override else rb["band_map"]
    ma = dict(band_map_override) if band_map_override else ra["band_map"]
    optical = ("blue", "green", "red", "nir", "red_edge", "swir1", "swir2", "gray")
    common = [r for r in optical if r in mb and r in ma]
    bands = {
        "before": {"band_map": mb, "source": "override" if band_map_override else rb["source"], "count": before.count},
        "after": {"band_map": ma, "source": "override" if band_map_override else ra["source"], "count": after.count},
        "common_roles": common,
        "needs_confirmation": (not band_map_override) and (rb["needs_confirmation"] or ra["needs_confirmation"]),
        "notes": list(dict.fromkeys(rb["notes"] + ra["notes"])),
    }
    if not common:
        issues.append(Issue("error", "no_common_bands",
                            "The two rasters have no spectral bands in common (check band count and band descriptions).",
                            {"before_bands": before.count, "after_bands": after.count}))
    else:
        if before.count != after.count:
            issues.append(Issue("warning", "band_count_mismatch",
                                f"Band counts differ ({before.count} vs {after.count}); only the common bands "
                                f"{common} are compared.", {}))
        if bands["needs_confirmation"]:
            issues.append(Issue("warning", "band_roles_assumed",
                                "Band roles were assumed from the band count, not read from metadata: " + " ".join(bands["notes"]),
                                {"band_map": mb}))
    if _dtype_family(before) != _dtype_family(after):
        issues.append(Issue("warning", "dtype_mismatch",
                            f"Different pixel types ({_dtype_family(before)} vs {_dtype_family(after)}); a relative radiometric "
                            "normalisation is applied, absolute values are not comparable.", {}))

    for label, frac in (("before", before_valid_fraction), ("after", after_valid_fraction)):
        if frac is None:
            continue
        if frac < 0.05:
            issues.append(Issue("error", "mostly_nodata", f"The {label} image is {1 - frac:.0%} NoData/masked.", {"valid_fraction": frac}))
        elif frac < 0.5:
            issues.append(Issue("warning", "high_nodata", f"The {label} image is {1 - frac:.0%} NoData/masked.", {"valid_fraction": frac}))

    ok = not any(i.level == "error" for i in issues)
    return PairValidation(
        ok=ok,
        issues=issues,
        analysis_crs_epsg=analysis_crs.to_epsg(),
        analysis_crs_wkt=analysis_crs.to_wkt(),
        overlap=overlap,
        resolution=resolution,
        bands=bands,
        suggested_pixel_size_m=suggested_ps,
    )
