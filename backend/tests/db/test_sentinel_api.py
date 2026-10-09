"""Sentinel search -> acquire -> analyse, with the provider mocked at the HTTP layer (no live credentials needed)."""
import json
from datetime import datetime, timezone

import httpx
import numpy as np
import pytest
import respx
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from scipy import ndimage

from app.config import settings
from app.jobs.runner import drain
from app.providers.registry import reset_status_cache
from app.providers.sentinel import reset_provider_cache
from tests.db.conftest import auth, make_user

pytestmark = pytest.mark.asyncio
API = "/api/v1"
TOKEN = settings.CDSE_TOKEN_URL
STAC = settings.CDSE_STAC_URL.rstrip("/")
SH = settings.CDSE_SH_BASE_URL.rstrip("/")
AOI_BBOX = [-62.32, -10.92, -62.28, -10.88]  # ~4.4 km square
FOOT = {"type": "Polygon", "coordinates": [[[-63, -11.5], [-61.9, -11.5], [-61.9, -10.4], [-63, -10.4], [-63, -11.5]]]}
SCENES = {
    "S2B_BEFORE_LOWCLOUD": ("2024-02-10T14:27:19Z", 2.0), "S2B_BEFORE_CLOUDY": ("2024-02-20T14:27:19Z", 28.0),
    "S2B_AFTER_LOWCLOUD": ("2024-08-05T14:27:21Z", 1.5), "S2B_AFTER_LATER": ("2024-08-25T14:27:21Z", 40.0),
}


def feature(pid):
    dt, cc = SCENES[pid]
    return {"id": pid, "geometry": FOOT, "properties": {"datetime": dt, "eo:cloud_cover": cc, "platform": "sentinel-2b", "gsd": 10, "processing:level": "L2"}}


def stac_search(request):
    body = json.loads(request.content)
    start = body["datetime"].split("/")[0]
    keep = [k for k, (dt, cc) in SCENES.items() if k.startswith("S2B_BEFORE" if start < "2024-05" else "S2B_AFTER") and cc <= body["query"]["eo:cloud_cover"]["lte"]
            and body["datetime"].split("/")[0] <= dt <= body["datetime"].split("/")[1]]
    return httpx.Response(200, json={"type": "FeatureCollection", "features": [feature(k) for k in keep]})


def scene_pixels(bbox, w, h, after: bool):
    """Synthetic reflectance*10000 mosaic: a vegetated field that becomes bare soil after a 90x60 px clearing; some cloud in 'after'."""
    rng = np.random.default_rng(int(abs(bbox[0]) * 7 + (1000 if after else 0)) % 2**31)
    arr = np.zeros((6, h, w), np.uint16)
    veg = ndimage.gaussian_filter(np.random.default_rng(1).standard_normal((h, w)), 30) > 0
    base = np.where(veg, 1, 0)
    refl = {True: (400, 900, 500, 4000), False: (1600, 2000, 2200, 2800)}
    for i in range(4):
        arr[i] = np.where(base == 1, refl[True][i], refl[False][i]) + rng.normal(0, 40, (h, w))
    if after:
        arr[:4, 100:190, 100:160] = np.array(refl[False])[:, None, None]  # clearing of vegetation (changed)
        arr[:4] = arr[:4] * 1.05 + 30  # illumination difference
        arr[:4, 300:340, 300:340] = 9000  # cloud (bright)
    arr[4] = 4
    if after:
        arr[4, 300:340, 300:340] = 9  # SCL: cloud high probability
    arr[5] = 1
    return arr


def process_handler(counter):
    def handler(request):
        counter.append(1)
        body = json.loads(request.content)
        b = body["input"]["bounds"]
        epsg = int(b["properties"]["crs"].rsplit("/", 1)[1])
        w, h = body["output"]["width"], body["output"]["height"]
        after = body["input"]["data"][0]["dataFilter"]["timeRange"]["from"] > "2024-05"
        with MemoryFile() as mf:
            with mf.open(driver="GTiff", width=w, height=h, count=6, dtype="uint16", crs=f"EPSG:{epsg}", transform=from_bounds(*b["bbox"], w, h)) as ds:
                ds.write(np.clip(scene_pixels(b["bbox"], w, h, after), 0, 65535).astype(np.uint16))
            return httpx.Response(200, content=mf.read())
    return handler


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(settings, "SENTINEL_PROVIDER", "cdse")
    monkeypatch.setattr(settings, "SENTINEL_HUB_CLIENT_ID", "sh-test-client")
    monkeypatch.setattr(settings, "SENTINEL_HUB_CLIENT_SECRET", "test-secret")
    reset_provider_cache(); reset_status_cache()
    yield
    reset_provider_cache(); reset_status_cache()


@pytest.fixture
async def ctx(client, db, provider):
    user = await make_user(db, "user")
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    return {"user": user, "h": h, "proj": proj}


