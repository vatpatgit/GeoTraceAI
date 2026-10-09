import json
from datetime import datetime, timezone

import httpx
import pytest
import respx
from shapely.geometry import shape

from app.providers import http as http_mod
from app.providers.base import ProviderAuthError, ProviderError, ProviderNotConfigured, ProviderRateLimited, ProviderUnavailable
from app.providers.openweather import AoiGeometryError, NormalizedAlert, OpenWeatherAlerts, normalize_response, prepare_location

URL = "https://api.openweathermap.org/alerts/1.0"
SQUARE = {"type": "Polygon", "coordinates": [[[10.0, 50.0], [10.5, 50.0], [10.5, 50.4], [10.0, 50.4], [10.0, 50.0]]]}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_):
        return None

    monkeypatch.setattr(http_mod.asyncio, "sleep", instant)


def payload(*alerts, date="2026-10-10T12:00:00+00:00"):
    return {"count": len(alerts), "items": [{"hour": 12, "date": date, "alerts": list(alerts)}]}


def alert(**over):
    base = {"alert_ID": "A1", "source": "government", "title": "Severe thunderstorm warning", "tag": "thunderstorm",
            "industry": {"industry_name": "general", "description": "Damaging winds possible", "severity": "severe"},
            "location": {"type": "polygon", "coordinates": [[[10.1, 50.1], [10.3, 50.1], [10.3, 50.3], [10.1, 50.3], [10.1, 50.1]]]},
            "certainty": "Likely", "urgency": "Expected"}
    base.update(over)
    return base


# ------------------------------------------------------------------------------------------------------------ AOI validation
def test_valid_polygon_is_accepted_and_reoriented_ccw():
    cw = {"type": "Polygon", "coordinates": [list(reversed(SQUARE["coordinates"][0]))]}
    loc = prepare_location(cw)
    ring = shape(loc).exterior
    assert loc["type"] == "Polygon" and ring.is_ccw
    assert shape(loc).equals(shape(SQUARE))  # same area, only the winding changed


@pytest.mark.parametrize("geom,msg", [
    ({"type": "Point", "coordinates": [10, 50]}, "Polygon AOI"),
    ({"type": "MultiPolygon", "coordinates": [SQUARE["coordinates"]]}, "MultiPolygon is not supported"),
    ({"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}, "invalid"),  # bow-tie
    ({"type": "Polygon", "coordinates": [[[179, 10], [181, 10], [181, 11], [179, 11], [179, 10]]]}, "Longitude"),
    ({"type": "Polygon", "coordinates": [[[10, 89], [11, 89], [11, 91], [10, 91], [10, 89]]]}, "latitude"),
    ({"type": "Nonsense"}, "not valid GeoJSON"),
    ({"type": "Polygon", "coordinates": []}, "empty|not valid"),
])
def test_invalid_geometry_is_rejected_before_any_request(geom, msg):
    import re

    with pytest.raises(AoiGeometryError) as e:
        prepare_location(geom)
    assert re.search(msg, str(e.value))


def test_limits_on_area_and_vertices():
    big = {"type": "Polygon", "coordinates": [[[0, 0], [40, 0], [40, 40], [0, 40], [0, 0]]]}
    with pytest.raises(AoiGeometryError, match="km2"):
        prepare_location(big, max_area_km2=1000)
    import math

    circle = {"type": "Polygon", "coordinates": [[[10 + 0.1 * math.cos(t / 100 * 2 * math.pi), 50 + 0.1 * math.sin(t / 100 * 2 * math.pi)] for t in range(100)] + [[10.1, 50.0]]]}
    with pytest.raises(AoiGeometryError, match="vertices"):
        prepare_location(circle, max_vertices=50)


# ------------------------------------------------------------------------------------------------------------ request building
def test_params_are_encoded_and_use_the_actual_aoi_not_the_doc_example():
    c = OpenWeatherAlerts(api_key="k-123")
    loc = prepare_location(SQUARE)
    p = c.build_params(loc, start=datetime(2026, 10, 10, 12, tzinfo=timezone.utc), end=datetime(2026, 10, 12, 12, tzinfo=timezone.utc),
                       source="government", tags=["flood", "wind"], severity="severe", certainty="likely", urgency="expected")
    assert p["appid"] == "k-123" and shape(json.loads(p["location"])).equals(shape(loc))
    assert " " not in p["location"]  # compact JSON
    assert p["tags"] == "flood,wind" and p["source"] == "government" and p["severity"] == "severe"
    assert p["start_date"] == "2026-10-10T12:00:00+00:00" and p["end_date"] == "2026-10-12T12:00:00+00:00"
    assert 10.0 in [pt[0] for pt in json.loads(p["location"])["coordinates"][0]]


def test_filters_are_validated_and_missing_key_is_a_clear_error():
    c = OpenWeatherAlerts(api_key="k")
    loc = prepare_location(SQUARE)
    for bad in ({"tags": ["snow,ice"]}, {"source": "other"}, {"severity": "catastrophic"}, {"urgency": "now"}):
        with pytest.raises(ValueError):
            c.build_params(loc, **bad)
    with pytest.raises(ProviderNotConfigured, match="OPENWEATHER_API_KEY"):
        OpenWeatherAlerts(api_key="").build_params(loc)


@respx.mock
async def test_request_url_carries_encoded_location_and_key():
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=payload(alert())))
    got = await OpenWeatherAlerts(api_key="secret-key").fetch(prepare_location(SQUARE))
    req = route.calls.last.request
    assert req.url.params["appid"] == "secret-key"
    assert shape(json.loads(req.url.params["location"])).equals(shape(SQUARE))
    assert len(got) == 1 and got[0].source_alert_id == "A1"


