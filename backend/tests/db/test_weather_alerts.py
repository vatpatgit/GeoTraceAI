import json

import httpx
import pytest
import respx
from shapely.geometry import shape

from app.config import settings
from app.providers import http as http_mod
from tests.db.conftest import auth, make_user

pytestmark = pytest.mark.asyncio
API = "/api/v1"
URL = "https://api.openweathermap.org/alerts/1.0"
BBOX = [10.0, 50.0, 10.5, 50.4]


@pytest.fixture(autouse=True)
def provider_key(monkeypatch):
    monkeypatch.setattr(settings, "OPENWEATHER_API_KEY", "test-key-not-real")
    monkeypatch.setattr(settings, "WEATHER_MIN_REFRESH_S", 300)

    async def instant(_):
        return None

    monkeypatch.setattr(http_mod.asyncio, "sleep", instant)


def alert(**over):
    base = {"alert_ID": "A1", "source": "government", "title": "Flood warning", "tag": "flood",
            "industry": {"industry_name": "general", "description": "River levels rising", "severity": "moderate"},
            "location": {"type": "polygon", "coordinates": [[[10.1, 50.1], [10.3, 50.1], [10.3, 50.3], [10.1, 50.3], [10.1, 50.1]]]},
            "certainty": "likely", "urgency": "expected"}
    base.update(over)
    return base


def body(*alerts):
    return {"count": len(alerts), "items": [{"hour": 12, "date": "2026-10-10T12:00:00+00:00", "alerts": list(alerts)}]}


async def setup(client, db, role="user"):
    user = await make_user(db, role)
    h = auth(user)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    aoi = (await client.post(f"{API}/projects/{proj['id']}/aois", headers=h, json={"name": "Elbe valley", "bbox": BBOX})).json()
    return user, h, proj, aoi


async def refresh(client, h, aoi, **kw):
    return await client.post(f"{API}/weather-alerts/refresh", headers=h, json={"aoi_id": aoi["id"], **kw})


@respx.mock
async def test_refresh_stores_normalised_alert_with_geometry_and_sends_the_real_aoi(client, db):
    _, h, _, aoi = await setup(client, db)
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=body(alert())))
    r = await refresh(client, h, aoi)
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["new"], out["updated"], out["unchanged"], out["total_active"], out["cached"]) == (1, 0, 0, 1, False)
    a = out["items"][0]
    assert (a["source_alert_id"], a["source"], a["title"], a["severity"], a["urgency"], a["certainty"], a["tags"]) == (
        "A1", "government", "Flood warning", "moderate", "expected", "likely", ["flood"])
    assert a["description"] == "River levels rising" and a["geometry"]["type"] == "Polygon" and a["aoi_name"] == "Elbe valley"
    assert a["start_time"].endswith("Z") and a["last_checked_at"]
    # the provider was called with THIS AOI's polygon (not a hardcoded example) and the key stays server-side
    sent = route.calls.last.request.url.params
    assert shape(json.loads(sent["location"])).bounds == pytest.approx(tuple(BBOX))
    assert sent["appid"] == "test-key-not-real" and "test-key-not-real" not in r.text


@respx.mock
async def test_unchanged_refresh_creates_no_duplicate_alert_or_notification(client, db):
    _, h, _, aoi = await setup(client, db)
    respx.get(URL).mock(return_value=httpx.Response(200, json=body(alert())))
    assert (await refresh(client, h, aoi)).json()["new"] == 1
    again = (await refresh(client, h, aoi, force=True)).json()
    assert (again["new"], again["updated"], again["unchanged"]) == (0, 0, 1)
    stored = (await client.get(f"{API}/weather-alerts", headers=h)).json()
    assert len(stored["items"]) == 1
    events = (await client.get(f"{API}/weather-alerts/events", headers=h)).json()
    assert len(events) == 1 and events[0]["kind"] == "new"  # still exactly one notification


