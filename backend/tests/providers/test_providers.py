"""Provider layer with mocked HTTP: auth, retries, search parsing, selection rule, grid planning and tiled download."""
import json
from datetime import datetime, timezone

import httpx
import numpy as np
import pytest
import respx
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds

from app.config import settings
from app.geo.errors import GeoProcessingError
from app.providers import http as phttp
from app.providers.acquire import MAX_REQUEST_PX, download_scene, plan_grid
from app.providers.base import ProviderAuthError, ProviderError, ProviderNotConfigured, ProviderRateLimited, ProviderUnavailable
from app.providers.process_api import BAND_DESCRIPTIONS
from app.providers.sentinel import CdseProvider, SentinelHubProvider, build_provider, reset_provider_cache
from app.schemas.sentinel import SceneOut
from app.services.sentinel import SELECTION_RULE, select_scene

TOKEN = settings.CDSE_TOKEN_URL
STAC = settings.CDSE_STAC_URL.rstrip("/")
SH = settings.CDSE_SH_BASE_URL.rstrip("/")


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    async def nosleep(_):
        return None

    monkeypatch.setattr(phttp.asyncio, "sleep", nosleep)


def token_ok(expires=3600):
    return httpx.Response(200, json={"access_token": "tok-abc", "expires_in": expires})


@pytest.mark.asyncio
@respx.mock
async def test_token_is_cached_and_refreshed_when_expiring():
    route = respx.post(TOKEN).mock(side_effect=[token_ok(3600), token_ok(30), token_ok(3600)])
    tm = phttp.TokenManager(TOKEN, "sh-id", "secret")
    assert await tm.get() == "tok-abc" and await tm.get() == "tok-abc"
    assert route.call_count == 1  # cached
    tm._expires = 0
    await tm.get()
    assert route.call_count == 2
    await tm.get()  # the 30 s token is inside the 60 s refresh margin => refreshed again
    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_bad_credentials_give_a_clear_auth_error_without_leaking_secrets():
    respx.post(TOKEN).mock(return_value=httpx.Response(401, json={"error": "invalid_client", "error_description": "Invalid client credentials"}))
    tm = phttp.TokenManager(TOKEN, "sh-id", "super-secret-value")
    with pytest.raises(ProviderAuthError) as err:
        await tm.get()
    assert "rejected the configured credentials" in str(err.value) and "super-secret-value" not in str(err.value)


@pytest.mark.asyncio
@respx.mock
async def test_retries_5xx_and_429_then_succeeds_but_not_4xx():
    route = respx.get("https://x.test/a").mock(side_effect=[httpx.Response(503), httpx.Response(502), httpx.Response(200, json={"ok": 1})])
    assert (await phttp.request("GET", "https://x.test/a")).json() == {"ok": 1} and route.call_count == 3
    r2 = respx.get("https://x.test/b").mock(side_effect=[httpx.Response(429, headers={"retry-after": "1"}), httpx.Response(200, json={})])
    await phttp.request("GET", "https://x.test/b")
    assert r2.call_count == 2
    r3 = respx.get("https://x.test/c").mock(return_value=httpx.Response(404, json={"message": "no such thing"}))
    with pytest.raises(ProviderError) as err:
        await phttp.request("GET", "https://x.test/c")
    assert r3.call_count == 1 and err.value.status == 404  # 4xx (other than 429) are never retried


@pytest.mark.asyncio
@respx.mock
async def test_retry_budget_is_bounded_and_errors_are_classified():
    r = respx.get("https://x.test/d").mock(return_value=httpx.Response(503, text="down"))
    with pytest.raises(ProviderUnavailable):
        await phttp.request("GET", "https://x.test/d")
    assert r.call_count == settings.PROVIDER_MAX_RETRIES
    respx.get("https://x.test/e").mock(return_value=httpx.Response(429))
    with pytest.raises(ProviderRateLimited):
        await phttp.request("GET", "https://x.test/e", retries=1)
    respx.get("https://x.test/f").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderUnavailable) as err:
        await phttp.request("GET", "https://x.test/f")
    assert err.value.code == "provider_timeout" and err.value.status == 504
    respx.get("https://x.test/g").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ProviderUnavailable):
        await phttp.request("GET", "https://x.test/g")


