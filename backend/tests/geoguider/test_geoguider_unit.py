"""GeoGuider units that need no database: periods, intent parsing/validation, pair ranking, workflow machine, tool registry guards."""
import uuid
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.analytics import llm
from app.geoguider import intent as intent_mod
from app.geoguider import pairs
from app.geoguider.intent import interpret, parse_rules
from app.geoguider.periods import resolve_period, sub_months
from app.geoguider.schemas import ChatRequest, Intent, WState, Workflow
from app.geoguider.tools import SearchIn, ToolContext, registry, split_windows
from app.geoguider.workflow import InvalidTransition, advance

TODAY = date(2026, 10, 10)


class Stub:
    def __init__(self, role="user"):
        self.id, self.role = uuid.uuid4(), role


# ------------------------------------------------------------------------------------------------- periods
@pytest.mark.parametrize(("text", "start", "end"), [
    ("changes in Mumbai over the past 10 years", date(2016, 10, 10), TODAY),
    ("the last five years", date(2021, 10, 10), TODAY),
    ("past 6 months", date(2026, 4, 10), TODAY),
    ("since March 2019", date(2019, 3, 1), TODAY),
    ("between March 2019 and June 2023", date(2019, 3, 1), date(2023, 6, 30)),
    ("in 2021", date(2021, 1, 1), date(2021, 12, 31)),
    ("last year", date(2025, 10, 10), TODAY),
])
def test_period_resolution_uses_today_not_hardcoded_dates(text, start, end):
    p = resolve_period(text, TODAY)
    assert (p.start, p.end) == (start, end)


def test_period_is_relative_to_the_supplied_today():
    assert resolve_period("past 10 years", date(2030, 2, 28)).start == date(2020, 2, 28)
    assert sub_months(date(2026, 3, 31), 1) == date(2026, 2, 28)


def test_no_period_and_future_end_are_handled():
    assert resolve_period("changes in Mumbai", TODAY) is None
    assert resolve_period("between 2024 and 2099", TODAY).end == TODAY


# ------------------------------------------------------------------------------------------------- intent
def test_mumbai_request_is_understood():
    i = parse_rules("Show me past 10 years changes in Mumbai.", TODAY)
    assert (i.intent_type, i.location_query, i.start_date) == ("change_analysis", "Mumbai", date(2016, 10, 10))


def test_missing_location_and_period_are_not_invented():
    i = parse_rules("Analyze changes.", TODAY)
    assert i.intent_type == "change_analysis" and i.location_query is None and i.start_date is None and not i.use_current_area


@pytest.mark.parametrize(("text", "kind"), [
    ("Open the satellite imagery page.", "navigate"), ("Show weather alerts for this AOI.", "weather_alerts"), ("Explain my latest analysis", "explain_results"),
    ("Export the current change-detection results.", "export_results"), ("What changed the most?", "ask_results"), ("run it", "confirm"), ("cancel", "cancel"),
    ("Find recent Sentinel-2 imagery for my selected AOI.", "find_imagery"), ("Compare two satellite images of this area.", "compare_dates"),
])
def test_supported_requests_map_to_intents(text, kind):
    assert parse_rules(text, TODAY).intent_type == kind


def test_trend_request_sets_trend_mode():
    assert parse_rules("Show a year-by-year change trend for Mumbai", TODAY).analysis_mode == "trend"


def test_navigation_is_limited_to_known_routes():
    with pytest.raises(ValidationError):
        Intent(intent_type="navigate", navigate_to="https://evil.example/phish")
    with pytest.raises(ValidationError):
        Intent(intent_type="navigate", navigate_to="javascript:alert(1)")
    assert parse_rules("Open the satellite imagery page", TODAY).navigate_to == "map"


def test_intent_validation_rejects_bad_values():
    with pytest.raises(ValidationError):
        Intent(start_date=date(2025, 1, 1), end_date=date(2024, 1, 1))
    with pytest.raises(ValidationError):
        Intent(cloud_cover_limit=300)
    with pytest.raises(ValidationError):
        Intent(intent_type="drop_database")
    assert Intent(location_query="Mum\x00bai\n").location_query == "Mum bai"


