"""End-to-end baseline pipeline checks against synthetic scenes with exactly known changes."""
import numpy as np
import pytest
import rasterio
from pyproj import Geod, Transformer
from shapely.geometry import MultiPolygon, Polygon, box, shape
from shapely.geometry.polygon import LinearRing
from shapely.ops import transform

from app.geo.config import DetectionConfig, PipelineConfig, PostprocessConfig
from app.geo.errors import PairIncompatibleError
from app.geo.pipeline import run_pipeline
from app.geo.polygonize import clean_geometry, geodesic_area_m2
from app.geo.synthetic import ChangeSpec, make_synthetic_pair

GEOD = Geod(ellps="WGS84")
TO_WGS = Transformer.from_crs("EPSG:32633", "EPSG:4326", always_xy=True)


def truth_geom(synth, spec: ChangeSpec):
    """Ground-truth rectangle of a ChangeSpec in lon/lat."""
    t = synth.transform
    (r0, r1), (c0, c1) = spec.rows, spec.cols
    x0, y0 = t @ (c0, r0)
    x1, y1 = t @ (c1, r1)
    return transform(TO_WGS.transform, box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))


@pytest.fixture(scope="module")
def cva_result(synth, tmp_path_factory):
    cfg = PipelineConfig(detection=DetectionConfig(method="spectral_cva"))
    return run_pipeline(synth.before, synth.after, tmp_path_factory.mktemp("cva"), cfg)


def test_all_known_changes_found_and_noise_rejected(synth, cva_result):
    feats = cva_result.features
    assert len(feats) == len(synth.changes) == 4  # 25 isolated speckle pixels must not become features
    # every truth rectangle is matched by exactly one feature (centroid inside it)
    from shapely.geometry import Point
    for spec in synth.changes:
        tg = truth_geom(synth, spec)
        hits = [f for f in feats if tg.contains(Point(f.centroid_lon, f.centroid_lat))]
        assert len(hits) == 1, spec


def test_pixel_level_accuracy_against_truth(synth, cva_result):
    with rasterio.open(cva_result.mask_path) as ds:
        mask = ds.read(1) == 1
    truth = synth.truth_mask
    tp = (mask & truth).sum()
    precision = tp / max(mask.sum(), 1)
    recall = tp / truth.sum()
    iou = tp / ((mask | truth).sum())
    assert precision > 0.95 and recall > 0.95 and iou > 0.90, (precision, recall, iou)


def test_area_matches_independent_geodesic_area(synth, cva_result):
    for spec in synth.changes:
        expected = abs(GEOD.geometry_area_perimeter(truth_geom(synth, spec))[0])
        tg = truth_geom(synth, spec)
        feat = next(f for f in cva_result.features if tg.contains(Point_(f)))
        assert feat.area_m2 == pytest.approx(expected, rel=0.06), (spec.kind, feat.area_m2, expected)
    # and clearly in square metres: 60x80 px at 10 m ~ 480,000 m2 (not degrees, not km2)
    biggest = max(cva_result.features, key=lambda f: f.area_m2)
    assert 4.3e5 < biggest.area_m2 < 5.3e5


def Point_(f):
    from shapely.geometry import Point
    return Point(f.centroid_lon, f.centroid_lat)


def test_centroids_are_lonlat_and_accurate(synth, cva_result):
    for spec in synth.changes:
        tg = truth_geom(synth, spec)
        c = tg.centroid
        feat = next(f for f in cva_result.features if tg.contains(Point_(f)))
        # within ~1.5 px (15 m ~ 1.5e-4 deg)
        assert abs(feat.centroid_lon - c.x) < 2e-4 and abs(feat.centroid_lat - c.y) < 2e-4
        assert -180 <= feat.centroid_lon <= 180 and -90 <= feat.centroid_lat <= 90


def test_geometries_are_valid_wgs84_and_rfc7946_oriented(cva_result):
    for f in cva_result.features:
        g = f.geometry
        assert g.is_valid and isinstance(g, (Polygon, MultiPolygon))
        minx, miny, maxx, maxy = g.bounds
        assert 14.9 < minx < maxx < 15.2 and 40.4 < miny < maxy < 40.8  # lon/lat, not metres
        polys = g.geoms if isinstance(g, MultiPolygon) else [g]
        for p in polys:
            assert LinearRing(p.exterior.coords).is_ccw  # exterior counter-clockwise
            assert all(not LinearRing(r.coords).is_ccw for r in p.interiors)


def test_categories_and_provenance_semantics(synth, cva_result):
    by_kind = {}
    for spec in synth.changes:
        tg = truth_geom(synth, spec)
        f = next(f for f in cva_result.features if tg.contains(Point_(f)))
        by_kind.setdefault(spec.kind, set()).add((f.category, f.category_basis))
    assert by_kind["vegetation_loss"] == {("vegetation_decrease", "spectral_index")}
    assert by_kind["vegetation_gain"] == {("vegetation_increase", "spectral_index")}
    # soil -> built has a small dNDVI: honestly reported as an unclassified observed difference
    assert by_kind["built"] == {("unclassified_change", "observed_difference")}
    assert all(f.confidence is None for f in cva_result.features)  # no meaningful confidence for the baseline
    assert cva_result.detection.confidence_kind is None


def test_severity_follows_documented_area_bands(cva_result):
    for f in cva_result.features:
        if f.area_m2 >= 50_000:
            assert f.severity == "critical"
        elif f.area_m2 >= 10_000:
            assert f.severity in ("high", "critical")
        assert f.severity_reasons and "area" in f.severity_reasons[0]


