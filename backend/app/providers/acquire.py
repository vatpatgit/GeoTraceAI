"""Scene retrieval: plan a metric grid over the AOI, fetch (tiled) GeoTIFFs from the provider, mosaic, register as assets."""
from __future__ import annotations

import hashlib
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.io import MemoryFile
from rasterio.transform import Affine
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

from app import storage
from app.config import settings
from app.geo.errors import GeoProcessingError
from app.geo.raster_io import utm_crs_for_lonlat
from app.geo.writers import write_geotiff
from app.providers.base import ProviderError
from app.providers.process_api import ANALYSIS_EVALSCRIPT, BAND_DESCRIPTIONS

MAX_REQUEST_PX = 2000  # Process API limit is 2500 px per side; keep headroom
EVALSCRIPT_SHA = hashlib.sha256(ANALYSIS_EVALSCRIPT.encode()).hexdigest()[:16]
ProgressFn = Callable[[float, str], None]


@dataclass
class GridPlan:
    epsg: int
    left: float
    top: float
    width: int
    height: int
    pixel_size: float

    @property
    def transform(self) -> Affine:
        return Affine(self.pixel_size, 0, self.left, 0, -self.pixel_size, self.top)

    def tiles(self) -> list[tuple[int, int, int, int]]:
        """(col0, row0, w, h) blocks of at most MAX_REQUEST_PX per side."""
        out = []
        for r0 in range(0, self.height, MAX_REQUEST_PX):
            for c0 in range(0, self.width, MAX_REQUEST_PX):
                out.append((c0, r0, min(MAX_REQUEST_PX, self.width - c0), min(MAX_REQUEST_PX, self.height - r0)))
        return out


def plan_grid(aoi_geojson: dict[str, Any], pixel_size: float) -> GridPlan:
    poly = shape(aoi_geojson)
    c = poly.centroid
    crs = utm_crs_for_lonlat(c.x, c.y)
    to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    minx, miny, maxx, maxy = shp_transform(to_utm.transform, poly).bounds
    left = math.floor(minx / pixel_size) * pixel_size
    top = math.ceil(maxy / pixel_size) * pixel_size
    right = math.ceil(maxx / pixel_size) * pixel_size
    bottom = math.floor(miny / pixel_size) * pixel_size
    w, h = int(round((right - left) / pixel_size)), int(round((top - bottom) / pixel_size))
    if w * h > settings.MAX_RASTER_PIXELS:
        side = math.sqrt(settings.MAX_RASTER_PIXELS) * pixel_size / 1000
        raise GeoProcessingError(
            f"The area needs {w * h / 1e6:.0f} MP at {pixel_size:g} m; the limit is {settings.MAX_RASTER_PIXELS / 1e6:.0f} MP. "
            f"Use an AOI of at most about {side:.0f} km x {side:.0f} km.", code="too_many_pixels")
    return GridPlan(epsg=crs.to_epsg(), left=left, top=top, width=w, height=h, pixel_size=pixel_size)


async def download_scene(provider, plan: GridPlan, acquired_at: datetime, dest, *, tags: dict[str, str],
                         progress: ProgressFn | None = None, cancel_check: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Fetch every tile of ``plan`` for the scene captured at ``acquired_at`` and write one analysis-ready GeoTIFF."""
    report = progress or (lambda f, m: None)
    mosaic = np.zeros((len(BAND_DESCRIPTIONS), plan.height, plan.width), dtype=np.uint16)
    tiles = plan.tiles()
    for i, (c0, r0, w, h) in enumerate(tiles):
        if cancel_check and cancel_check():
            from app.geo.pipeline import JobCancelled
            raise JobCancelled()
        x0 = plan.left + c0 * plan.pixel_size
        y1 = plan.top - r0 * plan.pixel_size
        bbox = (x0, y1 - h * plan.pixel_size, x0 + w * plan.pixel_size, y1)
        data = await provider.process_geotiff(epsg=plan.epsg, bbox=bbox, width=w, height=h, acquired_at=acquired_at)
        with MemoryFile(data) as mf, mf.open() as ds:
            if ds.count != len(BAND_DESCRIPTIONS) or (ds.width, ds.height) != (w, h):
                raise ProviderError(
                    f"Unexpected provider response ({ds.count} bands, {ds.width}x{ds.height}); expected "
                    f"{len(BAND_DESCRIPTIONS)} bands, {w}x{h}.", code="provider_bad_response", status=502)
            mosaic[:, r0:r0 + h, c0:c0 + w] = ds.read().astype(np.uint16)
        report((i + 1) / len(tiles), f"Downloaded tile {i + 1}/{len(tiles)}")
    if not mosaic[5].any():
        raise ProviderError("The provider returned no data for this scene and area (the scene may not cover the AOI).",
                            code="no_data_in_aoi", status=422)
    write_geotiff(dest, mosaic, crs=CRS.from_epsg(plan.epsg).to_wkt(), transform=plan.transform, descriptions=BAND_DESCRIPTIONS, tags=tags)
    return {"tiles": len(tiles), "epsg": plan.epsg, "width": plan.width, "height": plan.height, "pixel_size_m": plan.pixel_size,
            "evalscript_sha": EVALSCRIPT_SHA, "bands": BAND_DESCRIPTIONS,
            "valid_fraction": float((mosaic[5] > 0).mean())}


def aoi_hash(aoi_geojson: dict[str, Any], pixel_size: float) -> str:
    coords = np.round(np.array(shape(aoi_geojson).exterior.coords), 6).tolist()
    return hashlib.sha256(f"{coords}|{pixel_size}".encode()).hexdigest()[:20]


def new_asset_path():
    asset_id = uuid.uuid4()
    return asset_id, storage.asset_dir(asset_id) / "original.tif"