def search_body(**kw):
    return {"bbox": AOI_BBOX, "before": {"start": "2024-01-15", "end": "2024-03-15"}, "after": {"start": "2024-07-15", "end": "2024-09-15"},
            "max_cloud_cover_pct": 30, **kw}


@respx.mock
async def test_search_returns_scenes_with_coverage_and_documented_suggestion(client, ctx):
    respx.post(f"{STAC}/search").mock(side_effect=stac_search)
    r = await client.post(f"{API}/sentinel/search", headers=ctx["h"], json=search_body())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["provider"] == "cdse" and 15 < d["aoi_area_km2"] < 25
    assert [s["product_id"] for s in d["before"]] == ["S2B_BEFORE_LOWCLOUD", "S2B_BEFORE_CLOUDY"]
    assert [s["product_id"] for s in d["after"]] == ["S2B_AFTER_LOWCLOUD"]  # the 40% scene is excluded by the 30% limit
    assert all(s["coverage_of_aoi_pct"] == pytest.approx(100.0) for s in d["before"] + d["after"])
    assert d["suggested_before"] == "S2B_BEFORE_LOWCLOUD" and d["suggested_after"] == "S2B_AFTER_LOWCLOUD" and "cloud" in d["suggestion_rule"]
    assert d["warnings"] == []  # full coverage, scenes on both sides, credentials configured


@respx.mock
async def test_search_with_no_results_explains_instead_of_picking_something(client, ctx):
    respx.post(f"{STAC}/search").mock(return_value=httpx.Response(200, json={"type": "FeatureCollection", "features": []}))
    d = (await client.post(f"{API}/sentinel/search", headers=ctx["h"], json=search_body())).json()
    assert d["before"] == [] and d["after"] == [] and d["suggested_before"] is None
    assert any("BEFORE" in w for w in d["warnings"]) and any("AFTER" in w for w in d["warnings"])


async def test_search_validates_input(client, ctx):
    big = {"bbox": [-63, -12, -61, -10]}  # ~ 48,000 km2
    r = await client.post(f"{API}/sentinel/search", headers=ctx["h"], json=search_body(**big))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_aoi" and "limit" in r.json()["detail"]["message"]
    r2 = await client.post(f"{API}/sentinel/search", headers=ctx["h"], json={**search_body(), "after": {"start": "2024-01-20", "end": "2024-02-01"}})
    assert r2.status_code == 422  # windows must be ordered
    r3 = await client.post(f"{API}/sentinel/search", headers=ctx["h"], json={"before": {"start": "2024-01-01", "end": "2024-02-01"}, "after": {"start": "2024-07-01", "end": "2024-08-01"}})
    assert r3.status_code == 422  # an AOI is required
    r4 = await client.post(f"{API}/sentinel/search", json=search_body())
    assert r4.status_code == 401


