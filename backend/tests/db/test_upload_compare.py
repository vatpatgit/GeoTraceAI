import io

import pytest
from PIL import Image
from shapely.geometry import shape, box

from app.ml.registry import learned_ready
from app.services.upload_compare import choose_model, grid_for
from tests.db.conftest import auth, make_user
from tests.db.test_api_workflow import upload

pytestmark = pytest.mark.asyncio
API = "/api/v1"


async def world(client, db, synth):
    user = await make_user(db, "user")
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    b = (await upload(client, h, proj["id"], synth.before, acquisition_date="2024-01-10T10:00:00Z")).json()
    a = (await upload(client, h, proj["id"], synth.after, acquisition_date="2024-06-20T10:00:00Z")).json()
    v = (await client.post(f"{API}/imagery/validate-pair", headers=h, json={"before_asset_id": b["id"], "after_asset_id": a["id"]})).json()
    return h, b, a, v["overlap"]["bounds_wgs84"]


async def test_grid_is_mercator_correct_and_rejects_bad_boxes():
    bounds, (w, h), px = grid_for((15.0, 40.6, 15.05, 40.64), 1000)
    assert w == 1000 and 1000 < h < 1100 and 3 < px < 8  # 0.04 deg of latitude is 0.04/cos(lat) in Mercator => height slightly > width
    from app.geo.errors import PairIncompatibleError

    for bad in ((1, 1, 0, 2), (-181, 0, 10, 10), (0, 84, 5, 86)):
        with pytest.raises(PairIncompatibleError):
            grid_for(bad, 512)


async def test_model_choice_follows_resolution():
    mid, reason = choose_model(20.0)
    if learned_ready("oscd-s2-v1"):
        assert mid == "oscd-s2-v1" and "fine-tuned on Sentinel-2" in reason
    mid, reason = choose_model(1.0)
    if learned_ready("idasiamnet-levir-v1"):
        assert mid == "idasiamnet-levir-v1" and "aerial" in reason
    elif learned_ready("levir-cd-v1"):
        assert mid == "levir-cd-v1" and "aerial" in reason
    assert choose_model(1.0, "x")[0] == "x"


async def test_render_returns_georeferenced_png_for_the_common_box(client, db, synth):
    h, b, a, bb = await world(client, db, synth)
    box_s = ",".join(str(v) for v in bb)
    r = await client.get(f"{API}/imagery/{b['id']}/render?bbox={box_s}&width=512", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    im = Image.open(io.BytesIO(r.content))
    assert im.size == tuple(int(x) for x in r.headers["x-image-size"].split("x"))
    alpha = im.convert("RGBA").getchannel("A")
    assert alpha.getextrema()[1] == 255  # real pixels over the overlap
    # both dates render onto the identical pixel grid, so they can be compared side by side
    r2 = await client.get(f"{API}/imagery/{a['id']}/render?bbox={box_s}&width=512", headers=h)
    assert Image.open(io.BytesIO(r2.content)).size == im.size
    # input validation + access control
    assert (await client.get(f"{API}/imagery/{b['id']}/render?bbox=1,2,3", headers=h)).status_code == 422
    other = await make_user(db, "user")
    assert (await client.get(f"{API}/imagery/{b['id']}/render?bbox={box_s}", headers=auth(other))).status_code == 404
    assert (await client.get(f"{API}/imagery/{b['id']}/render?bbox={box_s}")).status_code == 401


async def test_ml_changes_on_uploaded_pair_returns_geojson_inside_the_box(client, db, synth):
    if not (learned_ready("oscd-s2-v1") or learned_ready("levir-cd-v1")):
        pytest.skip("no trained model installed")
    h, b, a, bb = await world(client, db, synth)
    r = await client.post(f"{API}/imagery/ml-changes", headers=h, json={"before_asset_id": b["id"], "after_asset_id": a["id"], "bbox": bb, "width": 768})
    assert r.status_code == 200, r.text
    fc = r.json()
    m = fc["metadata"]
    assert fc["type"] == "FeatureCollection" and m["source"] == "uploaded GeoTIFFs" and m["model_choice_reason"]
    assert m["model_id"] and m["disclaimer"] and m["stats"]["analyzed_area_m2"] > 0
    region = box(*bb).buffer(0.001)
    for f in fc["features"]:
        g = shape(f["geometry"])
        assert g.is_valid and region.contains(g)  # polygons are georeferenced into the compared area
        assert f["properties"]["area_m2"] > 0
    # authorization: someone else's assets are invisible
    other = await make_user(db, "user")
    r2 = await client.post(f"{API}/imagery/ml-changes", headers=auth(other), json={"before_asset_id": b["id"], "after_asset_id": a["id"], "bbox": bb})
    assert r2.status_code == 404
    bad = await client.post(f"{API}/imagery/ml-changes", headers=h, json={"before_asset_id": b["id"], "after_asset_id": a["id"], "bbox": [1, 2, 0, 3]})
    assert bad.status_code == 422