STAC_FEATURES = {"type": "FeatureCollection", "features": [
    {"id": "S2A_A", "geometry": {"type": "Polygon", "coordinates": [[[-63, -11], [-62, -11], [-62, -10], [-63, -10], [-63, -11]]]},
     "properties": {"datetime": "2024-07-03T14:27:19.024000Z", "eo:cloud_cover": 3.2, "platform": "sentinel-2b", "gsd": 10, "processing:level": "L2",
                    "view:sun_elevation": 51.6, "sat:relative_orbit": 53, "unrelated": "dropped"}},
    {"id": "S2A_B", "geometry": None, "properties": {"datetime": "2024-07-08T14:27:19Z", "platform": "sentinel-2a"}},
    {"id": "S2A_NODATE", "geometry": None, "properties": {}},
]}


@pytest.mark.asyncio
@respx.mock
async def test_cdse_search_builds_the_query_and_parses_scenes():
    route = respx.post(f"{STAC}/search").mock(return_value=httpx.Response(200, json=STAC_FEATURES))
    p = CdseProvider(None, None)  # catalogue search needs no credentials
    scenes = await p.search({"type": "Polygon", "coordinates": [[[-62.3, -10.9], [-62.2, -10.9], [-62.2, -10.8], [-62.3, -10.9]]]},
                            datetime(2024, 7, 1, tzinfo=timezone.utc), datetime(2024, 7, 31, tzinfo=timezone.utc), max_cloud_pct=20, limit=10)
    body = json.loads(route.calls[0].request.content)
    assert body["collections"] == ["sentinel-2-l2a"] and body["query"] == {"eo:cloud_cover": {"lte": 20}} and body["limit"] == 10
    assert body["datetime"] == "2024-07-01T00:00:00Z/2024-07-31T00:00:00Z" and "intersects" in body
    assert [s.product_id for s in scenes] == ["S2A_A", "S2A_B"]  # the item without a timestamp is dropped
    assert scenes[0].cloud_cover_pct == 3.2 and scenes[0].properties == {"view:sun_elevation": 51.6, "sat:relative_orbit": 53}
    assert scenes[1].cloud_cover_pct is None  # unknown cloud cover is reported as unknown, never as 0


@pytest.mark.asyncio
async def test_imagery_without_credentials_is_reported_not_faked():
    p = CdseProvider(None, None)
    with pytest.raises(ProviderNotConfigured):
        await p.process_geotiff(epsg=32720, bbox=(0, 0, 1, 1), width=10, height=10, acquired_at=datetime.now(timezone.utc))


@pytest.mark.asyncio
@respx.mock
async def test_process_api_reauthenticates_once_on_401_then_fails_clearly():
    respx.post(TOKEN).mock(return_value=token_ok())
    proc = respx.post(f"{SH}/api/v1/process").mock(return_value=httpx.Response(401, json={"error": {"message": "expired"}}))
    p = CdseProvider("sh-id", "secret")
    with pytest.raises(ProviderAuthError):
        await p.process_geotiff(epsg=32720, bbox=(0, 0, 100, 100), width=10, height=10, acquired_at=datetime(2024, 7, 3, 14, 27, tzinfo=timezone.utc))
    assert proc.call_count == 2  # original + one retry with a fresh token


def scene(pid, day, cc, cov=100.0):
    return SceneOut(product_id=pid, collection="sentinel-2-l2a", provider="cdse", acquired_at=datetime(2024, 7, day, tzinfo=timezone.utc),
                    cloud_cover_pct=cc, footprint=None, coverage_of_aoi_pct=cov)


def test_selection_rule_is_deterministic_and_documented():
    assert "95%" in SELECTION_RULE and "cloud" in SELECTION_RULE
    scenes = [scene("a", 2, 30), scene("b", 9, 4), scene("c", 15, 2), scene("d", 20, 1, cov=60)]
    assert select_scene(scenes, "before").product_id == "c"  # d has low coverage; b/c equal-cloud => latest for 'before'
    assert select_scene(scenes, "after").product_id == "b"  # ... earliest for 'after'
    assert select_scene([scene("x", 1, None), scene("y", 2, 50)], "after").product_id == "y"  # unknown cloud ranks worst
    assert select_scene([], "before") is None
    low = [scene("p", 3, 1, cov=40), scene("q", 4, 2, cov=70)]
    assert select_scene(low, "before").product_id in ("p", "q")  # nothing fully covers: best-covering pool is used


