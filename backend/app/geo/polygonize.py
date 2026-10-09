"""Mask -> georeferenced polygons with geodesic area, centroid and zonal statistics."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import rasterio
import shapely
from pyproj import CRS, Geod, Transformer
from rasterio.features import shapes
from scipy import ndimage
from shapely.geometry import MultiPolygon, Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import transform as shp_transform
from shapely.strtree import STRtree

from app.geo.config import PostprocessConfig, SeverityConfig
from app.geo.detect import DetectionOutput
from app.geo.postprocess import EIGHT
from app.geo.preprocess import AlignedPair
from app.geo.severity import severity_for

GEOD = Geod(ellps="WGS84")
COORD_DECIMALS = 7  # ~1 cm


@dataclass
class ChangeFeatureRecord:
    index: int
    geometry: BaseGeometry  # EPSG:4326, RFC 7946 ring orientation
    area_m2: float
    perimeter_m: float
    centroid_lon: float
    centroid_lat: float
    point_lon: float  # guaranteed inside the polygon (for map pins / fly-to)
    point_lat: float
    pixel_count: int
    magnitude: float  # mean change score of the component, 0..1
    magnitude_max: float
    confidence: float | None
    delta_ndvi: float | None
    category: str
    category_basis: str
    severity: str
    severity_reasons: list[str]
    distance_to_boundary_m: float | None = None
    nearest_boundary_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return tuple(self.geometry.bounds)  # type: ignore[return-value]


def geodesic_area_m2(geom: BaseGeometry) -> float:
    """Ellipsoidal area (WGS84) of a lon/lat Polygon/MultiPolygon in square metres, holes subtracted."""
    if geom.is_empty:
        return 0.0
    if isinstance(geom, MultiPolygon):
        return float(sum(geodesic_area_m2(p) for p in geom.geoms))
    if not isinstance(geom, Polygon):
        return 0.0
    ext_x, ext_y = geom.exterior.xy
    area = abs(GEOD.polygon_area_perimeter(ext_x, ext_y)[0])
    for ring in geom.interiors:
        rx, ry = ring.xy
        area -= abs(GEOD.polygon_area_perimeter(rx, ry)[0])
    return float(max(area, 0.0))


def geodesic_perimeter_m(geom: BaseGeometry) -> float:
    if isinstance(geom, MultiPolygon):
        return float(sum(geodesic_perimeter_m(p) for p in geom.geoms))
    if not isinstance(geom, Polygon) or geom.is_empty:
        return 0.0
    total = abs(GEOD.polygon_area_perimeter(*geom.exterior.xy)[1])
    for ring in geom.interiors:
        total += abs(GEOD.polygon_area_perimeter(*ring.xy)[1])
    return float(total)


def _polys_only(geom: BaseGeometry) -> BaseGeometry | None:
    if geom.is_empty:
        return None
    if isinstance(geom, (Polygon, MultiPolygon)):
        return geom
    polys = [g for g in getattr(geom, "geoms", []) if isinstance(g, (Polygon, MultiPolygon))]
    if not polys:
        return None
    flat: list[Polygon] = []
    for g in polys:
        flat.extend(g.geoms if isinstance(g, MultiPolygon) else [g])
    return MultiPolygon(flat) if len(flat) > 1 else flat[0]


def clean_geometry(geom: BaseGeometry) -> BaseGeometry | None:
    """Repair invalid geometry and keep only polygonal parts."""
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    return _polys_only(geom)


def orient_rfc7946(geom: BaseGeometry) -> BaseGeometry:
    if isinstance(geom, MultiPolygon):
        return MultiPolygon([orient(p, sign=1.0) for p in geom.geoms])
    return orient(geom, sign=1.0)


def round_geometry(geom: BaseGeometry, decimals: int = COORD_DECIMALS) -> BaseGeometry:
    return shapely.set_precision(geom, 10 ** -decimals) if decimals is not None else geom


def grid_area_m2(aligned: AlignedPair) -> float:
    """Geodesic area of the aligned grid rectangle."""
    t = aligned.affine
    ring = [t @ (0, 0), t @ (aligned.width, 0), t @ (aligned.width, aligned.height), t @ (0, aligned.height)]
    tr = Transformer.from_crs(CRS.from_wkt(aligned.crs_wkt), "EPSG:4326", always_xy=True)
    return geodesic_area_m2(shp_transform(tr.transform, Polygon(ring)))


def polygonize_changes(
    mask: np.ndarray,
    score: np.ndarray,
    aligned: AlignedPair,
    detection: DetectionOutput,
    post_cfg: PostprocessConfig,
    sev_cfg: SeverityConfig,
    *,
    boundaries: Sequence[tuple[str, str, BaseGeometry]] | None = None,
) -> tuple[list[ChangeFeatureRecord], dict[str, Any]]:
    """Convert the cleaned mask into feature records (sorted by area, largest first)."""
    labels, n = ndimage.label(mask, structure=EIGHT)
    stats: dict[str, Any] = {"components": int(n), "truncated": False, "dropped_components": 0}
    if n == 0:
        return [], stats

    idx = np.arange(1, n + 1)
    pix = np.bincount(labels.ravel(), minlength=n + 1)[1:]
    if n > post_cfg.max_features:
        keep_ids = idx[np.argsort(pix)[::-1][: post_cfg.max_features]]
        keep = np.zeros(n + 1, dtype=bool)
        keep[keep_ids] = True
        labels = np.where(keep[labels], labels, 0)
        stats.update(truncated=True, dropped_components=int(n - post_cfg.max_features))
        idx = keep_ids
    score_f = np.clip(score, 0.0, 1.0)
    mean_score = dict(zip(idx.tolist(), ndimage.mean(score_f, labels, idx)))
    max_score = dict(zip(idx.tolist(), ndimage.maximum(score_f, labels, idx)))
    mean_dndvi: dict[int, float] = {}
    if detection.delta_ndvi_path:
        with rasterio.open(detection.delta_ndvi_path) as ds:
            d = np.nan_to_num(ds.read(1), nan=0.0)
        mean_dndvi = dict(zip(idx.tolist(), ndimage.mean(d, labels, idx)))

    crs = CRS.from_wkt(aligned.crs_wkt)
    to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    tol = post_cfg.simplify_tolerance_px * aligned.pixel_size_m

    polys_by_label: dict[int, list[Polygon]] = {}
    for geom, val in shapes(labels.astype(np.int32), mask=labels > 0, transform=aligned.affine, connectivity=8):
        polys_by_label.setdefault(int(val), []).append(shape(geom))

    bnd = []
    if boundaries:
        tr_b = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        bnd = [(bid, name, shp_transform(tr_b.transform, g)) for bid, name, g in boundaries]
        tree = STRtree([g for _, _, g in bnd])

    records: list[ChangeFeatureRecord] = []
    for lab, polys in polys_by_label.items():
        g_proj = polys[0] if len(polys) == 1 else shapely.union_all(polys)
        if tol > 0:
            g_proj = g_proj.simplify(tol, preserve_topology=True)
        g_proj = clean_geometry(g_proj)
        if g_proj is None:
            continue
        g_wgs = clean_geometry(shp_transform(to_wgs.transform, g_proj))
        if g_wgs is None:
            continue
        g_wgs = orient_rfc7946(g_wgs)
        area = geodesic_area_m2(g_wgs)
        if area <= 0:
            continue
        c = g_proj.centroid
        clon, clat = to_wgs.transform(c.x, c.y)
        p = g_proj.representative_point()
        plon, plat = to_wgs.transform(p.x, p.y)
        magnitude = float(mean_score[lab])
        dist = nearest = None
        if bnd:
            j = tree.nearest(g_proj)
            dist = float(g_proj.distance(bnd[j][2]))
            nearest = bnd[j][0]
        dn = mean_dndvi.get(lab)
        category, basis = detection.default_category, detection.category_basis
        if dn is not None and detection.method == "spectral_cva":
            label_thr = float(detection.details.get("ndvi_label_threshold", 0.20))
            if dn <= -label_thr:
                category, basis = "vegetation_decrease", "spectral_index"
            elif dn >= label_thr:
                category, basis = "vegetation_increase", "spectral_index"
        elif dn is not None and detection.method == "ndvi_diff":
            category = "vegetation_decrease" if dn < 0 else "vegetation_increase"
        sev, reasons = severity_for(area, magnitude, dist, sev_cfg)
        records.append(ChangeFeatureRecord(
            index=0, geometry=g_wgs, area_m2=area, perimeter_m=geodesic_perimeter_m(g_wgs),
            centroid_lon=float(clon), centroid_lat=float(clat), point_lon=float(plon), point_lat=float(plat),
            pixel_count=int(pix[lab - 1]) if lab - 1 < len(pix) else 0,
            magnitude=magnitude, magnitude_max=float(max_score[lab]),
            confidence=magnitude if detection.confidence_kind else None,
            delta_ndvi=float(dn) if dn is not None else None,
            category=category, category_basis=basis, severity=sev, severity_reasons=reasons,
            distance_to_boundary_m=dist, nearest_boundary_id=nearest,
        ))
    records.sort(key=lambda r: r.area_m2, reverse=True)
    for i, r in enumerate(records, start=1):
        r.index = i
    stats["features"] = len(records)
    return records, stats
