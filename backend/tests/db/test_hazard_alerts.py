"""Hazard alerts: feed parsing, AOI matching, dedup / expiry / re-notify, authorization. The upstream feed is MOCKED (sample payloads shaped like
the real responses observed on 2026-10-09); a live check against the real feed is documented in docs/HAZARD_ALERTS.md."""
from datetime import datetime, timedelta, timezone

import pytest
from geoalchemy2.shape import from_shape
from shapely.geometry import box

from app.config import settings
from app.models import AreaOfInterest, HazardAlert
from app.providers import hazards as feed
from app.providers.base import ProviderError
from app.providers.hazards import FeedResult, HazardEvent
from app.services import access
from app.services import hazards as svc
from tests.db.conftest import auth, make_user

pytestmark = pytest.mark.asyncio
API = "/api/v1/hazard-alerts"
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
MS = int(NOW.timestamp() * 1000)
POLY = box(-81.0, 7.5, -80.8, 7.7)  # near the Panama sequence seen in the live feed


def quake(i, lat, lon, mag, age_h=1.0):
    return {"id": f"us{i}", "lat": lat, "lng": lon, "depth": 10, "magnitude": mag, "place": "13 km W of Río Grande, Panama", "time": MS - int(age_h * 3600_000),
            "url": f"https://earthquake.usgs.gov/earthquakes/eventpage/us{i}", "tsunami": 0, "type": "earthquake", "felt": None, "alert": None}


# ------------------------------------------------------------------------------------------------- parsing
def test_millisecond_timestamps_and_hostile_fields_are_handled():
    rows = [quake(1, 7.6, -80.9, 5.1), {**quake(2, 7.6, -80.9, 5.0), "place": "x\x00\x1b[31m" + "A" * 500, "url": "javascript:alert(1)"},
            {"id": "bad", "lat": 99, "lng": 0, "magnitude": 5, "time": MS}, {"lat": 1, "lng": 1}, "garbage", None, {**quake(3, 7, -80, 5), "magnitude": "NaN"}]
    ev = feed.parse_earthquakes(rows)
    assert [e.external_id for e in ev] == ["us1", "us2"]
    assert ev[0].occurred_at.year == 2026 and ev[0].details["url"].startswith("https://earthquake.usgs.gov/")
    assert ev[1].details["url"] is None and "\x00" not in ev[1].title and len(ev[1].title) < 160  # untrusted text bounded and cleaned


def test_fire_and_storm_parsers_skip_unrecognised_records():
    fires = feed.parse_fires([{"lat": 7.6, "lng": -80.9, "brightness": 300, "confidence": "nominal", "date": "2026-10-08", "time": "0828", "frp": 12.5}, {"lat": 7, "lng": 1, "date": "bad"}])
    assert len(fires) == 1 and fires[0].occurred_at == datetime(2026, 10, 8, 8, 28, tzinfo=timezone.utc)
    storms = feed.parse_storms([{"id": "eonet-1", "title": "Hurricane X", "severity": "high", "lat": 15.9, "lng": -104.5, "date": "2026-10-09T12:00:00Z", "source": "http://insecure", "provider": "NASA EONET"},
                                {"title": "no id", "lat": 1, "lng": 1}])
    assert len(storms) == 1 and storms[0].details["source_url"] is None


# ------------------------------------------------------------------------------------------------- matching
def test_matching_thresholds_distance_and_age(monkeypatch):
    monkeypatch.setattr(settings, "HAZARD_QUAKE_MIN_MAG", 4.0)
    monkeypatch.setattr(settings, "HAZARD_QUAKE_RADIUS_KM", 100.0)
    events = {"earthquake": feed.parse_earthquakes([quake(1, 7.6, -80.9, 5.0), quake(2, 7.6, -80.9, 3.5), quake(3, 12.0, -80.9, 6.0), quake(4, 7.6, -80.9, 5.5, age_h=100)])}
    got = svc.match_aoi(POLY, events, NOW)
    assert [c.external_id for c in got] == ["us1"]  # too weak, too far and too old are all excluded
    assert got[0].distance_km == 0.0 and got[0].severity == "medium"
    assert svc.quake_severity(7.0) == "critical" and svc.quake_severity(6.0) == "high" and svc.quake_severity(4.2) == "low"


def test_fire_hotspots_are_aggregated_per_day_and_low_confidence_dropped(monkeypatch):
    monkeypatch.setattr(settings, "HAZARD_FIRE_RADIUS_KM", 25.0)
    rows = [{"lat": 7.6 + i * 0.001, "lng": -80.9, "confidence": "nominal", "date": "2026-10-09", "time": "0100", "frp": 5.0 + i} for i in range(12)]
    rows += [{"lat": 7.6, "lng": -80.9, "confidence": "low", "date": "2026-10-09", "time": "0100", "frp": 99}, {"lat": 40, "lng": 10, "confidence": "high", "date": "2026-10-09", "time": "0100", "frp": 9}]
    got = svc.match_aoi(POLY, {"fire": feed.parse_fires(rows)}, NOW)
    assert len(got) == 1 and got[0].details["hotspots"] == 12 and got[0].severity == "medium" and got[0].external_id == "fires-2026-10-09"