def test_plan_grid_is_metric_snapped_and_tiled():
    poly = {"type": "Polygon", "coordinates": [[[-62.32, -10.92], [-62.28, -10.92], [-62.28, -10.88], [-62.32, -10.88], [-62.32, -10.92]]]}
    g = plan_grid(poly, 10.0)
    assert g.epsg == 32720 and g.left % 10 == 0 and g.top % 10 == 0
    assert 430 < g.width < 460 and 430 < g.height < 460  # ~4.4 km at 10 m
    assert len(g.tiles()) == 1
    big = {"type": "Polygon", "coordinates": [[[-62.5, -11.1], [-62.0, -11.1], [-62.0, -10.6], [-62.5, -10.6], [-62.5, -11.1]]]}
    g2 = plan_grid(big, 10.0)
    assert g2.width > MAX_REQUEST_PX and len(g2.tiles()) == 9  # ~5.5 km... 55 km => 3 x 3 requests of <= 2000 px
    assert sum(w * h for _, _, w, h in g2.tiles()) == g2.width * g2.height  # tiles exactly cover the grid
    huge = {"type": "Polygon", "coordinates": [[[-65, -13], [-60, -13], [-60, -8], [-65, -8], [-65, -13]]]}
    with pytest.raises(GeoProcessingError) as err:
        plan_grid(huge, 10.0)
    assert err.value.code == "too_many_pixels" and "km" in str(err.value)


def fake_geotiff(epsg, bbox, w, h, bands=6, fill=None):
    arr = np.zeros((bands, h, w), np.uint16)
    arr[0:4] = 1000 if fill is None else fill
    if bands >= 6:
        arr[4] = 4  # SCL: vegetation
        arr[5] = 1  # dataMask
    with MemoryFile() as mf:
        with mf.open(driver="GTiff", width=w, height=h, count=bands, dtype="uint16", crs=f"EPSG:{epsg}", transform=from_bounds(*bbox, w, h)) as ds:
            ds.write(arr)
        return mf.read()


@pytest.mark.asyncio
@respx.mock
async def test_tiled_download_stitches_a_georeferenced_mosaic(tmp_path):
    respx.post(TOKEN).mock(return_value=token_ok())
    seen = []

    def process(request):
        body = json.loads(request.content)
        b = body["input"]["bounds"]
        epsg = int(b["properties"]["crs"].rsplit("/", 1)[1])
        w, h = body["output"]["width"], body["output"]["height"]
        seen.append((tuple(b["bbox"]), w, h, body["input"]["data"][0]["dataFilter"]["timeRange"]))
        assert request.headers["authorization"] == "Bearer tok-abc" and request.headers["accept"] == "image/tiff"
        return httpx.Response(200, content=fake_geotiff(epsg, b["bbox"], w, h, fill=len(seen) * 100))

    respx.post(f"{SH}/api/v1/process").mock(side_effect=process)
    poly = {"type": "Polygon", "coordinates": [[[-62.5, -11.1], [-62.0, -11.1], [-62.0, -10.6], [-62.5, -10.6], [-62.5, -11.1]]]}
    plan = plan_grid(poly, 10.0)
    p = CdseProvider("sh-id", "secret")
    dest = tmp_path / "scene.tif"
    meta = await download_scene(p, plan, datetime(2024, 7, 3, 14, 27, 19, tzinfo=timezone.utc), dest, tags={"role": "before"})
    assert meta["tiles"] == 9 and len(seen) == 9 and meta["valid_fraction"] == pytest.approx(1.0)
    # the request is restricted to the scene's own pass (+-3 h tolerates catalogue/tile timestamp skew), not a whole day
    assert seen[0][3] == {"from": "2024-07-03T11:27:19Z", "to": "2024-07-03T17:27:19Z"}
    import rasterio

    with rasterio.open(dest) as ds:
        assert ds.count == 6 and list(ds.descriptions) == BAND_DESCRIPTIONS
        assert ds.crs.to_epsg() == 32720 and ds.transform.a == 10.0 and (ds.width, ds.height) == (plan.width, plan.height)
        a = ds.read(1)
        assert a[0, 0] == 100 and a[-1, -1] == 900  # tile blocks landed in the right corners
        assert ds.tags()["role"] == "before"