@respx.mock
async def test_material_change_updates_the_alert_and_notifies_once(client, db):
    _, h, _, aoi = await setup(client, db)
    respx.get(URL).mock(return_value=httpx.Response(200, json=body(alert())))
    await refresh(client, h, aoi)
    respx.get(URL).mock(return_value=httpx.Response(200, json=body(alert(title="Flood warning (upgraded)", industry={"severity": "extreme"}))))
    up = (await refresh(client, h, aoi, force=True)).json()
    assert (up["new"], up["updated"]) == (0, 1)
    a = up["items"][0]
    assert a["severity"] == "extreme" and a["title"].endswith("(upgraded)") and a["change_count"] == 1
    events = (await client.get(f"{API}/weather-alerts/events", headers=h)).json()
    kinds = sorted(e["kind"] for e in events)
    assert kinds == ["new", "updated"]
    upd = next(e for e in events if e["kind"] == "updated")
    assert set(upd["changes"]) >= {"title", "severity"}
    # refreshing the SAME updated content again does not notify again
    await refresh(client, h, aoi, force=True)
    assert len((await client.get(f"{API}/weather-alerts/events", headers=h)).json()) == 2


@respx.mock
async def test_empty_result_is_valid_and_expires_previous_alerts_without_inventing_any(client, db):
    _, h, _, aoi = await setup(client, db)
    respx.get(URL).mock(return_value=httpx.Response(200, json=body(alert())))
    await refresh(client, h, aoi)
    respx.get(URL).mock(return_value=httpx.Response(200, json={"count": 0, "items": []}))
    r = (await refresh(client, h, aoi, force=True)).json()
    assert (r["total_active"], r["expired"], r["items"]) == (0, 1, [])
    listing = (await client.get(f"{API}/weather-alerts?status=active", headers=h)).json()
    assert listing["items"] == [] and listing["aois"][0]["alert_count"] == 0 and listing["aois"][0]["last_status"] == "ok"
    respx.get(URL).mock(return_value=httpx.Response(404, json={"code": 404, "message": "No data"}))  # documented 'no data' answer
    assert (await refresh(client, h, aoi, force=True)).status_code == 200


@respx.mock
async def test_missing_optional_fields_are_stored_as_unknown(client, db):
    _, h, _, aoi = await setup(client, db)
    respx.get(URL).mock(return_value=httpx.Response(200, json=body({"alert_ID": "Z9", "title": "Bare alert"})))
    a = (await refresh(client, h, aoi)).json()["items"][0]
    assert (a["severity"], a["urgency"], a["certainty"], a["description"], a["geometry"], a["tags"]) == ("unknown", "unknown", "unknown", None, None, [])


@respx.mock
async def test_provider_failures_surface_honestly_and_keep_stored_alerts(client, db):
    _, h, _, aoi = await setup(client, db)
    respx.get(URL).mock(return_value=httpx.Response(200, json=body(alert())))
    await refresh(client, h, aoi)
    for status, code in ((401, 502), (429, 429), (500, 502)):
        respx.get(URL).mock(return_value=httpx.Response(status, json={"code": status, "message": "x"}))
        r = await refresh(client, h, aoi, force=True)
        assert r.status_code == code, (status, r.text)
        assert r.json()["detail"]["message"]
    respx.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    assert (await refresh(client, h, aoi, force=True)).status_code == 504  # timeout -> gateway timeout
    listing = (await client.get(f"{API}/weather-alerts", headers=h)).json()
    assert len(listing["items"]) == 1 and listing["items"][0]["status"] == "active"  # a failed fetch never expires or deletes alerts
    assert listing["aois"][0]["last_status"] == "error" and listing["aois"][0]["last_error"]


@respx.mock
async def test_refresh_is_rate_guarded_unless_forced(client, db):
    _, h, _, aoi = await setup(client, db)
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=body(alert())))
    await refresh(client, h, aoi)
    cached = (await refresh(client, h, aoi)).json()
    assert cached["cached"] is True and route.call_count == 1 and cached["total_active"] == 1
    await refresh(client, h, aoi, force=True)
    assert route.call_count == 2


async def test_not_configured_returns_a_clear_error_and_no_alerts(client, db, monkeypatch):
    monkeypatch.setattr(settings, "OPENWEATHER_API_KEY", None)
    _, h, _, aoi = await setup(client, db)
    r = await refresh(client, h, aoi)
    assert r.status_code == 503 and "OPENWEATHER_API_KEY" in r.json()["detail"]["message"]
    assert (await client.get(f"{API}/weather-alerts/status", headers=h)).json()["configured"] is False
    listing = (await client.get(f"{API}/weather-alerts", headers=h)).json()
    assert listing["items"] == [] and listing["configured"] is False


