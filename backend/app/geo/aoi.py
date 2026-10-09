"""Area-of-interest construction and validation (pure functions)."""
from __future__ import annotations

import math
from typing import Any

import shapely
from pyproj import Geod
from shapely.geometry import Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry

from app.geo.errors import GeoProcessingError
from app.geo.polygonize import geodesic_area_m2, orient_rfc7946

_GEOD = Geod(ellps="WGS84")
MIN_AOI_KM2 = 1e-4  # 100 m2


class AoiError(GeoProcessingError):
    code = "invalid_aoi"


def _check_lonlat(x: float, y: float) -> None:
    if not (-180.0 <= x <= 180.0 and -90.0 <= y <= 90.0):
        raise AoiError(f"Coordinate ({x}, {y}) is outside valid lon/lat range; coordinates must be WGS84 [lon, lat].")


def polygon_from_geojson(geom: dict[str, Any]) -> Polygon:
    if not isinstance(geom, dict) or geom.get("type") != "Polygon":
        raise AoiError("AOI geometry must be a GeoJSON Polygon.")
    try:
        g = shape(geom)
    except Exception as exc:
        raise AoiError(f"AOI geometry could not be parsed: {exc}") from exc
    if g.is_empty:
        raise AoiError("AOI polygon is empty.")
    for x, y in g.exterior.coords:
        _check_lonlat(x, y)
    if not g.is_valid:
        g = shapely.make_valid(g)
        polys = [p for p in getattr(g, "geoms", [g]) if isinstance(p, Polygon)]
        if not polys:
            raise AoiError("AOI polygon is invalid and could not be repaired.")
        g = max(polys, key=lambda p: p.area)
    return g


def bbox_polygon(bbox: list[float]) -> Polygon:
    minx, miny, maxx, maxy = bbox
    for x, y in ((minx, miny), (maxx, maxy)):
        _check_lonlat(x, y)
    if minx >= maxx or miny >= maxy:
        raise AoiError("bbox must be [min_lon, min_lat, max_lon, max_lat] with min < max.")
    return box(minx, miny, maxx, maxy)


def circle_polygon(lon: float, lat: float, radius_m: float, segments: int = 72) -> Polygon:
    _check_lonlat(lon, lat)
    if abs(lat) > 85:
        raise AoiError("Circular AOIs are not supported above 85 degrees latitude.")
    pts = [_GEOD.fwd(lon, lat, 360.0 * i / segments, radius_m)[:2] for i in range(segments)]
    return Polygon(pts + [pts[0]])


def finalize_aoi(poly: Polygon, *, max_km2: float) -> tuple[Polygon, float]:
    """Validate size/shape and return (RFC7946-oriented polygon, geodesic area in km2)."""
    minx, miny, maxx, maxy = poly.bounds
    if maxx - minx > 180:
        raise AoiError("AOIs crossing the antimeridian are not supported; split the area in two.")
    poly = orient_rfc7946(poly)
    km2 = geodesic_area_m2(poly) / 1e6
    if km2 < MIN_AOI_KM2:
        raise AoiError(f"AOI is too small ({km2 * 1e6:.0f} m2).")
    if km2 > max_km2:
        side = math.sqrt(max_km2)
        raise AoiError(f"AOI is {km2:,.0f} km2 which exceeds the limit of {max_km2:,.0f} km2 (about {side:.0f} km x {side:.0f} km).",
                       details={"area_km2": km2, "limit_km2": max_km2})
    return poly, km2


def geojson(geom: BaseGeometry) -> dict[str, Any]:
    return mapping(geom)