@pytest.mark.asyncio
@respx.mock
async def test_malformed_provider_response_is_rejected(tmp_path):
    respx.post(TOKEN).mock(return_value=token_ok())
    respx.post(f"{SH}/api/v1/process").mock(side_effect=lambda r: httpx.Response(200, content=fake_geotiff(32720, (0, 0, 100, 100), 10, 10, bands=3)))
    poly = {"type": "Polygon", "coordinates": [[[-62.32, -10.92], [-62.31, -10.92], [-62.31, -10.91], [-62.32, -10.91], [-62.32, -10.92]]]}
    with pytest.raises(ProviderError) as err:
        await download_scene(CdseProvider("sh-id", "s"), plan_grid(poly, 10.0), datetime.now(timezone.utc), tmp_path / "x.tif", tags={})
    assert err.value.code == "provider_bad_response"


@pytest.mark.asyncio
@respx.mock
async def test_scene_with_no_data_over_the_aoi_is_an_error_not_an_empty_image(tmp_path):
    respx.post(TOKEN).mock(return_value=token_ok())

    def empty(request):
        body = json.loads(request.content)
        b = body["input"]["bounds"]
        w, h = body["output"]["width"], body["output"]["height"]
        with MemoryFile() as mf:
            with mf.open(driver="GTiff", width=w, height=h, count=6, dtype="uint16", crs="EPSG:32720", transform=from_bounds(*b["bbox"], w, h)) as ds:
                ds.write(np.zeros((6, h, w), np.uint16))
            return httpx.Response(200, content=mf.read())

    respx.post(f"{SH}/api/v1/process").mock(side_effect=empty)
    poly = {"type": "Polygon", "coordinates": [[[-62.32, -10.92], [-62.31, -10.92], [-62.31, -10.91], [-62.32, -10.91], [-62.32, -10.92]]]}
    with pytest.raises(ProviderError) as err:
        await download_scene(CdseProvider("sh-id", "s"), plan_grid(poly, 10.0), datetime.now(timezone.utc), tmp_path / "x.tif", tags={})
    assert err.value.code == "no_data_in_aoi"


def test_provider_selection_rules(monkeypatch):
    monkeypatch.setattr(settings, "SENTINEL_PROVIDER", "auto")
    monkeypatch.setattr(settings, "SENTINEL_HUB_CLIENT_ID", "sh-00000000-1111-2222-3333-444444444444")
    monkeypatch.setattr(settings, "SENTINEL_HUB_CLIENT_SECRET", "s")
    assert isinstance(build_provider(), CdseProvider) and build_provider().imagery_configured  # sh-<uuid> => CDSE client
    monkeypatch.setattr(settings, "SENTINEL_HUB_CLIENT_ID", "00000000-1111-2222-3333-444444444444")
    assert isinstance(build_provider(), SentinelHubProvider)  # plain UUID => commercial Sentinel Hub
    monkeypatch.setattr(settings, "SENTINEL_HUB_CLIENT_ID", None)
    p = build_provider()
    assert isinstance(p, CdseProvider) and not p.imagery_configured  # no credentials: public catalogue, no imagery
    monkeypatch.setattr(settings, "SENTINEL_PROVIDER", "none")
    assert build_provider() is None
    reset_provider_cache()


def test_blank_preview_detection():
    import io

    from PIL import Image

    from app.api.sentinel import _is_blank

    def png(alpha):
        buf = io.BytesIO()
        Image.new("RGBA", (8, 8), (10, 20, 30, alpha)).save(buf, "PNG")
        return buf.getvalue()

    assert _is_blank(png(0)) is True
    assert _is_blank(png(255)) is False
    assert _is_blank(b"not a png") is False


def test_scene_window_isolates_one_pass_but_tolerates_tile_time_skew():
    from datetime import datetime, timezone

    from app.providers.process_api import SCENE_WINDOW_S, time_range

    tr = time_range(datetime(2025, 1, 16, 5, 40, 59, tzinfo=timezone.utc), SCENE_WINDOW_S)
    assert tr == {"from": "2025-01-16T02:40:59Z", "to": "2025-01-16T08:40:59Z"}