def test_summary_is_consistent(cva_result):
    s = cva_result.summary
    assert s["feature_count"] == 4
    assert s["total_changed_area_m2"] == pytest.approx(sum(f.area_m2 for f in cva_result.features))
    assert s["analyzed_area_m2"] == pytest.approx(512 * 512 * 100, rel=0.01)
    assert 0.03 < s["changed_fraction"] < 0.08


def test_rgb_only_pair_works_without_ndvi(synth_rgb, tmp_path):
    res = run_pipeline(synth_rgb.before, synth_rgb.after, tmp_path, PipelineConfig(detection=DetectionConfig(method="spectral_cva")))
    assert len(res.features) == 4
    assert {f.category for f in res.features} == {"unclassified_change"}  # no NIR => no vegetation labelling


def test_ndvi_method_refuses_imagery_without_nir(synth_rgb, tmp_path):
    with pytest.raises(PairIncompatibleError) as err:
        run_pipeline(synth_rgb.before, synth_rgb.after, tmp_path, PipelineConfig(detection=DetectionConfig(method="ndvi_diff")))
    assert err.value.code == "ndvi_bands_missing"


def test_ndvi_method_on_four_band_pair(synth, tmp_path):
    res = run_pipeline(synth.before, synth.after, tmp_path, PipelineConfig(detection=DetectionConfig(method="ndvi_diff")))
    cats = sorted(f.category for f in res.features)
    # soil->built barely changes NDVI so it is (correctly) not an NDVI change: only the two vegetation changes remain
    assert cats == ["vegetation_decrease", "vegetation_increase"]


def test_no_change_scene_yields_no_features(tmp_path):
    quiet = make_synthetic_pair(tmp_path / "q", changes=(), speckle=0, seed=3)
    res = run_pipeline(quiet.before, quiet.after, tmp_path / "w")
    assert res.features == []
    assert any(w["code"] == "no_change_detected" for w in res.warnings)


def test_identical_images_do_not_crash(synth, tmp_path):
    res = run_pipeline(synth.before, synth.before, tmp_path)
    assert res.features == []


def test_auto_selects_baseline_for_10m_imagery_without_model(synth, tmp_path, monkeypatch):
    import app.ml.registry as reg
    monkeypatch.setattr(reg, "learned_ready", lambda model_id=None: False)
    res = run_pipeline(synth.before, synth.after, tmp_path)
    assert res.detection.method == "spectral_cva"
    assert "auto" in res.method_reason


def test_min_area_filter_is_configurable(synth, tmp_path):
    cfg = PipelineConfig(detection=DetectionConfig(method="spectral_cva"),
                         postprocess=PostprocessConfig(min_area_m2=100_000))
    res = run_pipeline(synth.before, synth.after, tmp_path, cfg)
    # only blocks >= 100,000 m2 survive: 60x80 (480k) and 50x50 (250k); 40x60 (240k) too; 20x30 (60k) is dropped
    assert len(res.features) == 3


def test_progress_and_cancellation(synth, tmp_path):
    from app.geo.pipeline import JobCancelled
    seen = []
    run_pipeline(synth.before, synth.after, tmp_path / "a", progress=lambda s, f, m: seen.append((s, f)))
    fr = [f for _, f in seen]
    assert fr == sorted(fr) and fr[0] == 0.0 and fr[-1] > 0.9
    assert {s for s, _ in seen} >= {"validating", "preprocessing", "detecting", "polygonizing"}
    with pytest.raises(JobCancelled):
        run_pipeline(synth.before, synth.after, tmp_path / "b", cancel_check=lambda: True)


def test_geographic_input_area_is_not_in_degrees(tmp_path):
    """A raster in EPSG:4326 must be analysed in a metric CRS: area in m2 independent of the input CRS."""
    from rasterio.transform import Affine
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from app.geo.writers import write_geotiff

    base = make_synthetic_pair(tmp_path / "b", name="utm")
    out = {}
    for role, src_path in (("before", base.before), ("after", base.after)):
        with rasterio.open(src_path) as src:
            t, w, h = calculate_default_transform(src.crs, "EPSG:4326", src.width, src.height, *src.bounds)
            data = np.zeros((src.count, h, w), src.dtypes[0])
            for i in range(1, src.count + 1):
                reproject(rasterio.band(src, i), data[i - 1], src_transform=src.transform, src_crs=src.crs,
                          dst_transform=t, dst_crs="EPSG:4326", resampling=Resampling.bilinear)
            out[role] = write_geotiff(tmp_path / f"{role}_geo.tif", data, crs="EPSG:4326", transform=t,
                                      descriptions=src.descriptions, build_overviews=False)
    res = run_pipeline(out["before"], out["after"], tmp_path / "w", PipelineConfig(detection=DetectionConfig(method="spectral_cva")))
    assert res.aligned.crs_epsg == 32633
    biggest = max(res.features, key=lambda f: f.area_m2)
    assert 4.0e5 < biggest.area_m2 < 5.6e5  # ~480,000 m2, definitely not 1e-4 (deg2) or 0.48 (km2)


def test_clean_geometry_repairs_bowtie():
    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)])
    assert not bowtie.is_valid
    fixed = clean_geometry(bowtie)
    assert fixed is not None and fixed.is_valid and fixed.area > 0


def test_geodesic_area_subtracts_holes():
    outer = [(10, 10), (10.01, 10), (10.01, 10.01), (10, 10.01)]
    hole = [(10.004, 10.004), (10.004, 10.006), (10.006, 10.006), (10.006, 10.004)]
    solid = geodesic_area_m2(Polygon(outer))
    donut = geodesic_area_m2(Polygon(outer, [hole]))
    assert solid == pytest.approx(0.01 * 111_000 * 0.01 * 109_500, rel=0.02)
    assert 0.03 < (solid - donut) / solid < 0.05