@respx.mock
async def test_invalid_filters_and_oversized_aoi_are_rejected_before_calling_the_provider(client, db, monkeypatch):
    _, h, _, aoi = await setup(client, db)
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=body()))
    assert (await refresh(client, h, aoi, tags=["snow,ice"])).status_code == 422
    assert (await refresh(client, h, aoi, source="nope")).status_code == 422
    monkeypatch.setattr(settings, "WEATHER_MAX_AOI_KM2", 10.0)
    r = await refresh(client, h, aoi)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "bad_aoi"
    assert route.call_count == 0


@respx.mock
async def test_authorization(client, db):
    _, h, proj, aoi = await setup(client, db)
    respx.get(URL).mock(return_value=httpx.Response(200, json=body(alert())))
    await refresh(client, h, aoi)
    other = await make_user(db, "user")
    ho = auth(other)
    assert (await refresh(client, ho, aoi)).status_code == 404  # private project is invisible
    assert (await client.get(f"{API}/weather-alerts?aoi_id={aoi['id']}", headers=ho)).status_code == 404
    assert (await client.get(f"{API}/weather-alerts", headers=ho)).json()["items"] == []
    assert (await client.get(f"{API}/weather-alerts/events", headers=ho)).json() == []
    assert (await client.get(f"{API}/weather-alerts")).status_code == 401
    # a viewer on a shared project can read stored alerts but cannot trigger paid provider calls
    await client.patch(f"{API}/projects/{proj['id']}", headers=h, json={"visibility": "shared"})
    viewer = await make_user(db, "viewer")
    hv = auth(viewer)
    assert len((await client.get(f"{API}/weather-alerts", headers=hv)).json()["items"]) == 1
    assert (await refresh(client, hv, aoi, force=True)).status_code == 403


@respx.mock
async def test_events_can_be_marked_read(client, db):
    _, h, _, aoi = await setup(client, db)
    respx.get(URL).mock(return_value=httpx.Response(200, json=body(alert(), alert(alert_ID="A2", title="Wind"))))
    await refresh(client, h, aoi)
    unread = (await client.get(f"{API}/weather-alerts/events?unread=true", headers=h)).json()
    assert len(unread) == 2
    assert (await client.post(f"{API}/weather-alerts/events/read", headers=h, json={"ids": [unread[0]["id"]]})).json()["marked_read"] == 1
    assert len((await client.get(f"{API}/weather-alerts/events?unread=true", headers=h)).json()) == 1
    assert (await client.post(f"{API}/weather-alerts/events/read", headers=h, json={"all": True})).json()["marked_read"] == 1
    assert (await client.get(f"{API}/weather-alerts/events?unread=true", headers=h)).json() == []


@respx.mock
async def test_scheduled_refresh_only_touches_monitored_aois_and_never_renotifies(client, db):
    from app.jobs.weather_refresh import refresh_all_once

    _, h, proj, aoi = await setup(client, db)
    other_aoi = (await client.post(f"{API}/projects/{proj['id']}/aois", headers=h, json={"name": "Unmonitored", "bbox": [20, 40, 20.2, 40.2]})).json()
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=body(alert())))
    assert (await refresh_all_once())["aois"] == 0 and route.call_count == 0  # nothing monitored yet
    m = await client.patch(f"{API}/weather-alerts/aois/{aoi['id']}/monitoring", headers=h, json={"enabled": True})
    assert m.status_code == 200 and m.json()["monitoring"] is True
    s1 = await refresh_all_once()
    assert (s1["aois"], s1["new"]) == (1, 1) and route.call_count == 1
    # the guard keeps back-to-back cycles from re-calling the provider; even when forced the alert is unchanged => no new event
    s2 = await refresh_all_once()
    assert s2["new"] == 0 and s2["updated"] == 0 and route.call_count == 1
    events = (await client.get(f"{API}/weather-alerts/events", headers=h)).json()
    assert len(events) == 1
    ids = {a["aoi_id"] for a in (await client.get(f"{API}/weather-alerts", headers=h)).json()["items"]}
    assert ids == {aoi["id"]} and other_aoi["id"] not in ids
