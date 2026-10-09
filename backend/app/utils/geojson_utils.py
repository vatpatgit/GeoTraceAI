import json
from typing import Dict, Any, Tuple
from shapely.geometry import shape, Polygon
import geojson

def validate_geojson_polygon(geojson_dict: Dict[str, Any]) -> bool:
    """Validate if the provided GeoJSON represents a valid Polygon."""
    try:
        geom = shape(geojson_dict)
        return isinstance(geom, Polygon) and geom.is_valid
    except Exception:
        return False

def geojson_to_wkt(geojson_dict: Dict[str, Any]) -> str:
    """Convert a GeoJSON geometry dictionary to WKT format."""
    geom = shape(geojson_dict)
    return geom.wkt

def bbox_from_geojson(geojson_dict: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """Calculate the bounding box (min_lng, min_lat, max_lng, max_lat) from GeoJSON."""
    geom = shape(geojson_dict)
    return geom.bounds

def calculate_area_km2(geojson_dict: Dict[str, Any]) -> float:
    """Geodesic (WGS84 ellipsoid) area in square kilometres of a lon/lat GeoJSON polygon."""
    from app.geo.polygonize import geodesic_area_m2

    return geodesic_area_m2(shape(geojson_dict)) / 1e6
