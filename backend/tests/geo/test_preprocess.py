import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

from app.geo.config import PreprocessConfig
from app.geo.errors import PairIncompatibleError
from app.geo.preprocess import align_pair
from app.geo.raster_io import inspect_raster
from app.geo.registration import estimate_shift
from app.geo.writers import write_geotiff


def test_same_grid_pair_is_aligned_losslessly(synth, tmp_path):
    out = align_pair(synth.before, synth.after, tmp_path)
    assert (out.width, out.height) == (512, 512)
    assert out.pixel_size_m == pytest.approx(10.0)
    assert out.crs_epsg == 32633
    assert out.roles == ["blue", "green", "red", "nir"]
    assert out.valid_fraction == pytest.approx(1.0)
    with rasterio.open(synth.before) as a, rasterio.open(out.before_path) as b:
        assert a.transform == b.transform
        assert np.array_equal(a.read(), b.read())  # identical grid => nothing resampled
    assert not out.registration["reliable"] or out.registration["magnitude_px"] < 0.5


def test_offgrid_geographic_input_is_reprojected_to_utm(synth, tmp_path):
    # Re-project the "after" image to EPSG:4326 (as a user upload might be) and align again.
    from rasterio.warp import calculate_default_transform, reproject, Resampling

    with rasterio.open(synth.after) as src:
        t, w, h = calculate_default_transform(src.crs, "EPSG:4326", src.width, src.height, *src.bounds)
        data = np.zeros((src.count, h, w), src.dtypes[0])
        for i in range(1, src.count + 1):
            reproject(rasterio.band(src, i), data[i - 1], src_transform=src.transform, src_crs=src.crs,
                      dst_transform=t, dst_crs="EPSG:4326", resampling=Resampling.bilinear)
        geo = write_geotiff(tmp_path / "after_geo.tif", data, crs="EPSG:4326", transform=t,
                            descriptions=src.descriptions, build_overviews=False)
    out = align_pair(synth.before, geo, tmp_path / "out")
    assert out.crs_epsg == 32633  # before is already metric UTM and the shared analysis CRS wins
    codes = {w["code"] for w in out.warnings}
    assert "crs_mismatch" in codes
    # the interior is valid; the sliver outside the (rotated) warped footprint is masked
    assert 0.9 < out.valid_fraction <= 1.0


def test_aoi_crop_limits_the_grid(synth, tmp_path):
    from pyproj import Transformer
    from shapely.geometry import box
    from shapely.ops import transform

    # AOI = central 2.56 km x 2.56 km square (256 px) expressed in WGS84
    tr = Transformer.from_crs("EPSG:32633", "EPSG:4326", always_xy=True)
    aoi = transform(tr.transform, box(500000 + 1280, 4500000 - 3840, 500000 + 3840, 4500000 - 1280))
    out = align_pair(synth.before, synth.after, tmp_path, aoi_wgs84=aoi)
    assert 250 <= out.width <= 262 and 250 <= out.height <= 262
    assert any(w["code"] == "aoi_clip" for w in out.warnings)


def test_pixel_cap_gives_actionable_error(synth, tmp_path):
    with pytest.raises(PairIncompatibleError) as err:
        align_pair(synth.before, synth.after, tmp_path, PreprocessConfig(max_pixels=10_000))
    assert err.value.code == "too_many_pixels"
    assert "Reduce the area of interest" in str(err.value)


def test_no_overlap_raises(synth, tmp_path):
    far = write_geotiff(tmp_path / "far.tif", np.ones((4, 64, 64), np.uint16), crs="EPSG:32633",
                        transform=Affine(10, 0, 900000, 0, -10, 4500000), descriptions=["blue", "green", "red", "nir"],
                        build_overviews=False)
    with pytest.raises(PairIncompatibleError):
        align_pair(synth.before, far, tmp_path / "o")


def test_nodata_edges_are_masked(synth, tmp_path):
    # Copy the before image, setting a 40 px wide NoData frame; valid fraction must drop accordingly.
    with rasterio.open(synth.before) as src:
        data = src.read()
        profile = src.profile
    data[:, :, :40] = 0
    nd = tmp_path / "nd.tif"
    profile.update(nodata=0)
    with rasterio.open(nd, "w", **profile) as dst:
        dst.write(data)
        for i, d in enumerate(["blue", "green", "red", "nir"], 1):
            dst.set_band_description(i, d)
    out = align_pair(nd, synth.after, tmp_path / "o")
    with rasterio.open(out.valid_mask_path) as m:
        mask = m.read(1)
    assert mask[:, :40].sum() == 0
    assert out.valid_fraction == pytest.approx(1 - 40 / 512, abs=0.02)


def test_misregistration_is_detected(synth, tmp_path):
    with rasterio.open(synth.after) as src:
        data = src.read()
        prof = src.profile
    shifted = np.roll(data, shift=(0, 4), axis=(1, 2))  # 4 px to the right
    p = tmp_path / "shifted.tif"
    with rasterio.open(p, "w", **prof) as dst:
        dst.write(shifted)
        for i, d in enumerate(["blue", "green", "red", "nir"], 1):
            dst.set_band_description(i, d)
    out = align_pair(synth.before, p, tmp_path / "o")
    assert out.registration["reliable"]
    assert out.registration["magnitude_px"] == pytest.approx(4.0, abs=0.7)
    assert any(w["code"] == "possible_misregistration" for w in out.warnings)


def test_phase_correlation_sign_and_subpixel():
    rng = np.random.default_rng(0)
    base = rng.random((256, 256)).astype(np.float32)
    from scipy import ndimage
    base = ndimage.gaussian_filter(base, 2)
    moved = np.roll(base, shift=(3, -5), axis=(0, 1))
    est = estimate_shift(base, moved)
    # a == b shifted back by (+5 x, -3 y)
    assert est.dx_px == pytest.approx(5.0, abs=0.3)
    assert est.dy_px == pytest.approx(-3.0, abs=0.3)
    assert est.peak > 0.3
