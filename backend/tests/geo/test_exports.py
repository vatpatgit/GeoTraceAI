"""Exports must reopen with independent parsers and preserve geometry + attributes."""
import json
import sqlite3
from datetime import datetime, timezone

import geopandas as gpd
import pyogrio
import pytest
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.polygon import LinearRing

from app.geo.exports import FEATURE_FIELDS, feature_collection, records_to_rows, write_geojson, write_geopackage
from app.geo.pipeline import run_pipeline
from app.geo.polygonize import geodesic_area_m2

BEFORE = datetime(2024, 1, 10, tzinfo=timezone.utc)
AFTER = datetime(2024, 6, 20, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def rows(synth, tmp_path_factory):
    res = run_pipeline(synth.before, synth.after, tmp_path_factory.mktemp("exp"))
    return records_to_rows(res.features, analysis_id="an-1", before_date=BEFORE, after_date=AFTER, method=res.detection.method,
                           magnitude_kind=res.detection.magnitude_kind, is_demo=True,
                           before_source="synthetic:before", after_source="synthetic:after")


def test_geojson_is_valid_rfc7946_and_roundtrips(rows, tmp_path):
    path = write_geojson(tmp_path / "out.geojson", rows, {"analysis_id": "an-1", "crs": "EPSG:4326"})
    fc = json.loads(path.read_text(encoding="utf-8"))
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == len(rows) == 4
    assert "crs" not in fc  # RFC 7946: WGS 84 is implied; the old 'crs' member is not allowed
    for feat, row in zip(fc["features"], rows):
        assert feat["type"] == "Feature" and feat["id"] == row["feature_id"]
        g = shape(feat["geometry"])
        assert g.is_valid and isinstance(g, (Polygon, MultiPolygon))
        for x, y in g.exterior.coords if isinstance(g, Polygon) else g.geoms[0].exterior.coords:
            assert -180 <= x <= 180 and -90 <= y <= 90
        ring = g.exterior if isinstance(g, Polygon) else g.geoms[0].exterior
        assert LinearRing(ring.coords).is_ccw
        p = feat["properties"]
        assert p["area_m2"] == pytest.approx(row["area_m2"]) and p["area_m2"] == pytest.approx(geodesic_area_m2(g), rel=1e-4)
        assert p["before_date"].startswith("2024-01-10") and p["after_date"].startswith("2024-06-20")
        assert p["severity"] in ("low", "medium", "high", "critical")
        assert p["is_demo"] is True and p["analysis_id"] == "an-1"
        assert set(FEATURE_FIELDS) <= set(p) | {"model_id"}
    json.dumps(fc, allow_nan=False)  # no NaN/Infinity (invalid JSON)


def test_geojson_empty_result_is_valid(tmp_path):
    path = write_geojson(tmp_path / "e.geojson", [], {"analysis_id": "x"})
    fc = json.loads(path.read_text())
    assert fc == {"type": "FeatureCollection", "features": [], "metadata": {"analysis_id": "x"}}


def test_geopackage_reopens_with_geometry_attributes_and_crs(rows, tmp_path):
    gpkg = write_geopackage(tmp_path / "out.gpkg", rows, analysis={"analysis_id": "an-1", "method": "spectral_cva", "config": {"k": 4}},
                            imagery=[{"role": "before", "source": "synthetic"}, {"role": "after", "source": "synthetic"}])
    layers = {name for name, _ in pyogrio.list_layers(gpkg)}
    assert {"change_features", "analysis_metadata", "source_imagery"} <= layers

    info = pyogrio.read_info(gpkg, layer="change_features")
    assert info["crs"] == "EPSG:4326"
    assert info["features"] == 4 and "MultiPolygon" in info["geometry_type"]

    gdf = gpd.read_file(gpkg, layer="change_features")
    assert gdf.crs.to_epsg() == 4326
    assert gdf.geometry.is_valid.all()
    by_id = {r["feature_id"]: r for r in rows}
    for _, rec in gdf.iterrows():
        src = by_id[rec["feature_id"]]
        assert rec["area_m2"] == pytest.approx(src["area_m2"])
        assert rec["category"] == src["category"]
        assert rec.geometry.symmetric_difference(src["geometry"]).area < 1e-12  # same geometry (Polygon promoted to Multi)
        assert str(rec["before_date"]).startswith("2024-01-10")

    meta = gpd.read_file(gpkg, layer="analysis_metadata")
    assert dict(zip(meta["key"], meta["value"]))["method"] == "spectral_cva"


def test_geopackage_is_structurally_valid_sqlite(rows, tmp_path):
    gpkg = write_geopackage(tmp_path / "s.gpkg", rows, analysis={"analysis_id": "a"})
    con = sqlite3.connect(gpkg)
    try:
        assert con.execute("PRAGMA application_id").fetchone()[0] == 0x47504B47  # 'GPKG'
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        srs = {r[0] for r in con.execute("SELECT srs_id FROM gpkg_spatial_ref_sys")}
        assert 4326 in srs
        gc = con.execute("SELECT table_name, geometry_type_name, srs_id FROM gpkg_geometry_columns").fetchall()
        assert ("change_features", "MULTIPOLYGON", 4326) in gc
        assert con.execute("SELECT COUNT(*) FROM change_features").fetchone()[0] == 4
        # spatial index (rtree) present for fast GIS loading
        assert con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'rtree_change_features%'").fetchone()[0] >= 1
    finally:
        con.close()


def test_geopackage_empty_result(tmp_path):
    gpkg = write_geopackage(tmp_path / "empty.gpkg", [], analysis={"analysis_id": "a"})
    assert pyogrio.read_info(gpkg, layer="change_features")["features"] == 0
    assert pyogrio.read_info(gpkg, layer="change_features")["crs"] == "EPSG:4326"


def test_selected_subset_export_contains_only_selection(rows):
    subset = rows[:2]
    fc = feature_collection(subset)
    assert [f["id"] for f in fc["features"]] == [r["feature_id"] for r in subset]
