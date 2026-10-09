import io

import numpy as np
import pytest
from PIL import Image

from app.ml.registry import learned_ready
from tests.db.conftest import auth, make_user

pytestmark = pytest.mark.asyncio
API = "/api/v1"


def scene(w=480, h=360, changed=True, fmt="PNG", seed=3):
    """A textured 'aerial' scene; the after image gets a bright block added when ``changed``."""
    rng = np.random.default_rng(seed)
    base = np.clip(rng.normal(90, 12, (h, w, 3)), 0, 255).astype(np.uint8)
    base[:, : w // 2, 1] += 25
    if changed:
        base[h // 4: h // 2, w // 2: w // 2 + w // 5] = (235, 235, 230)
    buf = io.BytesIO()
    Image.fromarray(base).save(buf, fmt)
    return buf.getvalue()


def files(b, a, bname="before.png", aname="after.png"):
    return {"before": (bname, b, "application/octet-stream"), "after": (aname, a, "application/octet-stream")}


async def post(client, h, f, **data):
    return await client.post(f"{API}/imagery/plain-ml-changes", headers=h, files=f, data=data)


async def test_png_and_jpeg_pair_returns_changes_in_image_pixel_coordinates(client, db):
    if not (learned_ready("oscd-s2-v1") or learned_ready("levir-cd-v1")):
        pytest.skip("no trained model installed")
    h = auth(await make_user(db, "user"))
    r = await post(client, h, files(scene(changed=False, fmt="JPEG"), scene(changed=True, fmt="PNG"), "a.jpg", "b.png"))
    assert r.status_code == 200, r.text
    fc = r.json()
    m = fc["metadata"]
    assert m["source"].startswith("uploaded images") and m["image_size"] == [480, 360] and m["pixel_size_known"] is False
    assert any("share of the image" in w for w in m["warnings"]) and m["total_changed_area_m2"] is None
    assert m["model_id"] and m["model_choice_reason"] and m["disclaimer"]
    for f in fc["features"]:
        xs = [p[0] for ring in f["geometry"]["coordinates"] for p in ring]
        ys = [p[1] for ring in f["geometry"]["coordinates"] for p in ring]
        assert -2 <= min(xs) and max(xs) <= 482 and -2 <= min(ys) and max(ys) <= 362  # pixel coordinates inside the image frame
        assert f["properties"]["area_px"] > 0 and f["properties"]["area_m2"] is None


async def test_known_pixel_size_gives_square_metres(client, db):
    if not (learned_ready("oscd-s2-v1") or learned_ready("levir-cd-v1")):
        pytest.skip("no trained model installed")
    h = auth(await make_user(db, "user"))
    r = await post(client, h, files(scene(changed=False), scene(changed=True)), pixel_size_m="0.5")
    assert r.status_code == 200, r.text
    m = r.json()["metadata"]
    assert m["pixel_size_known"] is True and m["pixel_size_m"] == 0.5 and m["stats"]["analyzed_area_m2"] == pytest.approx(480 * 360 * 0.25)
    assert "levir" in m["model_id"]  # 0.5 m/px => aerial model
    for f in r.json()["features"]:
        assert f["properties"]["area_m2"] == pytest.approx(f["properties"]["area_px"] * 0.25, rel=0.15)


async def test_non_images_and_unsupported_formats_are_rejected_by_content(client, db):
    h = auth(await make_user(db, "user"))
    ok = scene()
    r = await post(client, h, files(b"MZ\x90\x00 not an image at all", ok, "evil.png", "after.png"))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "not_an_image"
    buf = io.BytesIO()
    Image.new("RGB", (64, 64)).save(buf, "TIFF")  # a plain TIFF is not handled here (browsers cannot show it; use a GeoTIFF)
    r = await post(client, h, files(buf.getvalue(), ok, "a.tif", "b.png"))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "unsupported_format"


async def test_mismatched_proportions_and_bad_parameters_are_rejected(client, db):
    h = auth(await make_user(db, "user"))
    r = await post(client, h, files(scene(480, 360), scene(300, 400)))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "size_mismatch"
    assert (await post(client, h, files(scene(), scene()), pixel_size_m="-1")).status_code == 422
    assert (await post(client, h, files(scene(), scene()), pixel_size_m="abc")).status_code == 422


async def test_requires_authentication(client, db):
    r = await client.post(f"{API}/imagery/plain-ml-changes", files=files(scene(), scene()))
    assert r.status_code == 401


async def test_slightly_different_sizes_are_aligned_with_a_notice(client, db):
    if not (learned_ready("oscd-s2-v1") or learned_ready("levir-cd-v1")):
        pytest.skip("no trained model installed")
    h = auth(await make_user(db, "user"))
    r = await post(client, h, files(scene(480, 360), scene(496, 372)))
    assert r.status_code == 200, r.text
    assert any("resized to match" in w for w in r.json()["metadata"]["warnings"])