@respx.mock
async def test_acquire_downloads_scenes_masks_clouds_and_records_provenance(client, ctx):
    h = ctx["h"]
    respx.post(TOKEN).mock(return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 3600}))
    respx.get(url__regex=rf"{STAC}/collections/sentinel-2-l2a/items/.+").mock(
        side_effect=lambda req: httpx.Response(200, json=feature(str(req.url).rsplit("/", 1)[1])))
    calls = []
    respx.post(f"{SH}/api/v1/process").mock(side_effect=process_handler(calls))
    body = {"project_id": ctx["proj"]["id"], "aoi_geometry": {"type": "Polygon", "coordinates": [[
        [AOI_BBOX[0], AOI_BBOX[1]], [AOI_BBOX[2], AOI_BBOX[1]], [AOI_BBOX[2], AOI_BBOX[3]], [AOI_BBOX[0], AOI_BBOX[3]], [AOI_BBOX[0], AOI_BBOX[1]]]]},
            "before_product_id": "S2B_BEFORE_LOWCLOUD", "after_product_id": "S2B_AFTER_LOWCLOUD", "name": "Cdse mocked",
            "config": {"detection": {"method": "spectral_cva"}}}
    r = await client.post(f"{API}/sentinel/acquire", headers=h, json=body)
    assert r.status_code == 202, r.text
    aid = r.json()["analysis_id"]
    queued = (await client.get(f"{API}/analyses/{aid}", headers=h)).json()
    assert queued["status"] == "queued" and queued["input_type"] == "sentinel" and queued["before_asset_id"] is None
    assert queued["before_date"] == "2024-02-10T14:27:19Z" and queued["after_date"] == "2024-08-05T14:27:21Z"  # dates from the scenes

    await drain()
    a = (await client.get(f"{API}/analyses/{aid}", headers=h)).json()
    assert a["status"] == "completed", a.get("error")
    assert len(calls) == 2  # one tile per scene
    ev = [e["status"] for e in (await client.get(f"{API}/analyses/{aid}/events", headers=h)).json()]
    assert "acquiring_imagery" in ev and ev.index("acquiring_imagery") < ev.index("preprocessing")
    prog = [e["progress"] for e in (await client.get(f"{API}/analyses/{aid}/events", headers=h)).json()]
    assert prog == sorted(prog)
    # imagery provenance
    assets = {x["source_product_id"]: x for x in (await client.get(f"{API}/imagery?project_id={ctx['proj']['id']}", headers=h)).json()}
    b = assets["S2B_BEFORE_LOWCLOUD"]
    assert b["kind"] == "sentinel" and b["source_provider"] == "cdse" and b["cloud_cover_pct"] == 2.0 and b["pixel_size_m"] == pytest.approx(10.0)
    assert b["band_descriptions"] == ["blue", "green", "red", "nir", "scl", "data_mask"] and b["band_map"]["scl"] == 5
    assert b["crs_epsg"] == 32720 and b["acquisition_start"] == "2024-02-10T14:27:19Z"
    # the clearing is detected; the (bright) cloud patch is masked out via SCL, not reported as change
    feats = (await client.get(f"{API}/analyses/{aid}/features", headers=h)).json()["items"]
    assert len(feats) == 1 and 4.5e5 < feats[0]["area_m2"] < 6.5e5  # 90 x 60 px at 10 m = 540,000 m2
    assert feats[0]["category"] == "vegetation_decrease"
    assert any(w["code"] == "cloud_masked" for w in a["warnings"])
    assert a["summary"]["valid_fraction"] < 1.0 and a["summary"]["valid_fraction"] > 0.97
    assert a["method"] == "spectral_cva"
    # export carries the provider provenance
    fc = (await client.get(f"{API}/analyses/{aid}/export?format=geojson", headers=h)).json()
    assert fc["features"][0]["properties"]["before_source"] == "cdse:S2B_BEFORE_LOWCLOUD"

    # idempotent: acquiring the same scenes again must not call the (billable) Process API again
    r2 = await client.post(f"{API}/sentinel/acquire", headers=h, json={**body, "name": "again"})
    await drain()
    a2 = (await client.get(f"{API}/analyses/{r2.json()['analysis_id']}", headers=h)).json()
    assert a2["status"] == "completed" and len(calls) == 2
    assert a2["before_asset_id"] == a["before_asset_id"]


@respx.mock
async def test_auto_select_uses_the_documented_rule(client, ctx):
    h = ctx["h"]
    respx.post(f"{STAC}/search").mock(side_effect=stac_search)
    respx.post(TOKEN).mock(return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 3600}))
    calls = []
    respx.post(f"{SH}/api/v1/process").mock(side_effect=process_handler(calls))
    r = await client.post(f"{API}/sentinel/acquire", headers=h, json={
        "project_id": ctx["proj"]["id"], "aoi_geometry": {"type": "Polygon", "coordinates": [[[AOI_BBOX[0], AOI_BBOX[1]], [AOI_BBOX[2], AOI_BBOX[1]], [AOI_BBOX[2], AOI_BBOX[3]], [AOI_BBOX[0], AOI_BBOX[1]]]]},
        "auto_select": True, "before": {"start": "2024-01-15", "end": "2024-03-15"}, "after": {"start": "2024-07-15", "end": "2024-09-15"}})
    assert r.status_code == 202, r.text
    assert (r.json()["before_product_id"], r.json()["after_product_id"]) == ("S2B_BEFORE_LOWCLOUD", "S2B_AFTER_LOWCLOUD")
    a = (await client.get(f"{API}/analyses/{r.json()['analysis_id']}", headers=h)).json()
    assert a["input_type"] == "sentinel"
    from app.models import AnalysisJob
    from app.database import async_session_maker
    async with async_session_maker() as s:
        job = await s.get(AnalysisJob, __import__("uuid").UUID(a["id"]))
        assert job.acquisition_params["selection"] == "automatic" and "cloud" in job.acquisition_params["selection_rule"]


@respx.mock
async def test_auto_select_without_suitable_scene_is_refused_not_guessed(client, ctx):
    respx.post(f"{STAC}/search").mock(return_value=httpx.Response(200, json={"type": "FeatureCollection", "features": []}))
    r = await client.post(f"{API}/sentinel/acquire", headers=ctx["h"], json={
        "project_id": ctx["proj"]["id"], "aoi_geometry": {"type": "Polygon", "coordinates": [[[AOI_BBOX[0], AOI_BBOX[1]], [AOI_BBOX[2], AOI_BBOX[1]], [AOI_BBOX[2], AOI_BBOX[3]], [AOI_BBOX[0], AOI_BBOX[1]]]]},
        "auto_select": True, "before": {"start": "2024-01-15", "end": "2024-03-15"}, "after": {"start": "2024-07-15", "end": "2024-09-15"}})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "no_suitable_scene" and "Adjust the dates" in r.json()["detail"]["message"]


