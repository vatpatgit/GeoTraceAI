"""GeoJSON (RFC 7946) and GeoPackage writers for change features.

Both writers take the same neutral row format so exports from freshly computed results (tests, CLI) and from
database rows are identical.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.geometry.base import BaseGeometry

from app.geo.polygonize import COORD_DECIMALS, orient_rfc7946

# Canonical attribute order / names shared by GeoJSON and GeoPackage.
FEATURE_FIELDS = (
    "feature_id", "analysis_id", "category", "category_basis", "area_m2", "perimeter_m",
    "centroid_lon", "centroid_lat", "magnitude", "magnitude_kind", "confidence", "confidence_kind",
    "severity", "severity_basis", "before_date", "after_date", "detection_method", "model_id",
    "review_status", "distance_to_boundary_m", "before_source", "after_source", "is_demo",
)


def _json_value(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if hasattr(v, "item"):  # numpy scalar
        return v.item()
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return None
    return v


def _precise(geom: BaseGeometry) -> BaseGeometry:
    return shapely.set_precision(geom, 10 ** -COORD_DECIMALS)


def feature_collection(rows: Iterable[dict[str, Any]], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build an RFC 7946 FeatureCollection (WGS 84, lon/lat, counter-clockwise exterior rings)."""
    features = []
    for row in rows:
        geom: BaseGeometry = row["geometry"]
        geom = orient_rfc7946(_precise(geom)) if isinstance(geom, (Polygon, MultiPolygon)) else geom
        props = {k: _json_value(row.get(k)) for k in FEATURE_FIELDS if k in row}
        for k, v in row.items():
            if k not in FEATURE_FIELDS and k != "geometry" and k != "id":
                props[k] = _json_value(v)
        feat: dict[str, Any] = {"type": "Feature", "id": str(row.get("id") or row.get("feature_id")),
                                "geometry": mapping(geom), "properties": props}
        features.append(feat)
    fc: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if metadata:
        fc["metadata"] = {k: _json_value(v) for k, v in metadata.items()}
    return fc


def write_geojson(path: str | Path, rows: Sequence[dict[str, Any]], metadata: dict[str, Any] | None = None) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(feature_collection(rows, metadata), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return p


def _to_multi(geom: BaseGeometry) -> BaseGeometry:
    return MultiPolygon([geom]) if isinstance(geom, Polygon) else geom


def write_geopackage(
    path: str | Path,
    rows: Sequence[dict[str, Any]],
    *,
    analysis: dict[str, Any],
    imagery: Sequence[dict[str, Any]] = (),
    layer: str = "change_features",
) -> Path:
    """Write a GeoPackage with the spatial ``change_features`` layer (EPSG:4326, MultiPolygon) and two
    attribute-only tables: ``analysis_metadata`` (key/value) and ``source_imagery``."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        p.unlink()

    records = []
    for row in rows:
        rec = {k: row.get(k) for k in FEATURE_FIELDS}
        rec["geometry"] = _to_multi(orient_rfc7946(row["geometry"]))
        records.append(rec)
    if records:
        gdf = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
    else:
        gdf = gpd.GeoDataFrame({k: pd.Series(dtype="object") for k in FEATURE_FIELDS}, geometry=gpd.GeoSeries([], crs="EPSG:4326"), crs="EPSG:4326")
    for col in ("before_date", "after_date"):
        gdf[col] = pd.to_datetime(gdf[col], errors="coerce", utc=True).dt.tz_localize(None)
    for col in ("area_m2", "perimeter_m", "centroid_lon", "centroid_lat", "magnitude", "confidence", "distance_to_boundary_m"):
        gdf[col] = pd.to_numeric(gdf[col], errors="coerce").astype("float64")
    if "is_demo" in gdf:
        gdf["is_demo"] = gdf["is_demo"].fillna(False).astype(bool)

    gdf.to_file(p, layer=layer, driver="GPKG", engine="pyogrio", geometry_type="MultiPolygon")

    meta_df = pd.DataFrame([{"key": str(k), "value": json.dumps(_json_value(v), ensure_ascii=False, default=str)
                             if isinstance(v, (dict, list)) else str(_json_value(v))} for k, v in analysis.items()])
    _append_table(p, meta_df, "analysis_metadata")
    img_df = pd.DataFrame([{k: (json.dumps(v, default=str) if isinstance(v, (dict, list)) else _json_value(v)) for k, v in item.items()}
                           for item in imagery]) if imagery else pd.DataFrame({"role": pd.Series(dtype="object")})
    _append_table(p, img_df, "source_imagery")
    return p


def _append_table(path: Path, df: pd.DataFrame, name: str) -> None:
    import pyogrio

    pyogrio.write_dataframe(df, path, layer=name, driver="GPKG", append=True)


def records_to_rows(records, *, analysis_id: str, before_date, after_date, method: str, model_id: str | None = None,
                    magnitude_kind: str = "", confidence_kind: str | None = None, is_demo: bool = False,
                    before_source: str | None = None, after_source: str | None = None,
                    feature_ids: Sequence[str] | None = None, review_status: str = "unreviewed") -> list[dict[str, Any]]:
    """Convert pipeline ``ChangeFeatureRecord``s to the neutral export row format."""
    rows = []
    for i, r in enumerate(records):
        fid = feature_ids[i] if feature_ids else f"{analysis_id}-{r.index:05d}"
        rows.append({
            "id": fid, "feature_id": fid, "analysis_id": analysis_id, "geometry": r.geometry,
            "category": r.category, "category_basis": r.category_basis, "area_m2": r.area_m2, "perimeter_m": r.perimeter_m,
            "centroid_lon": r.centroid_lon, "centroid_lat": r.centroid_lat, "magnitude": r.magnitude,
            "magnitude_kind": magnitude_kind, "confidence": r.confidence, "confidence_kind": confidence_kind,
            "severity": r.severity, "severity_basis": "heuristic_priority_not_a_probability",
            "before_date": before_date, "after_date": after_date, "detection_method": method, "model_id": model_id,
            "review_status": review_status, "distance_to_boundary_m": r.distance_to_boundary_m,
            "before_source": before_source, "after_source": after_source, "is_demo": is_demo,
        })
    return rows
