"""GeoTIFF writing helpers (tiled, compressed, with overviews)."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine


def default_profile(*, count: int, dtype: str, width: int, height: int, crs, transform: Affine, nodata=None) -> dict:
    kind = np.dtype(dtype).kind
    profile = {
        "driver": "GTiff",
        "count": count,
        "dtype": dtype,
        "width": width,
        "height": height,
        "crs": crs,
        "transform": transform,
        "tiled": width >= 256 and height >= 256,
        "compress": "deflate",
        "predictor": 3 if kind == "f" else (2 if kind in "iu" and np.dtype(dtype).itemsize > 1 else 1),
        "BIGTIFF": "IF_SAFER",
    }
    if profile["tiled"]:
        profile["blockxsize"] = 256
        profile["blockysize"] = 256
    if nodata is not None:
        profile["nodata"] = nodata
    return profile


def write_geotiff(
    path: str | Path,
    data: np.ndarray,
    *,
    crs,
    transform: Affine,
    nodata=None,
    descriptions: Sequence[str | None] | None = None,
    tags: dict[str, str] | None = None,
    build_overviews: bool = True,
    overview_resampling: Resampling = Resampling.average,
) -> Path:
    """Write ``data`` (bands, rows, cols) as a tiled, compressed GeoTIFF."""
    arr = data if data.ndim == 3 else data[np.newaxis, ...]
    count, height, width = arr.shape
    profile = default_profile(
        count=count, dtype=str(arr.dtype), width=width, height=height, crs=crs, transform=transform, nodata=nodata
    )
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(p, "w", **profile) as dst:
        dst.write(arr)
        if descriptions:
            for i, d in enumerate(descriptions, start=1):
                if d and i <= count:
                    dst.set_band_description(i, d)
        if tags:
            dst.update_tags(**{k: str(v) for k, v in tags.items()})
        if build_overviews and min(width, height) >= 512:
            levels = []
            f = 2
            while min(width, height) // f >= 128 and len(levels) < 6:
                levels.append(f)
                f *= 2
            if levels:
                dst.build_overviews(levels, overview_resampling)
    return p
