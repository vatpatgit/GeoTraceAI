"""The acceptance workflow (PRD §16): upload -> validate -> analyse -> polygons -> view -> export -> alert -> analytics."""
import io
import json
import sqlite3

import geopandas as gpd
import pyogrio
import pytest
from PIL import Image
from shapely.geometry import shape

from app.jobs.runner import drain
from tests.db.conftest import auth, make_user

pytestmark = pytest.mark.asyncio
API = "/api/v1"


async def upload(client, headers, project_id, path, **extra):
    with open(path, "rb") as fh:
        return await client.post(f"{API}/imagery/upload", headers=headers,
                                 files={"file": (path.name, fh, "image/tiff")}, data={"project_id": str(project_id), **extra})


@pytest.fixture
async def world(client, db, synth):
    """A user with a project, two uploaded assets and one completed analysis."""
    user = await make_user(db, "user")
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    rb = await upload(client, h, proj["id"], synth.before, acquisition_date="2024-01-10T10:00:00Z")
    ra = await upload(client, h, proj["id"], synth.after, acquisition_date="2024-06-20T10:00:00Z")
    assert rb.status_code == 201 and ra.status_code == 201, (rb.text, ra.text)
    before, after = rb.json(), ra.json()
    created = await client.post(f"{API}/analyses", headers=h, json={
        "project_id": proj["id"], "before_asset_id": before["id"], "after_asset_id": after["id"],
        "config": {"detection": {"method": "spectral_cva"}}})
    assert created.status_code == 202, created.text
    n = await drain()
    assert n == 1
    analysis = (await client.get(f"{API}/analyses/{created.json()['id']}", headers=h)).json()
    return {"user": user, "h": h, "project": proj, "before": before, "after": after, "analysis": analysis}


async def test_upload_reports_georeferencing_and_provenance(world):
    b = world["before"]
    assert b["crs_epsg"] == 32633 and (b["width"], b["height"], b["band_count"]) == (512, 512, 4)
    assert b["pixel_size_m"] == pytest.approx(10.0)
    assert b["band_map"] == {"blue": 1, "green": 2, "red": 3, "nir": 4} and b["band_map_confirmed"]
    assert b["acquisition_start"] == "2024-01-10T10:00:00Z"
    assert b["sha256"] and b["original_filename"] == "scene_before.tif"
    assert 14.99 < b["bounds"][0] < b["bounds"][2] < 15.1  # lon/lat footprint
    assert "storage_path" not in b and "path" not in json.dumps(b).lower().replace("filepath", "")  # no internal paths leak


async def test_analysis_completed_with_real_results(world):
    a = world["analysis"]
    assert a["status"] == "completed" and a["progress"] == 1.0 and a["data_origin"] == "live" and not a["is_demo"]
    assert a["summary"]["feature_count"] == 4
    assert a["method"] == "spectral_cva" and "user selected" in a["method_reason"]
    assert {"change_mask", "change_score", "before_aligned", "after_aligned", "valid_mask"} <= set(a["artifacts"])
    assert a["bounds"] and a["processing"]["grid"]["pixel_size_m"] == pytest.approx(10.0)
    assert a["processing"]["detection"]["confidence_kind"] is None  # baseline: no fabricated confidence
    assert a["before_date"] == "2024-01-10T10:00:00Z" and a["after_date"] == "2024-06-20T10:00:00Z"
    assert a["summary"]["total_changed_area_m2"] == pytest.approx(sum(f for f in a["summary"]["area_by_category_m2"].values()))


async def test_job_events_form_a_monotonic_timeline(client, world):
    ev = (await client.get(f"{API}/analyses/{world['analysis']['id']}/events", headers=world["h"])).json()
    statuses = [e["status"] for e in ev]
    assert statuses[0] == "queued" and statuses[-1] == "completed"
    assert {"validating", "preprocessing", "detecting_changes", "polygonizing", "evaluating_alerts"} <= set(statuses)
    prog = [e["progress"] for e in ev]
    assert prog == sorted(prog)


