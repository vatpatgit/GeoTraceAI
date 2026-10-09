"""LIVE provider test (opt-in): real catalogue search + real Process API download + full pipeline.

    RUN_LIVE_SENTINEL=1 python -m pytest tests/integration -s

Uses the server's configured credentials (backend/.env). Costs a few processing units: one ~4 km x 4 km request per scene.
Not part of the default run (no credentials are required for the normal suite).
"""
import os
from datetime import datetime, timezone

import pytest
import rasterio

from app.geo.config import DetectionConfig, PipelineConfig
from app.geo.pipeline import run_pipeline
from app.providers.acquire import download_scene, plan_grid
from app.providers.sentinel import get_provider, reset_provider_cache
from app.services.sentinel import select_scene

pytestmark = [pytest.mark.skipif(os.environ.get("RUN_LIVE_SENTINEL") != "1", reason="set RUN_LIVE_SENTINEL=1 to run live provider tests"),
              pytest.mark.asyncio]

AOI = {"type": "Polygon", "coordinates": [[[-62.32, -10.92], [-62.28, -10.92], [-62.28, -10.88], [-62.32, -10.88], [-62.32, -10.92]]]}


async def test_live_search_download_and_detect(tmp_path):
    from shapely.geometry import shape
    from app.services.sentinel import scene_out

    reset_provider_cache()
    provider = get_provider()
    assert provider is not None and provider.imagery_configured, "configure SENTINEL_HUB_CLIENT_ID/SECRET in backend/.env"
    status = await provider.probe()
    print("probe:", status)
    assert status["catalog"] == "available" and status["imagery"] == "available", status

    aoi = shape(AOI)
    picked = {}
    for role, (a, b) in (("before", ("2024-06-01", "2024-07-31")), ("after", ("2025-06-01", "2025-07-31"))):
        scenes = await provider.search(AOI, datetime.fromisoformat(a + "T00:00:00+00:00"), datetime.fromisoformat(b + "T23:59:59+00:00"), max_cloud_pct=25, limit=20)
        out = [scene_out(s, aoi) for s in scenes]
        print(role, "scenes:", [(s.product_id[-22:], s.cloud_cover_pct, round(s.coverage_of_aoi_pct or 0)) for s in out])
        assert out, f"no {role} scenes found; widen the window"
        picked[role] = select_scene(out, role)
        print(role, "selected:", picked[role].product_id, picked[role].acquired_at, picked[role].cloud_cover_pct)

    plan = plan_grid(AOI, 10.0)
    paths = {}
    for role, sc in picked.items():
        dest = tmp_path / f"{role}.tif"
        meta = await download_scene(provider, plan, sc.acquired_at, dest, tags={"product_id": sc.product_id})
        print(role, "downloaded:", meta)
        paths[role] = dest
        with rasterio.open(dest) as ds:
            assert ds.count == 6 and ds.crs.to_epsg() == plan.epsg and (ds.width, ds.height) == (plan.width, plan.height)
            red = ds.read(3).astype(float)
            assert 0 < red[ds.read(6) > 0].mean() < 6000  # plausible reflectance*10000, not an all-zero / garbage image
        assert meta["valid_fraction"] > 0.5

    res = run_pipeline(paths["before"], paths["after"], tmp_path / "work", PipelineConfig(detection=DetectionConfig(method="spectral_cva")))
    s = res.summary
    print(f"pipeline: {s['feature_count']} polygons, changed {s['total_changed_area_m2'] / 1e4:.1f} ha of {s['analyzed_area_m2'] / 1e4:.0f} ha, "
          f"valid {s['valid_fraction']:.1%}, cloud-masked {res.aligned.cloud_masked_fraction:.1%}, registration {res.aligned.registration}")
    assert s["valid_fraction"] > 0.5 and s["analyzed_area_m2"] > 1e6
    assert all(f.area_m2 > 0 and f.geometry.is_valid for f in res.features)
