"""Sentinel Hub Process API client (used by both CDSE's and the commercial Sentinel Hub deployments)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.providers.base import ProviderAuthError
from app.providers.http import TokenManager, request

# Analysis-ready bands for the change pipeline: reflectance*10000 (UINT16) for B02/B03/B04/B08 plus the scene
# classification (SCL, used for cloud / shadow / cirrus masking) and the data mask. Band order is fixed and mirrored by
# BAND_DESCRIPTIONS so the pipeline reads band roles from metadata instead of guessing.
ANALYSIS_EVALSCRIPT = """//VERSION=3
function setup() {
  return { input: [{ bands: ["B02", "B03", "B04", "B08", "SCL", "dataMask"], units: ["REFLECTANCE", "REFLECTANCE", "REFLECTANCE", "REFLECTANCE", "DN", "DN"] }],
           output: { bands: 6, sampleType: "UINT16" } };
}
function evaluatePixel(s) {
  return [Math.round(s.B02 * 10000), Math.round(s.B03 * 10000), Math.round(s.B04 * 10000), Math.round(s.B08 * 10000), s.SCL, s.dataMask];
}
"""
BAND_DESCRIPTIONS = ["blue", "green", "red", "nir", "scl", "data_mask"]

PREVIEW_EVALSCRIPT = """//VERSION=3
function setup() { return { input: ["B02", "B03", "B04", "dataMask"], output: { bands: 4, sampleType: "UINT8" } }; }
function evaluatePixel(s) { return [255 * Math.min(1, 2.5 * s.B04), 255 * Math.min(1, 2.5 * s.B03), 255 * Math.min(1, 2.5 * s.B02), 255 * s.dataMask]; }
"""

# The catalogue's acquisition time and the Process API's per-tile timestamps can differ by more than a few minutes (observed for
# a Mumbai scene: empty result at +-10 min, full image at +-12 h). +-3 h still isolates a single satellite pass because
# Sentinel-2 revisits a given tile at most about twice per day (never within 3 hours).
SCENE_WINDOW_S = 3 * 3600

# Pixels the scene classification (SCL) marks as no-data, saturated, cloud shadow, medium/high cloud probability or thin cirrus
# become alpha 255 ("bad"); everything else is 0. Used to keep clouds out of ML change detection.
BADMASK_EVALSCRIPT = """//VERSION=3
function setup() {
  return { input: [{ bands: ["SCL", "dataMask", "B02", "B03", "B04"], units: ["DN", "DN", "REFLECTANCE", "REFLECTANCE", "REFLECTANCE"] }],
           output: { bands: 4, sampleType: "UINT8" } };
}
function evaluatePixel(s) {
  var scl = s.SCL === 0 || s.SCL === 1 || s.SCL === 3 || s.SCL === 8 || s.SCL === 9 || s.SCL === 10;
  // The scene classification misses small / thin clouds: also flag bright, spectrally flat (white) pixels.
  var mx = Math.max(s.B02, s.B03, s.B04), mn = Math.min(s.B02, s.B03, s.B04);
  var white = mn > 0.20 && (mx - mn) < 0.12;
  var bad = s.dataMask === 0 || scl || white;
  return [0, 0, 0, bad ? 255 : 0];
}
"""


def time_range(acquired_at: datetime, window_s: int) -> dict[str, str]:
    t = acquired_at.astimezone(timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return {"from": (t - timedelta(seconds=window_s)).strftime(fmt), "to": (t + timedelta(seconds=window_s)).strftime(fmt)}


class ProcessClient:
    def __init__(self, base_url: str, tokens: TokenManager, data_type: str = "sentinel-2-l2a"):
        self.base_url = base_url.rstrip("/")
        self.tokens = tokens
        self.data_type = data_type

    async def _post(self, payload: dict[str, Any], accept: str) -> bytes:
        for attempt in (0, 1):
            token = await self.tokens.get(force=attempt == 1)
            try:
                resp = await request("POST", f"{self.base_url}/api/v1/process", json=payload, timeout=180.0,
                                     headers={"Authorization": f"Bearer {token}", "Accept": accept, "Content-Type": "application/json"})
                return resp.content
            except ProviderAuthError:
                if attempt == 1:
                    raise
                self.tokens.invalidate()  # token may have expired server-side; retry once with a fresh one
        raise ProviderAuthError("Authentication failed")  # pragma: no cover

    def _payload(self, bounds: dict[str, Any], acquired_at: datetime, window_s: int, width: int, height: int,
                 fmt: str, evalscript: str) -> dict[str, Any]:
        return {
            "input": {
                "bounds": bounds,
                "data": [{"type": self.data_type, "dataFilter": {"timeRange": time_range(acquired_at, window_s), "mosaickingOrder": "mostRecent"}}],
            },
            "output": {"width": width, "height": height, "responses": [{"identifier": "default", "format": {"type": fmt}}]},
            "evalscript": evalscript,
        }

    async def geotiff(self, *, epsg: int, bbox: tuple[float, float, float, float], width: int, height: int, acquired_at: datetime,
                      window_s: int = SCENE_WINDOW_S) -> bytes:
        bounds = {"bbox": list(bbox), "properties": {"crs": f"http://www.opengis.net/def/crs/EPSG/0/{epsg}"}}
        return await self._post(self._payload(bounds, acquired_at, window_s, width, height, "image/tiff", ANALYSIS_EVALSCRIPT), "image/tiff")

    async def preview_png(self, *, bbox_wgs84: tuple[float, float, float, float], acquired_at: datetime, width: int, height: int,
                          window_s: int = SCENE_WINDOW_S) -> bytes:
        bounds = {"bbox": list(bbox_wgs84), "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}}
        return await self._post(self._payload(bounds, acquired_at, window_s, width, height, "image/png", PREVIEW_EVALSCRIPT), "image/png")

    async def badmask_png(self, *, bbox_wgs84: tuple[float, float, float, float], acquired_at: datetime, width: int, height: int,
                          window_s: int = SCENE_WINDOW_S) -> bytes:
        bounds = {"bbox": list(bbox_wgs84), "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}}
        return await self._post(self._payload(bounds, acquired_at, window_s, width, height, "image/png", BADMASK_EVALSCRIPT), "image/png")
