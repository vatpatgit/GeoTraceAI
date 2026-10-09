import io

import httpx
import pytest
import respx
from PIL import Image

from app.layers import registry
from tests.db.conftest import auth, make_user
from tests.db.test_api_workflow import _run_analysis

pytestmark = pytest.mark.asyncio
API = "/api/v1"

CAPS = """<?xml version="1.0"?><Capabilities xmlns="http://www.opengis.net/wmts/1.0" xmlns:ows="http://www.opengis.net/ows/1.1"><Contents>
<Layer><ows:Title>NDVI</ows:Title><ows:Identifier>MODIS_Terra_L3_NDVI_16Day</ows:Identifier><Format>image/png</Format>
<Dimension><ows:Identifier>time</ows:Identifier><Default>2026-09-14</Default><Value>2000-03-05/2026-09-14/P16D</Value></Dimension>
<TileMatrixSetLink><TileMatrixSet>GoogleMapsCompatible_Level9</TileMatrixSet></TileMatrixSetLink></Layer>
<Layer><ows:Title>IMERG</ows:Title><ows:Identifier>IMERG_Precipitation_Rate</ows:Identifier><Format>image/png</Format>
<Dimension><ows:Identifier>time</ows:Identifier><Default>2026-10-07</Default><Value>2000-06-01/2026-10-07/P1D</Value></Dimension>
<TileMatrixSetLink><TileMatrixSet>GoogleMapsCompatible_Level6</TileMatrixSet></TileMatrixSetLink></Layer>
</Contents></Capabilities>"""


def png():
    buf = io.BytesIO()
    Image.new("RGBA", (256, 256), (10, 200, 10, 120)).save(buf, "PNG")
    return buf.getvalue()


async def test_registry_covers_the_prd_layers_with_honest_metadata():
    ids = {d.id for d in registry.REGISTRY}
    assert {"ndvi", "temperature", "rainfall", "soil-moisture", "air-quality", "wildfire", "flood-risk", "deforestation"} <= ids
    for d in registry.REGISTRY:
        assert d.attribution and d.limitations and d.legend and d.group in ("environmental", "risk")
        assert d.requires_analysis or registry._tile_url(d)
    fire = registry.BY_ID["wildfire"]
    assert "risk" in " ".join(fire.limitations).lower() and fire.data_type == "observed"  # hotspot is not a forecast
    assert "air temperature" in " ".join(registry.BY_ID["temperature"].limitations)
    assert "CAMS" in " ".join(registry.BY_ID["air-quality"].limitations)  # we do not pretend to be CAMS
    assert "{bbox-epsg-3857}" in registry._tile_url(fire) and "{time}" in registry._tile_url(fire)


@respx.mock
async def test_refresh_marks_layers_by_real_probe_outcome(client, db, migrated_database):
    respx.get(registry.GIBS_CAPS).mock(return_value=httpx.Response(200, text=CAPS))
    respx.get(url__regex=r"https://gibs\.earthdata\.nasa\.gov/wmts/.*MODIS_Terra_L3_NDVI_16Day.*").mock(return_value=httpx.Response(200, content=png(), headers={"content-type": "image/png"}))
    respx.get(url__regex=r"https://gibs\.earthdata\.nasa\.gov/wmts/.*IMERG.*").mock(return_value=httpx.Response(404, text="nope"))
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(200, content=png(), headers={"content-type": "image/png"}))
    await registry.refresh_availability(probe=True)
    admin = await make_user(db, "viewer")
    layers = {l["id"]: l for l in (await client.get(f"{API}/layers", headers=auth(admin))).json()}
    assert layers["ndvi"]["availability"] == "available" and layers["ndvi"]["temporal"]["default_time"] == "2026-09-14"
    assert "GoogleMapsCompatible_Level9" in layers["ndvi"]["tile_url"] and "{time}" in layers["ndvi"]["tile_url"]
    assert layers["rainfall"]["availability"] == "unavailable" and "404" in layers["rainfall"]["availability_detail"]
    assert layers["ndvi-after"]["availability"] == "requires_analysis" and layers["ndvi-after"]["tile_url"] is None
    assert layers["wildfire"]["limitations"] and layers["wildfire"]["attribution"]
    assert (await client.get(f"{API}/layers")).status_code == 401


@respx.mock
async def test_offline_provider_never_claims_available(client, db, migrated_database):
    respx.get(url__regex=r".*").mock(side_effect=httpx.ConnectError("offline"))
    await registry.refresh_availability(probe=True)
    user = await make_user(db, "viewer")
    layers = {l["id"]: l for l in (await client.get(f"{API}/layers", headers=auth(user))).json()}
    assert all(l["availability"] in ("unavailable", "requires_analysis") for l in layers.values())
    assert "unreachable" in layers["ndvi"]["availability_detail"]


async def test_analysis_ndvi_tiles_are_rendered_from_the_imagery(client, db, synth):
    import math
    user = await make_user(db, "user")
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    a = await _run_analysis(client, h, proj["id"], synth)
    b = a["bounds"]
    lon, lat = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    z = 12
    x = int((lon + 180) / 360 * 2 ** z)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2 ** z)
    for layer in ("ndvi_before", "ndvi_after", "delta_ndvi"):
        r = await client.get(f"{API}/analyses/{a['id']}/tiles/{layer}/{z}/{x}/{y}.png", headers=h)
        img = Image.open(io.BytesIO(r.content))
        assert r.status_code == 200 and img.getchannel("A").getbbox() is not None, layer
    # vegetation shows green-dominant pixels, bare soil/water do not: the colour ramp is real NDVI, not a placeholder
    px = list(Image.open(io.BytesIO((await client.get(f"{API}/analyses/{a['id']}/tiles/ndvi_before/{z}/{x}/{y}.png", headers=h)).content)).convert("RGBA").getdata())
    opaque = [p for p in px if p[3] > 0]
    assert any(p[1] > p[0] and p[1] > p[2] for p in opaque) and any(p[0] > p[1] for p in opaque)