async def test_acquire_without_credentials_reports_not_configured_and_does_not_fabricate(client, db, monkeypatch):
    monkeypatch.setattr(settings, "SENTINEL_PROVIDER", "auto")
    monkeypatch.setattr(settings, "SENTINEL_HUB_CLIENT_ID", None)
    monkeypatch.setattr(settings, "SENTINEL_HUB_CLIENT_SECRET", None)
    reset_provider_cache(); reset_status_cache()
    user = await make_user(db, "user")
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    r = await client.post(f"{API}/sentinel/acquire", headers=h, json={
        "project_id": proj["id"], "aoi_geometry": {"type": "Polygon", "coordinates": [[[AOI_BBOX[0], AOI_BBOX[1]], [AOI_BBOX[2], AOI_BBOX[1]], [AOI_BBOX[2], AOI_BBOX[3]], [AOI_BBOX[0], AOI_BBOX[1]]]]},
        "before_product_id": "A", "after_product_id": "B"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "provider_not_configured" and "upload GeoTIFFs" in r.json()["detail"]["message"]
    assert (await client.get(f"{API}/analyses?project_id={proj['id']}", headers=h)).json() == []  # no job was created
    reset_provider_cache()


@respx.mock
async def test_provider_auth_failure_fails_the_job_with_a_clear_message(client, ctx):
    h = ctx["h"]
    respx.post(TOKEN).mock(return_value=httpx.Response(401, json={"error": "invalid_client"}))
    respx.get(url__regex=rf"{STAC}/collections/sentinel-2-l2a/items/.+").mock(side_effect=lambda req: httpx.Response(200, json=feature(str(req.url).rsplit("/", 1)[1])))
    r = await client.post(f"{API}/sentinel/acquire", headers=h, json={
        "project_id": ctx["proj"]["id"], "aoi_geometry": {"type": "Polygon", "coordinates": [[[AOI_BBOX[0], AOI_BBOX[1]], [AOI_BBOX[2], AOI_BBOX[1]], [AOI_BBOX[2], AOI_BBOX[3]], [AOI_BBOX[0], AOI_BBOX[1]]]]},
        "before_product_id": "S2B_BEFORE_LOWCLOUD", "after_product_id": "S2B_AFTER_LOWCLOUD"})
    assert r.status_code == 202
    await drain()
    a = (await client.get(f"{API}/analyses/{r.json()['analysis_id']}", headers=h)).json()
    assert a["status"] == "failed" and a["error"]["code"] == "provider_auth_failed" and "credentials" in a["error"]["message"]
    assert "test-secret" not in json.dumps(a)


@respx.mock
async def test_viewer_can_search_but_not_acquire(client, db, provider):
    viewer = await make_user(db, "viewer")
    respx.post(f"{STAC}/search").mock(side_effect=stac_search)
    assert (await client.post(f"{API}/sentinel/search", headers=auth(viewer), json=search_body())).status_code == 200
    r = await client.post(f"{API}/sentinel/acquire", headers=auth(viewer), json={"project_id": "00000000-0000-0000-0000-000000000000",
        "aoi_geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}, "before_product_id": "a", "after_product_id": "b"})
    assert r.status_code == 403


@respx.mock
async def test_rate_limited_search_maps_to_429(client, ctx, monkeypatch):
    import app.providers.http as ph

    async def nosleep(_):
        return None
    monkeypatch.setattr(ph.asyncio, "sleep", nosleep)
    respx.post(f"{STAC}/search").mock(return_value=httpx.Response(429, headers={"retry-after": "7"}))
    r = await client.post(f"{API}/sentinel/search", headers=ctx["h"], json=search_body())
    assert r.status_code == 429 and r.json()["detail"]["code"] == "provider_rate_limited" and r.headers["retry-after"] == "7"


@respx.mock
async def test_status_endpoint_reflects_real_probe_results(client, ctx):
    respx.get(f"{STAC}/").mock(return_value=httpx.Response(200, json={"type": "Catalog"}))
    respx.post(TOKEN).mock(return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 3600}))
    s = (await client.get(f"{API}/sentinel/status?refresh=true", headers=ctx["h"])).json()[0]
    assert s["provider"] == "cdse" and s["catalog"] == "available" and s["imagery"] == "available" and s["configured"]
    respx.post(TOKEN).mock(return_value=httpx.Response(401, json={"error": "invalid_client"}))
    reset_provider_cache()
    s2 = (await client.get(f"{API}/sentinel/status?refresh=true", headers=ctx["h"])).json()[0]
    assert s2["imagery"] == "unavailable" and "credentials" in s2["detail"]
