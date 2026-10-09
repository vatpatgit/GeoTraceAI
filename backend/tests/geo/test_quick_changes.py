import io

import numpy as np
import pytest
import rasterio
from PIL import Image

from app.services.quick_changes import _write_rgb_tiff

BBOX = (10.0, 20.0, 10.1, 20.1)


def png(rgba):
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    return buf.getvalue()


def test_tiff_is_georeferenced_and_masks_transparent_and_cloudy_pixels(tmp_path):
    rgba = np.full((20, 40, 4), (80, 120, 60, 255), dtype=np.uint8)
    rgba[:, :5, 3] = 0  # provider returned no data here
    bad = np.zeros((20, 40), dtype=bool)
    bad[10:, 20:] = True  # cloud / shadow
    w, valid = _write_rgb_tiff(png(rgba), BBOX, tmp_path / "a.tif", bad)
    assert w == 40
    with rasterio.open(tmp_path / "a.tif") as ds:
        assert ds.crs.to_epsg() == 4326 and ds.count == 3 and ds.nodata == 0
        assert tuple(round(v, 6) for v in ds.bounds) == BBOX
        data = ds.read()
        assert (data[:, :, :5] == 0).all()  # no-data stays nodata
        assert (data[:, 10:, 20:] == 0).all()  # masked cloud is excluded from the comparison
        assert (data[:, :10, 5:] > 0).all()
    assert valid == pytest.approx(1 - (20 * 5 + 10 * 20 - 0) / (20 * 40), abs=1e-6)


def test_real_dark_pixels_are_not_mistaken_for_nodata(tmp_path):
    rgba = np.zeros((8, 8, 4), dtype=np.uint8)
    rgba[..., 3] = 255  # opaque black
    _, valid = _write_rgb_tiff(png(rgba), BBOX, tmp_path / "b.tif")
    assert valid == 1.0
    with rasterio.open(tmp_path / "b.tif") as ds:
        assert (ds.read() > 0).all()
