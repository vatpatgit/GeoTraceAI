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
    """
    Calculate approximate area in square kilometers for a GeoJSON geometry in EPSG:4326.
    Uses a simple approximation for unprojected coordinates, suitable for estimation.
    """
    geom = shape(geojson_dict)
    # 1 square degree is approximately 12321 square kilometers at the equator
    # For a more accurate area, projection should be used.
    # We use a rough estimate here for simplicity.
    area_sq_degrees = geom.area
    # Average latitude approximation factor could be applied, but this is a rough estimate
    return area_sq_degrees * 12321.0