def test_chat_request_needs_content():
    with pytest.raises(ValidationError):
        ChatRequest()


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(llm, "llm_enabled", lambda: True)

    async def boom(*a, **k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(llm, "_complete", boom)
    i = await interpret("Show me changes in Paris over the past 3 years", TODAY, {})
    assert i.source == "rules" and i.location_query == "Paris"


@pytest.mark.asyncio
async def test_llm_output_is_validated_and_dates_are_recomputed(monkeypatch):
    monkeypatch.setattr(llm, "llm_enabled", lambda: True)

    async def fake(*a, **k):  # the model tries a wrong period and a hostile route
        return '{"intent_type":"change_analysis","location_query":"Paris","start_date":"2001-01-01","end_date":"2002-01-01","navigate_to":"http://evil"}'
    monkeypatch.setattr(llm, "_complete", fake)
    assert (await interpret("changes in Paris past 3 years", TODAY, {})).source == "rules"  # invalid route -> whole output rejected

    async def fake2(*a, **k):
        return '{"intent_type":"change_analysis","location_query":"Paris","start_date":"2001-01-01","end_date":"2002-01-01"}'
    monkeypatch.setattr(llm, "_complete", fake2)
    i = await interpret("changes in Paris past 3 years", TODAY, {})
    assert i.source == "llm" and i.start_date == date(2023, 10, 10)  # code, not the model, resolves the period


# ------------------------------------------------------------------------------------------------- pairs
def card(pid, when, cloud=1.0, cov=100.0):
    return {"product_id": pid, "acquired_at": when, "cloud_cover_pct": cloud, "coverage_of_aoi_pct": cov}


def test_pair_ranking_prefers_clear_full_coverage_same_season():
    b = [card("b1", "2017-03-01T05:00:00Z", 1), card("b2", "2017-09-01T05:00:00Z", 1), card("b3", "2017-03-05T05:00:00Z", 25)]
    a = [card("a1", "2025-03-03T05:00:00Z", 1), card("a2", "2025-03-04T05:00:00Z", 20, 60)]
    best = pairs.best_pairs(b, a, 3)
    assert (best[0][1]["product_id"], best[0][2]["product_id"]) == ("b1", "a1")
    assert len({(x[1]["product_id"]) for x in best}) == len(best)


def test_unusable_pairs_are_rejected():
    assert pairs.score_pair(card("a", "2025-01-02T00:00:00Z"), card("b", "2025-01-03T00:00:00Z")) is None  # < 3 days apart
    assert pairs.score_pair(card("a", "2024-01-01T00:00:00Z"), card("b", "2025-01-01T00:00:00Z", cov=20)) is None


def test_series_option_exists_only_for_multi_period_requests():
    wins = [{"scenes": [card(f"s{i}", f"{2017 + i}-03-01T05:00:00Z")]} for i in range(5)]
    assert not any(o["kind"] == "series" for o in pairs.build_options(wins, "two_date", 3))
    opts = pairs.build_options(wins, "trend", 3)
    series = next(o for o in opts if o["kind"] == "series")
    assert len(series["pairs"]) == 3 and opts[0]["recommended"] and opts[0]["id"] == "series"
    assert pairs.build_options(wins[:1], "two_date", 3) == []  # one sub-period cannot form a before/after


def test_position_description_is_computed():
    box = [72.8, 19.0, 73.0, 19.2]
    assert pairs.locate_in_bbox(72.9, 19.1, box) == "central part"
    assert pairs.locate_in_bbox(72.99, 19.19, box) == "north-eastern part"
    assert pairs.locate_in_bbox(72.81, 19.1, box) == "western part"


def test_split_windows_cover_the_period_without_overlap():
    w = split_windows(date(2016, 10, 10), date(2026, 10, 10), 11)
    assert w[0][0] == date(2016, 10, 10) and w[-1][1] == date(2026, 10, 10) and len(w) == 11
    assert all(a[1] < b[0] for a, b in zip(w, w[1:]))


# ------------------------------------------------------------------------------------------------- workflow machine
def test_workflow_transitions_are_validated():
    wf = Workflow()
    with pytest.raises(InvalidTransition):
        advance(wf, WState.ANALYZING)  # cannot jump from IDLE
    for s in (WState.INTENT_RESOLVED, WState.AOI_CONFIRMED, WState.SCENES_FOUND, WState.SCENES_SELECTED, WState.PREPROCESSING, WState.ANALYZING, WState.RESULTS_READY, WState.COMPLETED):
        advance(wf, s)
    with pytest.raises(InvalidTransition):
        advance(wf, WState.ANALYZING)


def test_failed_can_retry_but_cancelled_cannot_resume():
    wf = Workflow(state=WState.FAILED)
    advance(wf, WState.SCENES_SELECTED)
    with pytest.raises(InvalidTransition):
        advance(Workflow(state=WState.CANCELLED), WState.PREPROCESSING)


# ------------------------------------------------------------------------------------------------- registry guards
@pytest.mark.asyncio
async def test_unknown_tool_is_refused():
    ctx = ToolContext(None, Stub())
    r = await registry.call("rm_rf", {"path": "/"}, ctx)
    assert not r.ok and r.code == "unknown_tool"


@pytest.mark.asyncio
async def test_read_only_role_cannot_use_write_or_expensive_tools():
    ctx = ToolContext(None, Stub("viewer"))
    for name, args in (("create_or_update_aoi", {"name": "x", "bbox": [0, 0, 0.1, 0.1]}), ("run_change_detection", {"aoi_id": str(uuid.uuid4()), "pairs": []})):
        r = await registry.call(name, args, ctx)
        assert not r.ok and r.code == "forbidden"
    assert [t["permission"] for t in registry.describe() if t["name"] in ("run_change_detection",)] == ["expensive"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "args"), [
    ("search_satellite_scenes", {"bbox": [0, 0, 1, 1], "start": "2025-01-01", "end": "2024-01-01"}),
    ("search_satellite_scenes", {"bbox": [0, 0, 1, 1], "start": "2025-01-01", "end": "2999-01-01"}),
    ("search_satellite_scenes", {"bbox": [10, 0, 1, 1], "start": "2024-01-01", "end": "2025-01-01"}),
    ("search_satellite_scenes", {"bbox": [0, 0, 1, 1], "start": "2024-01-01", "end": "2025-01-01", "windows": 999}),
    ("resolve_location", {"query": "x"}), ("navigate_to_page", {"route": "https://evil.example"}), ("navigate_to_page", {"route": "map", "panel": "<script>"}),
    ("get_change_statistics", {"analysis_id": "not-a-uuid"}), ("get_detected_features", {"analysis_id": str(uuid.uuid4()), "n": 5000}),
])
async def test_tool_inputs_are_strictly_validated(name, args):
    r = await registry.call(name, args, ToolContext(None, Stub()))
    assert not r.ok and r.code == "invalid_input"