# ------------------------------------------------------------------------------------------------------------ responses & errors
@respx.mock
async def test_empty_results_are_valid_and_404_means_no_data():
    c = OpenWeatherAlerts(api_key="k")
    respx.get(URL).mock(return_value=httpx.Response(200, json={"count": 0, "items": []}))
    assert await c.fetch(prepare_location(SQUARE)) == []
    respx.get(URL).mock(return_value=httpx.Response(404, json={"code": 404, "message": "No data"}))
    assert await c.fetch(prepare_location(SQUARE)) == []


@respx.mock
@pytest.mark.parametrize("status,exc,text", [
    (401, ProviderAuthError, "plan does not include the Alerts product"),
    (429, ProviderRateLimited, "rate limit"),
    (500, ProviderUnavailable, "unavailable"),
    (400, ProviderError, "rejected the request"),
])
async def test_http_errors_map_to_clear_provider_errors(status, exc, text):
    respx.get(URL).mock(return_value=httpx.Response(status, json={"code": status, "message": "boom", "parameters": ["location"]}))
    with pytest.raises(exc) as e:
        await OpenWeatherAlerts(api_key="k").fetch(prepare_location(SQUARE))
    assert text in str(e.value)
    assert "k" != str(e.value)  # message never echoes the key


@respx.mock
async def test_timeouts_and_malformed_bodies():
    c = OpenWeatherAlerts(api_key="k")
    respx.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderUnavailable):
        await c.fetch(prepare_location(SQUARE))
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>not json</html>"))
    with pytest.raises(ProviderUnavailable, match="not valid JSON"):
        await c.fetch(prepare_location(SQUARE))
    respx.get(URL).mock(return_value=httpx.Response(200, json="a string"))
    with pytest.raises(ProviderUnavailable, match="unexpected response"):
        await c.fetch(prepare_location(SQUARE))


@respx.mock
async def test_transient_server_error_is_retried():
    route = respx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(200, json=payload(alert()))])
    got = await OpenWeatherAlerts(api_key="k").fetch(prepare_location(SQUARE))
    assert route.call_count == 2 and len(got) == 1


# ------------------------------------------------------------------------------------------------------------ normalisation
def test_normalisation_keeps_provider_fields_and_lowercases_enums():
    [a] = normalize_response(payload(alert()))
    assert (a.source_alert_id, a.source, a.title, a.tags) == ("A1", "government", "Severe thunderstorm warning", ["thunderstorm"])
    assert (a.severity, a.urgency, a.certainty) == ("severe", "expected", "likely")
    assert a.description == "Damaging winds possible"
    assert a.geometry["type"] == "Polygon" and a.industry[0]["industry_name"] == "general"
    assert a.start_time == datetime(2026, 10, 10, 12, tzinfo=timezone.utc) and a.end_time == datetime(2026, 10, 10, 13, tzinfo=timezone.utc)


def test_missing_optional_fields_become_unknown_not_invented():
    [a] = normalize_response({"items": [{"date": "2026-10-10T00:00:00+00:00", "alerts": [{"alert_ID": "X", "title": "t"}]}]})
    assert (a.severity, a.urgency, a.certainty) == ("unknown", "unknown", "unknown")
    assert a.description is None and a.geometry is None and a.tags == [] and a.source is None


def test_hourly_segments_of_one_alert_merge_into_a_time_span_with_max_severity():
    p = {"items": [
        {"date": "2026-10-10T12:00:00+00:00", "alerts": [alert(industry={"severity": "minor"})]},
        {"date": "2026-10-10T13:00:00+00:00", "alerts": [alert(industry={"severity": "severe"})]},
        {"date": "2026-10-10T14:00:00+00:00", "alerts": [alert(), {"alert_ID": "B2", "title": "Other", "tags": ["rain", "wind"]}]},
    ]}
    out = {a.source_alert_id: a for a in normalize_response(p)}
    assert set(out) == {"A1", "B2"}
    assert out["A1"].start_time.hour == 12 and out["A1"].end_time.hour == 15 and out["A1"].severity == "severe"
    assert out["B2"].tags == ["rain", "wind"]


def test_alternative_shapes_and_junk_are_tolerated():
    flat = alert(location={"type": "Polygon", "coordinates": [[10.1, 50.1], [10.3, 50.1], [10.3, 50.3], [10.1, 50.1]]})  # un-nested ring
    pt = alert(alert_ID="P", location={"type": "point", "coordinates": [10.2, 50.2]})
    assert {a.source_alert_id: a.geometry["type"] for a in normalize_response({"alerts": [flat, pt, "junk", 7, None]})} == {"A1": "Polygon", "P": "Point"}
    assert normalize_response([alert()])[0].source_alert_id == "A1"
    assert normalize_response({"items": "nope"}) == [] and normalize_response(None) == [] and normalize_response({}) == []
    bad_geo = normalize_response(payload(alert(location={"type": "polygon", "coordinates": "x"})))
    assert bad_geo[0].geometry is None  # unusable geometry is dropped, the alert itself is kept


def test_alert_without_id_gets_a_stable_synthetic_id():
    a1 = normalize_response(payload(alert(alert_ID=None)))[0]
    a2 = normalize_response(payload(alert(alert_ID=None)))[0]
    assert a1.id_synthesized and a1.source_alert_id == a2.source_alert_id and a1.source_alert_id.startswith("synth-")


def test_content_hash_changes_only_for_material_changes():
    base = normalize_response(payload(alert()))[0]
    same = normalize_response(payload(alert()))[0]
    assert base.content_hash() == same.content_hash()
    assert base.content_hash() != normalize_response(payload(alert(title="Warning upgraded")))[0].content_hash()
    assert base.content_hash() != normalize_response(payload(alert(industry={"severity": "extreme"})))[0].content_hash()
    assert isinstance(base, NormalizedAlert)