async def test_feature_queries_filter_sort_and_paginate_server_side(client, world):
    h, aid = world["h"], world["analysis"]["id"]
    page = (await client.get(f"{API}/analyses/{aid}/features?limit=2", headers=h)).json()
    assert page["total"] == 4 and len(page["items"]) == 2 and page["items"][0]["area_m2"] >= page["items"][1]["area_m2"]
    big = (await client.get(f"{API}/analyses/{aid}/features?min_area_m2=100000", headers=h)).json()
    assert big["total"] == 3
    crit = (await client.get(f"{API}/analyses/{aid}/features?severity=critical", headers=h)).json()
    assert crit["total"] >= 1 and all(f["severity"] == "critical" for f in crit["items"])
    veg = (await client.get(f"{API}/analyses/{aid}/features?category=vegetation_decrease", headers=h)).json()
    assert veg["total"] == 1 and veg["items"][0]["category_basis"] == "spectral_index"
    f0 = page["items"][0]
    assert f0["geometry"]["type"] in ("Polygon", "MultiPolygon") and len(f0["centroid"]) == 2
    minx, miny, maxx, maxy = f0["bbox"]
    inbox = (await client.get(f"{API}/analyses/{aid}/features?bbox={minx},{miny},{maxx},{maxy}", headers=h)).json()
    assert f0["id"] in {f["id"] for f in inbox["items"]}
    far = (await client.get(f"{API}/analyses/{aid}/features?bbox=100,10,101,11", headers=h)).json()
    assert far["total"] == 0
    gj = (await client.get(f"{API}/analyses/{aid}/features?format=geojson&limit=50", headers=h)).json()
    assert gj["type"] == "FeatureCollection" and gj["total"] == 4 and not gj["truncated"]
    one = (await client.get(f"{API}/analyses/{aid}/features/{f0['id']}", headers=h)).json()
    assert one["id"] == f0["id"] and one["severity_reasons"]


async def test_review_status_is_persisted_and_audited(client, world):
    h, aid = world["h"], world["analysis"]["id"]
    fid = (await client.get(f"{API}/analyses/{aid}/features?limit=1", headers=h)).json()["items"][0]["id"]
    r = await client.patch(f"{API}/analyses/{aid}/features/{fid}/review", headers=h, json={"review_status": "confirmed", "review_note": "checked on site imagery"})
    assert r.status_code == 200 and r.json()["review_status"] == "confirmed" and r.json()["review_note"] == "checked on site imagery"
    only = (await client.get(f"{API}/analyses/{aid}/features?review_status=confirmed", headers=h)).json()
    assert only["total"] == 1