@pytest.mark.asyncio
async def test_navigation_tool_returns_only_allowed_keys():
    r = await registry.call("navigate_to_page", {"route": "map", "panel": "quick"}, ToolContext(None, Stub()))
    assert r.ok and r.data["route"] == "map"


def test_every_tool_documents_permission_and_has_a_timeout():
    for t in registry.describe():
        assert t["permission"] in ("read", "write", "expensive") and 0 < t["timeout_s"] <= 150 and t["description"]
    assert intent_mod.ROUTES  # route allow-list is the single source of truth for navigation


def test_search_window_validation_object():
    SearchIn(bbox=[0, 0, 1, 1], start=date(2020, 1, 1), end=datetime.now(timezone.utc).date())


@pytest.mark.asyncio
async def test_ollama_needs_a_model_not_a_key_and_is_called_natively(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    monkeypatch.setattr(settings, "LLM_MODEL", None)
    assert not llm.llm_enabled()
    monkeypatch.setattr(settings, "LLM_MODEL", "gemma4:26b")
    assert llm.llm_enabled()
    seen = {}

    class R:
        def raise_for_status(self): pass
        def json(self): return {"message": {"content": '{"intent_type":"help","reply":"I can search imagery."}'}}

    class C:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, **kw):
            seen["url"], seen["json"] = url, kw["json"]
            return R()

    monkeypatch.setattr(llm.httpx, "AsyncClient", C)
    i = await interpret("what are you able to do for me?", TODAY, {})
    assert i.source == "llm" and i.intent_type == "help"
    assert seen["url"].endswith("/api/chat") and seen["json"]["model"] == "gemma4:26b" and seen["json"]["think"] is False