def test_distance_is_geodesic_to_the_nearest_aoi_edge():
    d = svc.distance_to_aoi_km(POLY, 7.6, -80.7)  # 0.1 deg east of the AOI at ~7.6N
    assert 10.5 < d < 11.5
    assert svc.distance_to_aoi_km(POLY, 7.6, -80.9) == 0.0


# ------------------------------------------------------------------------------------------------- persistence
async def make_aoi(db, user):
    project = await access.default_project(db, user)
    row = AreaOfInterest(project_id=project.id, name="Panama test", geometry=from_shape(POLY, srid=4326), area_km2=490.0, source="drawn")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def result(quakes=None, errors=None):
    return FeedResult(events={"earthquake": feed.parse_earthquakes(quakes or [])} | ({} if errors else {}), errors=errors or {})


async def test_reconcile_dedups_updates_expires_and_renotifies(db):
    user = await make_user(db)
    aoi = await make_aoi(db, user)
    s1 = await svc.reconcile(db, [aoi], result([quake(1, 7.6, -80.9, 5.0)]), NOW)
    assert (s1.new, s1.updated, s1.expired) == (1, 0, 0)
    row = (await db.execute(HazardAlert.__table__.select())).first()
    s2 = await svc.reconcile(db, [aoi], result([quake(1, 7.6, -80.9, 5.0)]), NOW)
    assert (s2.new, s2.updated) == (0, 0)  # unchanged re-fetch creates nothing
    await db.execute(HazardAlert.__table__.update().values(read_at=NOW))
    await db.commit()
    s3 = await svc.reconcile(db, [aoi], result([quake(1, 7.6, -80.9, 6.2)]), NOW)  # revised upwards
    assert s3.updated == 1
    h = (await db.execute(__import__("sqlalchemy").select(HazardAlert))).scalars().one()
    assert h.severity == "high" and h.read_at is None  # worse -> unread again
    s4 = await svc.reconcile(db, [aoi], result([]), NOW + timedelta(minutes=5))
    assert s4.expired == 1 and row is not None
    h = (await db.execute(__import__("sqlalchemy").select(HazardAlert))).scalars().one()
    await db.refresh(h)
    assert h.status == "expired"


async def test_a_failed_feed_kind_never_expires_existing_alerts(db):
    user = await make_user(db)
    aoi = await make_aoi(db, user)
    await svc.reconcile(db, [aoi], result([quake(1, 7.6, -80.9, 5.0)]), NOW)
    failed = FeedResult(events={}, errors={"earthquake": "feed down"})  # unknown is not the same as gone
    s = await svc.reconcile(db, [aoi], failed, NOW + timedelta(minutes=5))
    assert s.expired == 0 and s.errors == {"earthquake": "feed down"}


# ------------------------------------------------------------------------------------------------- API
@pytest.fixture
def fake_feed(monkeypatch):
    calls = {"n": 0}

    async def fetch(kinds=feed.KINDS):
        calls["n"] += 1
        return FeedResult(events={"earthquake": feed.parse_earthquakes([quake(1, 7.6, -80.9, 5.0, age_h=0.1)]), "fire": [], "storm": []})
    monkeypatch.setattr("app.services.hazards.feed.fetch_feed", fetch)
    svc._cache.update(at=0.0, result=None)
    return calls


async def test_refresh_list_read_and_isolation(client, db, fake_feed):
    a, b = await make_user(db), await make_user(db)
    await make_aoi(db, a)
    r = await client.post(f"{API}/refresh", headers=auth(a), json={})
    assert r.status_code == 200 and r.json()["new"] == 1 and r.json()["errors"] == {}
    again = await client.post(f"{API}/refresh", headers=auth(a), json={})
    assert again.json()["cached"] is True and fake_feed["n"] == 1  # one upstream fetch serves repeated requests
    items = (await client.get(API, headers=auth(a))).json()
    assert len(items) == 1 and items[0]["kind"] == "earthquake" and items[0]["aoi_name"] == "Panama test" and items[0]["read_at"] is None
    assert (await client.get(API, headers=auth(b))).json() == []  # another user's AOIs are invisible
    assert (await client.post(f"{API}/read", headers=auth(b), json={"all": True})).json()["marked_read"] == 0
    assert (await client.post(f"{API}/read", headers=auth(a), json={"ids": [items[0]["id"]]})).json()["marked_read"] == 1
    assert (await client.get(API, headers=auth(a), params={"unread": True})).json() == []
    assert (await client.get(API, headers=auth(a), params={"kind": "bogus"})).status_code == 422


async def test_feed_outage_is_reported_not_hidden(client, db, monkeypatch):
    user = await make_user(db)
    await make_aoi(db, user)
    svc._cache.update(at=0.0, result=None)

    async def boom(kinds=feed.KINDS):
        raise ProviderError("The live hazard feed is unreachable: timeout", code="feed_unavailable", status=502)
    monkeypatch.setattr("app.services.hazards.feed.fetch_feed", boom)
    r = await client.post(f"{API}/refresh", headers=auth(user), json={})
    assert r.status_code == 502 and "unreachable" in r.json()["detail"]["message"]


async def test_requires_auth_and_status_lists_unsupported_kinds(client, db):
    assert (await client.get(API)).status_code == 401
    user = await make_user(db)
    s = (await client.get(f"{API}/status", headers=auth(user))).json()
    assert "air_quality" in s["not_supported"] and s["kinds"]["fire"]["note"].startswith("satellite thermal anomalies")
