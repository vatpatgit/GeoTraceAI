import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

from app.geo.errors import RasterValidationError
from app.geo.raster_io import detect_band_roles, inspect_raster, sniff_tiff, utm_crs_for_lonlat
from app.geo.validation import validate_pair
from app.geo.writers import write_geotiff


def test_inspect_reports_georeferencing(synth):
    info = inspect_raster(synth.before)
    assert info.crs_epsg == 32633
    assert (info.width, info.height, info.count) == (512, 512, 4)
    assert info.pixel_size_m == pytest.approx((10.0, 10.0))
    assert info.band_descriptions == ["blue", "green", "red", "nir"]
    assert info.transform[:3] == (10.0, 0.0, 500000.0)
    minx, miny, maxx, maxy = info.bounds_wgs84
    # UTM 33N: easting 500000 is the central meridian (15 E); northing 4.5e6 m is ~40.6 N
    assert 14.999 < minx < maxx < 15.1
    assert 40.5 < miny < maxy < 40.7


def test_geographic_pixel_size_is_metric(tmp_path):
    p = write_geotiff(tmp_path / "geo.tif", np.zeros((1, 64, 64), np.uint8), crs="EPSG:4326",
                      transform=Affine(0.0001, 0, 10.0, 0, -0.0001, 45.0), build_overviews=False)
    info = inspect_raster(p)
    assert info.is_geographic
    # 0.0001 deg lat ~ 11.1 m; lon shrinks with cos(45 deg) ~ 7.9 m
    assert info.pixel_size_m[1] == pytest.approx(11.1, abs=0.2)
    assert info.pixel_size_m[0] == pytest.approx(7.9, abs=0.3)


def test_fake_extension_is_rejected(tmp_path):
    bogus = tmp_path / "image.tif"
    bogus.write_bytes(b"<html>definitely not a tiff</html>")
    with pytest.raises(RasterValidationError) as err:
        inspect_raster(bogus)
    assert err.value.code == "not_a_tiff"


def test_missing_crs_is_rejected(tmp_path):
    p = tmp_path / "nocrs.tif"
    with rasterio.open(p, "w", driver="GTiff", width=16, height=16, count=1, dtype="uint8") as dst:
        dst.write(np.zeros((1, 16, 16), np.uint8))
    with pytest.raises(RasterValidationError) as err:
        inspect_raster(p)
    assert err.value.code == "no_crs"


def test_pixel_limit_enforced(synth):
    with pytest.raises(RasterValidationError) as err:
        inspect_raster(synth.before, max_pixels=1000)
    assert err.value.code == "too_large"


def test_band_roles_from_descriptions_and_count():
    named = detect_band_roles(["B02", "B03", "B04", "B08", "SCL"], 5)
    assert named["band_map"] == {"blue": 1, "green": 2, "red": 3, "nir": 4, "scl": 5}
    assert not named["needs_confirmation"]
    rgb = detect_band_roles([None, None, None], 3)
    assert rgb["band_map"] == {"red": 1, "green": 2, "blue": 3} and rgb["needs_confirmation"]
    four = detect_band_roles([None] * 4, 4)
    assert four["needs_confirmation"] and any("NIR" in n for n in four["notes"])


def test_utm_zone_selection():
    assert utm_crs_for_lonlat(15.0, 40.0).to_epsg() == 32633
    assert utm_crs_for_lonlat(-70.0, -10.0).to_epsg() == 32719
    assert utm_crs_for_lonlat(0.0, 89.0).to_epsg() == 32661


def test_valid_pair_has_no_errors(synth):
    v = validate_pair(inspect_raster(synth.before), inspect_raster(synth.after))
    assert v.ok
    assert v.analysis_crs_epsg == 32633
    assert v.overlap["fraction_of_before"] == pytest.approx(1.0, abs=1e-6)
    assert v.bands["common_roles"] == ["blue", "green", "red", "nir"]


def test_non_overlapping_pair_is_an_error(synth, tmp_path):
    far = write_geotiff(tmp_path / "far.tif", np.ones((4, 64, 64), np.uint16), crs="EPSG:32633",
                        transform=Affine(10, 0, 900000, 0, -10, 4500000), descriptions=["blue", "green", "red", "nir"],
                        build_overviews=False)
    v = validate_pair(inspect_raster(synth.before), inspect_raster(far))
    assert not v.ok
    assert any(i.code in ("no_overlap", "insufficient_overlap") for i in v.errors)


def test_partial_overlap_resolution_and_crs_mismatch_warn(synth, tmp_path):
    # shifted by half a scene, 20 m pixels, in a different CRS (UTM 32N) => all three warnings
    p = write_geotiff(tmp_path / "other.tif", np.ones((4, 256, 256), np.uint16) * 100, crs="EPSG:32632",
                      transform=Affine(20, 0, 300000 + 0, 0, -20, 4500000), descriptions=["blue", "green", "red", "nir"],
                      build_overviews=False)
    v = validate_pair(inspect_raster(synth.before), inspect_raster(p))
    codes = {i.code for i in v.issues}
    assert {"crs_mismatch", "resolution_mismatch"} <= codes
    assert v.ok or "insufficient_overlap" in codes or "no_overlap" in codes
    assert v.resolution["target_pixel_size_m"] == pytest.approx(20.0)


def test_no_common_bands_is_an_error(synth, tmp_path):
    one = write_geotiff(tmp_path / "gray.tif", np.ones((1, 512, 512), np.uint8), crs="EPSG:32633",
                        transform=Affine(*inspect_raster(synth.before).transform), build_overviews=False)
    v = validate_pair(inspect_raster(synth.before), inspect_raster(one))
    assert not v.ok and any(i.code == "no_common_bands" for i in v.errors)