async def test_geojson_export_is_valid_and_matches_stored_results(client, world):
    h, aid = world["h"], world["analysis"]["id"]
    r = await client.get(f"{API}/analyses/{aid}/export?format=geojson", headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/geo+json")
    assert r.headers["x-feature-count"] == "4" and "attachment" in r.headers["content-disposition"]
    fc = r.json()
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 4 and "crs" not in fc
    stored = (await client.get(f"{API}/analyses/{aid}/features?limit=10", headers=h)).json()["items"]
    by_id = {f["id"]: f for f in stored}
    for feat in fc["features"]:
        s = by_id[feat["id"]]
        assert feat["properties"]["area_m2"] == pytest.approx(s["area_m2"])
        assert shape(feat["geometry"]).is_valid
        assert feat["properties"]["before_date"].startswith("2024-01-10") and feat["properties"]["is_demo"] is False
    assert fc["metadata"]["data_origin"] == "live" and fc["metadata"]["feature_count"] == 4


async def test_filtered_and_selected_exports_contain_only_requested_features(client, world):
    h, aid = world["h"], world["analysis"]["id"]
    big = await client.get(f"{API}/analyses/{aid}/export?format=geojson&min_area_m2=100000", headers=h)
    assert len(big.json()["features"]) == 3 and big.json()["metadata"]["scope"] == "filtered"
    items = (await client.get(f"{API}/analyses/{aid}/features?limit=2", headers=h)).json()["items"]
    ids = [i["id"] for i in items]
    sel = await client.post(f"{API}/analyses/{aid}/export", headers=h, json={"format": "geojson", "filters": {"ids": ids}})
    assert {f["id"] for f in sel.json()["features"]} == set(ids) and sel.json()["metadata"]["scope"] == "selected"


async def test_geopackage_export_reopens_with_gis_libraries(client, world, tmp_path):
    h, aid = world["h"], world["analysis"]["id"]
    r = await client.get(f"{API}/analyses/{aid}/export?format=gpkg", headers=h)
    assert r.status_code == 200
    path = tmp_path / "x.gpkg"
    path.write_bytes(r.content)
    layers = {n for n, _ in pyogrio.list_layers(path)}
    assert {"change_features", "analysis_metadata", "source_imagery"} <= layers
    gdf = gpd.read_file(path, layer="change_features")
    assert len(gdf) == 4 and gdf.crs.to_epsg() == 4326 and gdf.geometry.is_valid.all()
    meta = gpd.read_file(path, layer="analysis_metadata")
    kv = dict(zip(meta["key"], meta["value"]))
    assert kv["analysis_id"] == aid and kv["method"] == "spectral_cva"
    imgs = gpd.read_file(path, layer="source_imagery")
    assert set(imgs["role"]) == {"before", "after"} and imgs["sha256"].notna().all()
    assert sqlite3.connect(path).execute("PRAGMA integrity_check").fetchone()[0] == "ok"


async def test_csv_export(client, world):
    r = await client.get(f"{API}/analyses/{world['analysis']['id']}/export?format=csv", headers=world["h"])
    lines = r.text.strip().splitlines()
    assert len(lines) == 5 and lines[0].startswith("feature_id,analysis_id,category")


async def test_tiles_render_and_are_georeferenced(client, world):
    h, aid = world["h"], world["analysis"]["id"]
    b = world["analysis"]["bounds"]
    # pick the tile containing the scene centre at zoom 12
    import math
    lon, lat = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    z = 12
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    for layer in ("before", "after", "mask", "score"):
        r = await client.get(f"{API}/analyses/{aid}/tiles/{layer}/{z}/{x}/{y}.png", headers=h)
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        img = Image.open(io.BytesIO(r.content))
        assert img.size == (256, 256)
        assert img.getchannel("A").getbbox() is not None, f"{layer} tile is empty"
    # far away tile => transparent
    r = await client.get(f"{API}/analyses/{aid}/tiles/before/{z}/{(x + 40) % n}/{y}.png", headers=h)
    assert Image.open(io.BytesIO(r.content)).getchannel("A").getbbox() is None
    assert (await client.get(f"{API}/analyses/{aid}/tiles/nope/{z}/{x}/{y}.png", headers=h)).status_code == 404
    assert (await client.get(f"{API}/analyses/{aid}/tiles/mask/{z}/{n + 5}/{y}.png", headers=h)).status_code == 404
    art = await client.get(f"{API}/analyses/{aid}/artifacts/change_mask", headers=h)
    assert art.status_code == 200 and art.content[:2] in (b"II", b"MM")


async def test_mask_tile_pixels_sit_on_the_feature(client, world):
    """The red mask pixels in a map tile must be where the polygon's centroid says they are."""
    import math
    import numpy as np
    h, aid = world["h"], world["analysis"]["id"]
    f = (await client.get(f"{API}/analyses/{aid}/features?limit=1", headers=h)).json()["items"][0]
    lon, lat = f["centroid"]
    z = 14
    n = 2 ** z
    xf = (lon + 180) / 360 * n
    yf = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    tx, ty = int(xf), int(yf)
    r = await client.get(f"{API}/analyses/{aid}/tiles/mask/{z}/{tx}/{ty}.png", headers=h)
    alpha = np.array(Image.open(io.BytesIO(r.content)).getchannel("A"))
    px, py = (xf - tx) * 256, (yf - ty) * 256
    assert alpha[int(py), int(px)] > 0  # the centroid pixel itself is painted as changed


async def test_alerts_are_generated_deduplicated_and_workflow_works(client, db, world):
    h, aid = world["h"], world["analysis"]["id"]
    rule = await client.post(f"{API}/alerts/rules", headers=h, json={
        "name": "Big changes", "min_area_m2": 100000, "min_severity": "high", "project_id": world["project"]["id"]})
    assert rule.status_code == 201, rule.text
    ev = await client.post(f"{API}/analyses/{aid}/evaluate-alerts", headers=h)
    assert ev.status_code == 200 and ev.json()["incidents_created"] >= 1
    first_total = ev.json()["incidents_created"]
    again = await client.post(f"{API}/analyses/{aid}/evaluate-alerts", headers=h)
    assert again.json()["incidents_created"] == 0  # retry-safe: no duplicates
    page = (await client.get(f"{API}/alerts", headers=h)).json()
    assert page["total"] == first_total and page["open"] == first_total
    inc = page["items"][0]
    assert inc["analysis_id"] == aid and inc["rule_name"] == "Big changes" and inc["area_m2"] >= 100000
    assert inc["evidence"]["rule"]["min_area_m2"] == 100000 and inc["evidence"]["matched"]["area_m2"] == pytest.approx(inc["area_m2"])
    assert len(inc["centroid"]) == 2 and len(inc["bbox"]) == 4
    ack = await client.patch(f"{API}/alerts/{inc['id']}", headers=h, json={"status": "acknowledged"})
    assert ack.json()["status"] == "acknowledged" and ack.json()["acknowledged_at"]
    res = await client.patch(f"{API}/alerts/{inc['id']}", headers=h, json={"status": "resolved", "resolution_note": "false positive"})
    assert res.json()["status"] == "resolved" and res.json()["resolution_note"] == "false positive"
    assert (await client.get(f"{API}/alerts?status=resolved", headers=h)).json()["total"] == 1
    assert (await client.get(f"{API}/alerts?severity=low", headers=h)).json()["total"] == 0
    stats = (await client.get(f"{API}/alerts/stats", headers=h)).json()
    assert stats["by_status"]["resolved"] == 1


async def test_rule_with_no_matching_feature_creates_nothing(client, world):
    h, aid = world["h"], world["analysis"]["id"]
    await client.post(f"{API}/alerts/rules", headers=h, json={"name": "Huge only", "min_area_m2": 50_000_000})
    ev = (await client.post(f"{API}/analyses/{aid}/evaluate-alerts", headers=h)).json()
    assert ev["incidents_created"] == 0 and ev["rules_evaluated"] == 1


# ------------------------------------------------------------------------------------------------ authorization
async def test_private_project_is_invisible_to_other_users_but_shared_is_readable(client, db, world):
    aid = world["analysis"]["id"]
    other = await make_user(db, "user")
    viewer = await make_user(db, "viewer")
    admin = await make_user(db, "admin")
    assert (await client.get(f"{API}/analyses/{aid}", headers=auth(other))).status_code == 404
    assert (await client.get(f"{API}/analyses/{aid}/features", headers=auth(other))).status_code == 404
    assert (await client.get(f"{API}/analyses/{aid}/export?format=geojson", headers=auth(other))).status_code == 404
    assert (await client.get(f"{API}/analyses/{aid}/tiles/before/5/1/1.png", headers=auth(other))).status_code == 404
    assert (await client.get(f"{API}/imagery/{world['before']['id']}", headers=auth(other))).status_code == 404
    assert (await client.get(f"{API}/analyses/{aid}", headers=auth(admin))).status_code == 200
    # share it: viewer can read but not write
    r = await client.patch(f"{API}/projects/{world['project']['id']}", headers=world["h"], json={"visibility": "shared"})
    assert r.status_code == 200
    assert (await client.get(f"{API}/analyses/{aid}", headers=auth(viewer))).status_code == 200
    assert (await client.get(f"{API}/analyses/{aid}/export?format=geojson", headers=auth(viewer))).status_code == 200
    assert (await client.post(f"{API}/analyses/{aid}/cancel", headers=auth(viewer))).status_code == 403
    assert (await client.delete(f"{API}/analyses/{aid}", headers=auth(viewer))).status_code == 403
    assert (await client.post(f"{API}/alerts/rules", headers=auth(viewer), json={"name": "x"})).status_code == 403
    assert (await client.patch(f"{API}/analyses/{aid}/features/{uuid_zero()}/review", headers=auth(viewer),
                               json={"review_status": "confirmed"})).status_code == 403
    # a non-owner user (write role) still cannot modify someone else's shared project
    assert (await client.delete(f"{API}/analyses/{aid}", headers=auth(other))).status_code == 403


def uuid_zero():
    return "00000000-0000-0000-0000-000000000000"


async def test_alert_rules_and_incidents_are_private_to_their_owner(client, db, world):
    h, aid = world["h"], world["analysis"]["id"]
    await client.post(f"{API}/alerts/rules", headers=h, json={"name": "mine", "min_area_m2": 1})
    await client.post(f"{API}/analyses/{aid}/evaluate-alerts", headers=h)
    other = await make_user(db, "user")
    assert (await client.get(f"{API}/alerts/rules", headers=auth(other))).json() == []
    assert (await client.get(f"{API}/alerts", headers=auth(other))).json()["total"] == 0
    inc = (await client.get(f"{API}/alerts", headers=h)).json()["items"][0]
    assert (await client.patch(f"{API}/alerts/{inc['id']}", headers=auth(other), json={"status": "acknowledged"})).status_code == 404


async def test_unauthenticated_requests_are_rejected(client, world):
    aid = world["analysis"]["id"]
    for path in (f"/analyses/{aid}", f"/analyses/{aid}/features", f"/analyses/{aid}/export?format=geojson", "/alerts", "/projects",
                 f"/imagery/{world['before']['id']}", f"/analyses/{aid}/tiles/before/1/0/0.png"):
        assert (await client.get(API + path)).status_code == 401, path


# ------------------------------------------------------------------------------------------------ validation & failure
async def test_non_tiff_content_is_rejected_even_with_tif_extension(client, db):
    user = await make_user(db, "user")
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    r = await client.post(f"{API}/imagery/upload", headers=h, data={"project_id": proj["id"]},
                          files={"file": ("evil.tif", io.BytesIO(b"<html><script>alert(1)</script></html>"), "image/tiff")})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "not_a_tiff"
    import os
    from app.config import settings
    assert not any((settings.STORAGE_DIR / "imagery").glob("*")) if (settings.STORAGE_DIR / "imagery").exists() else True  # nothing left behind


async def test_upload_size_limit_is_enforced(client, db, synth, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 0)  # any non-empty file is too large
    user = await make_user(db, "user")
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    r = await upload(client, h, proj["id"], synth.before)
    assert r.status_code == 413


async def test_path_traversal_filename_cannot_escape_storage(client, db, synth):
    user = await make_user(db, "user")
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    with open(synth.before, "rb") as fh:
        r = await client.post(f"{API}/imagery/upload", headers=h, data={"project_id": proj["id"]},
                              files={"file": ("../../../../etc/passwd.tif", fh, "image/tiff")})
    assert r.status_code == 201 and r.json()["original_filename"] == "passwd.tif"


async def test_reupload_of_identical_file_reuses_asset(client, db, synth):
    user = await make_user(db, "user")
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    a = await upload(client, h, proj["id"], synth.before)
    b = await upload(client, h, proj["id"], synth.before)
    assert a.status_code == 201 and b.status_code == 200 and a.json()["id"] == b.json()["id"]


async def test_incompatible_pair_is_rejected_with_explanations(client, db, synth, tmp_path):
    import numpy as np
    from rasterio.transform import Affine
    from app.geo.writers import write_geotiff
    user = await make_user(db, "user")
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    far = write_geotiff(tmp_path / "far.tif", np.ones((4, 128, 128), np.uint16), crs="EPSG:32633",
                        transform=Affine(10, 0, 900000, 0, -10, 4500000), descriptions=["blue", "green", "red", "nir"], build_overviews=False)
    a = (await upload(client, h, proj["id"], synth.before)).json()
    b = (await upload(client, h, proj["id"], far)).json()
    v = await client.post(f"{API}/imagery/validate-pair", headers=h, json={"before_asset_id": a["id"], "after_asset_id": b["id"]})
    assert v.status_code == 200 and v.json()["ok"] is False
    assert any(i["code"] in ("no_overlap", "insufficient_overlap") for i in v.json()["issues"])
    r = await client.post(f"{API}/analyses", headers=h, json={"project_id": proj["id"], "before_asset_id": a["id"], "after_asset_id": b["id"]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "incompatible_pair"


async def test_date_order_is_validated(client, db, synth):
    user = await make_user(db, "user")
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    a = (await upload(client, h, proj["id"], synth.before)).json()
    b = (await upload(client, h, proj["id"], synth.after)).json()
    r = await client.post(f"{API}/analyses", headers=h, json={
        "project_id": proj["id"], "before_asset_id": a["id"], "after_asset_id": b["id"],
        "before_date": "2024-06-01T00:00:00Z", "after_date": "2024-01-01T00:00:00Z"})
    assert r.status_code == 422


async def test_queued_analysis_can_be_cancelled_and_retried(client, db, synth):
    user = await make_user(db, "user")
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    a = (await upload(client, h, proj["id"], synth.before)).json()
    b = (await upload(client, h, proj["id"], synth.after)).json()
    job = (await client.post(f"{API}/analyses", headers=h, json={"project_id": proj["id"], "before_asset_id": a["id"], "after_asset_id": b["id"]})).json()
    c = await client.post(f"{API}/analyses/{job['id']}/cancel", headers=h)
    assert c.json()["status"] == "cancelled"
    assert (await drain()) == 0  # cancelled jobs are never picked up
    r = await client.post(f"{API}/analyses/{job['id']}/retry", headers=h)
    assert r.status_code == 202 and r.json()["status"] == "queued"
    assert (await drain()) == 1
    done = (await client.get(f"{API}/analyses/{job['id']}", headers=h)).json()
    assert done["status"] == "completed" and done["summary"]["feature_count"] == 4


async def test_failed_job_reports_a_clear_error_and_keeps_system_usable(client, db, synth, monkeypatch):
    import app.jobs.executor as ex
    user = await make_user(db, "user")
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    a = (await upload(client, h, proj["id"], synth.before)).json()
    b = (await upload(client, h, proj["id"], synth.after)).json()
    job = (await client.post(f"{API}/analyses", headers=h, json={"project_id": proj["id"], "before_asset_id": a["id"], "after_asset_id": b["id"],
                                                                 "config": {"preprocess": {"max_pixels": 1000}}})).json()
    await drain()
    failed = (await client.get(f"{API}/analyses/{job['id']}", headers=h)).json()
    assert failed["status"] == "failed" and failed["error"]["code"] == "too_many_pixels"
    assert "Reduce the area of interest" in failed["error"]["message"]
    # unexpected crash => generic message, no stack trace / internal paths leaked to the client
    def boom(*a, **k):
        raise RuntimeError("secret internal detail /var/lib/x")
    monkeypatch.setattr(ex, "run_pipeline", boom)
    job2 = (await client.post(f"{API}/analyses", headers=h, json={"project_id": proj["id"], "before_asset_id": a["id"], "after_asset_id": b["id"]})).json()
    await drain()
    crashed = (await client.get(f"{API}/analyses/{job2['id']}", headers=h)).json()
    assert crashed["status"] == "failed" and crashed["error"]["code"] == "internal_error"
    assert "secret internal detail" not in json.dumps(crashed)


async def test_health_and_ready_are_real(client, migrated_database):
    assert (await client.get("/health")).json()["status"] == "ok"
    r = await client.get("/ready")
    assert r.status_code == 200 and r.json()["checks"]["database"]["ok"] is True


# ------------------------------------------------------------------------------------------------ spatial integration
async def _scene_regions(db, synth):
    """A region covering the western half of the synthetic scene, and one far away."""
    from geoalchemy2.shape import from_shape
    from pyproj import Transformer
    from shapely.geometry import box
    from shapely.ops import transform
    from app.models import Region

    tr = Transformer.from_crs("EPSG:32633", "EPSG:4326", always_xy=True)
    west = transform(tr.transform, box(500000, 4500000 - 5120, 500000 + 2600, 4500000))
    far = box(100.0, 10.0, 100.1, 10.1)
    out = []
    for name, geom in (("West half", west), ("Far away", far)):
        r = Region(name=name, geometry=from_shape(geom, srid=4326), center_lat=0, center_lng=0, area_km2=1, risk_level="high")
        db.add(r)
        out.append(r)
    await db.commit()
    for r in out:
        await db.refresh(r)
    return out


async def _run_analysis(client, h, project_id, synth, name="a"):
    a = (await upload(client, h, project_id, synth.before)).json()
    b = (await upload(client, h, project_id, synth.after)).json()
    job = (await client.post(f"{API}/analyses", headers=h, json={"project_id": project_id, "before_asset_id": a["id"], "after_asset_id": b["id"], "name": name,
                                                                   "config": {"detection": {"method": "spectral_cva"}}})).json()
    await drain()
    return (await client.get(f"{API}/analyses/{job['id']}", headers=h)).json()


async def test_region_scoped_rules_proximity_and_aoi_filter(client, db, synth):
    user = await make_user(db, "user")
    h = auth(user)
    west, far = await _scene_regions(db, synth)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    analysis = await _run_analysis(client, h, proj["id"], synth)
    assert analysis["status"] == "completed", analysis.get("error")
    feats = (await client.get(f"{API}/analyses/{analysis['id']}/features?limit=10", headers=h)).json()["items"]
    # proximity was measured against the monitored regions known when the job ran
    assert all(f["distance_to_boundary_m"] is not None for f in feats)
    assert any(f["distance_to_boundary_m"] == 0 for f in feats)  # something lies inside the western half

    r_in = await client.post(f"{API}/alerts/rules", headers=h, json={"name": "inside west", "region_id": str(west.id), "min_area_m2": 1})
    r_far = await client.post(f"{API}/alerts/rules", headers=h, json={"name": "far", "region_id": str(far.id), "min_area_m2": 1})
    r_near = await client.post(f"{API}/alerts/rules", headers=h, json={"name": "near west", "region_id": str(west.id), "region_relation": "within_distance",
                                                                       "distance_m": 500, "min_area_m2": 1})
    assert r_in.status_code == r_far.status_code == r_near.status_code == 201, (r_in.text, r_far.text, r_near.text)
    ev = (await client.post(f"{API}/analyses/{analysis['id']}/evaluate-alerts", headers=h)).json()
    assert not ev["errors"], ev
    by_rule = {}
    for inc in (await client.get(f"{API}/alerts?limit=100", headers=h)).json()["items"]:
        by_rule.setdefault(inc["rule_name"], []).append(inc)
    inside = {f["id"] for f in feats if f["distance_to_boundary_m"] == 0}
    assert {i["feature_id"] for i in by_rule["inside west"]} == inside
    assert "far" not in by_rule  # nothing intersects the distant region
    near = {f["id"] for f in feats if f["distance_to_boundary_m"] <= 500}  # nearest boundary is the west region
    assert {i["feature_id"] for i in by_rule["near west"]} == near and near >= inside
    assert all(i["evidence"]["matched"]["scope"][0]["name"] == "West half" for i in by_rule["near west"])

    aoi = await client.post(f"{API}/projects/{proj['id']}/aois", headers=h, json={"name": "west", "bbox": list(west_bbox(feats))})
    assert aoi.status_code == 201, aoi.text
    got = (await client.get(f"{API}/analyses/{analysis['id']}/features?aoi_id={aoi.json()['id']}", headers=h)).json()
    assert 0 < got["total"] <= len(feats)


def west_bbox(feats):
    xs0 = min(f["bbox"][0] for f in feats); ys0 = min(f["bbox"][1] for f in feats)
    xs1 = min(f["bbox"][2] for f in feats) + 0.0005; ys1 = max(f["bbox"][3] for f in feats)
    return xs0 - 0.001, ys0 - 0.001, xs1, ys1 + 0.001


async def test_spatial_dedup_suppresses_re_alerts_for_the_same_change(client, db, synth):
    user = await make_user(db, "user")
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    first = await _run_analysis(client, h, proj["id"], synth, "first")
    await client.post(f"{API}/alerts/rules", headers=h, json={"name": "dedup", "min_area_m2": 1, "dedup_mode": "spatial"})
    await client.post(f"{API}/alerts/rules", headers=h, json={"name": "nodedup", "min_area_m2": 1, "dedup_mode": "none"})
    r1 = (await client.post(f"{API}/analyses/{first['id']}/evaluate-alerts", headers=h)).json()
    assert r1["incidents_created"] == 8 and r1["suppressed_duplicates"] == 0  # 4 features x 2 rules
    # a second analysis of the same area re-detects the same four changes
    from app.models import ImageryAsset  # new assets (different bytes) to avoid asset reuse
    second_pair_dir = synth.before.parent
    import numpy as np, rasterio
    with rasterio.open(synth.after) as src:
        data = src.read(); prof = src.profile; desc = src.descriptions
    data = np.clip(data.astype("int32") + 3, 0, 65535).astype(data.dtype)  # tiny radiometric nudge => different file
    p2 = second_pair_dir / "after_nudged.tif"
    with rasterio.open(p2, "w", **prof) as dst:
        dst.write(data)
        for i, d in enumerate(desc, 1):
            dst.set_band_description(i, d)
    a = (await upload(client, h, proj["id"], synth.before)).json()
    b = (await upload(client, h, proj["id"], p2)).json()
    job = (await client.post(f"{API}/analyses", headers=h, json={"project_id": proj["id"], "before_asset_id": a["id"], "after_asset_id": b["id"], "name": "second",
                                                                   "config": {"detection": {"method": "spectral_cva"}}})).json()
    await drain()
    second = (await client.get(f"{API}/analyses/{job['id']}", headers=h)).json()
    assert second["status"] == "completed"
    alerts = second["summary"]["alerts"]
    # the dedup rule stays quiet (same persistent changes); the non-dedup rule alerts again
    assert alerts["suppressed_duplicates"] == 4 and alerts["incidents_created"] == 4
    by_rule = {}
    for inc in (await client.get(f"{API}/alerts?limit=100", headers=h)).json()["items"]:
        by_rule.setdefault(inc["rule_name"], []).append(inc)
    assert len(by_rule["dedup"]) == 4 and len(by_rule["nodedup"]) == 8
