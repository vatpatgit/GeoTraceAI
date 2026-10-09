import csv
import io
import json

import pytest

from app.analytics import llm
from app.analytics.nl import parse_question
from tests.db.conftest import auth, make_user
from tests.db.test_api_workflow import _run_analysis, _scene_regions

pytestmark = pytest.mark.asyncio
API = "/api/v1"


async def ask(client, h, question=None, **kw):
    r = await client.post(f"{API}/analytics/query", headers=h, json={"question": question, **kw})
    return r


@pytest.fixture
async def done(client, db, synth):
    user = await make_user(db, "user")
    h = auth(user)
    await _scene_regions(db, synth)
    proj = (await client.post(f"{API}/projects/default", headers=h)).json()
    analysis = await _run_analysis(client, h, proj["id"], synth, name="first")
    assert analysis["status"] == "completed", analysis.get("error")
    feats = (await client.get(f"{API}/analyses/{analysis['id']}/features?limit=100", headers=h)).json()["items"]
    return {"user": user, "h": h, "project": proj, "analysis": analysis, "features": feats}


async def test_parser_maps_questions_to_approved_operations_only():
    cases = {
        "Which are the 5 largest changes?": ("largest_changes", 5),
        "Compare this analysis with the previous run": ("compare_analyses", None),
        "Which detections require human review?": ("needs_review", None),
        "How much vegetation changed?": ("vegetation_summary", None),
        "Which high-severity detections are within 1 km of a monitored boundary?": ("near_boundary", None),
        "What changed between the selected dates?": ("summarize_analysis", None),
    }
    for q, (op, n) in cases.items():
        spec, _ = parse_question(q, [])
        assert spec is not None and spec.operation == op, (q, spec)
        if n:
            assert spec.n == n
    near, _ = parse_question("Which high-severity detections are within 1 km of a monitored boundary?", [])
    assert near.distance_m == 1000 and near.min_severity == "high"
    spec, _ = parse_question("Write me a poem about satellites", [])
    assert spec is None
    spec, _ = parse_question("DROP TABLE users; -- largest changes", [])  # text never becomes SQL; at most an approved operation
    assert spec is None or spec.operation == "largest_changes"


async def test_numbers_grounded_rejects_invented_figures():
    facts = "4 polygons covering 12,345 m2; largest is 6,000 m2"
    assert llm.numbers_grounded("Four polygons cover about 12,345 m2.", facts)
    assert llm.numbers_grounded("The largest is 6000 m2 of 12345 m2.", facts)
    assert not llm.numbers_grounded("About 98,000 m2 changed.", facts)
    assert not llm.numbers_grounded("The area grew by 37.5 percent.", facts)


async def test_summary_matches_stored_results(client, done):
    r = await ask(client, done["h"], "What changed between the selected dates?")
    assert r.status_code == 200, r.text
    body = r.json()
    a = done["analysis"]
    assert body["understood"] and body["operation"] == "summarize_analysis" and body["answer_source"] == "deterministic"
    assert body["data"]["feature_count"] == a["summary"]["feature_count"] == len(done["features"])
    assert body["data"]["total_changed_area_m2"] == pytest.approx(a["summary"]["total_changed_area_m2"])
    assert body["measured_facts"] and any(ref["kind"] == "feature" for ref in body["references"])


async def test_largest_changes_are_ordered_by_stored_area(client, done):
    body = (await ask(client, done["h"], "Which are the 3 largest changes?")).json()
    ids = [ref["id"] for ref in body["references"] if ref["kind"] == "feature"]
    expected = [f["id"] for f in sorted(done["features"], key=lambda f: -f["area_m2"])[:3]]
    assert ids == expected
    assert all(ref["centroid"] and len(ref["centroid"]) == 2 for ref in body["references"] if ref["kind"] == "feature")


async def test_unsupported_question_is_not_answered_with_made_up_content(client, done):
    body = (await ask(client, done["h"], "Will it rain in Paris tomorrow?")).json()
    assert body["understood"] is False and body["operation"] == "none" and body["suggestions"]
    assert body["measured_facts"] == [] and body["references"] == []


async def test_comparison_and_history_are_honest_without_history(client, done):
    body = (await ask(client, done["h"], "Compare this analysis with the previous run")).json()
    assert body["understood"] and body["data"] == {} and "no earlier" in body["answer"].lower()
    hist = (await ask(client, done["h"], "Show the history over time", project_id=done["project"]["id"])).json()
    assert hist["operation"] == "history"
    assert "trend" in " ".join(hist["caveats"] + [hist["answer"]]).lower() or len(hist["data"].get("points", [])) < 2


async def test_comparison_with_a_previous_analysis(client, db, synth, done):
    second = await _run_analysis(client, done["h"], done["project"]["id"], synth, name="second")
    assert second["status"] == "completed"
    body = (await ask(client, done["h"], "Compare this analysis with the previous run", analysis_id=second["id"])).json()
    assert body["understood"] and body["data"], body
    assert body["measured_facts"]
    assert {ref["analysis_id"] or ref["id"] for ref in body["references"] if ref["kind"] == "analysis"} <= {second["id"], done["analysis"]["id"]}


async def test_near_boundary_uses_stored_distances(client, done):
    body = (await ask(client, done["h"], "Which high-severity detections are within 100 km of a monitored boundary?")).json()
    assert body["understood"] and body["operation"] == "near_boundary"
    stored = {f["id"] for f in done["features"] if f["distance_to_boundary_m"] is not None and f["distance_to_boundary_m"] <= 100_000 and f["severity"] in ("high", "critical")}
    got = {ref["id"] for ref in body["references"] if ref["kind"] == "feature"}
    assert got == stored


async def test_structured_spec_and_bad_spec(client, done):
    fid = done["features"][0]["id"]
    ok = await client.post(f"{API}/analytics/query", headers=done["h"], json={"spec": {"operation": "explain_feature", "feature_id": fid}, "analysis_id": done["analysis"]["id"]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["measured_facts"]
    bad = await client.post(f"{API}/analytics/query", headers=done["h"], json={"spec": {"operation": "drop_everything"}})
    assert bad.status_code == 422
    empty = await client.post(f"{API}/analytics/query", headers=done["h"], json={})
    assert empty.status_code == 422


async def test_ungrounded_llm_narration_is_discarded(client, done, monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config.settings, "LLM_API_KEY", "test-key")

    async def invented(system, user, max_tokens=500):
        return "A huge 987,654 m2 area of forest was lost, up 41.7 percent."

    monkeypatch.setattr(llm, "_complete", invented)
    body = (await ask(client, done["h"], "What changed between the selected dates?")).json()
    assert body["answer_source"] == "deterministic" and "987,654" not in body["answer"]


async def test_grounded_llm_narration_is_used(client, done, monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config.settings, "LLM_API_KEY", "test-key")

    async def grounded(system, user, max_tokens=500):
        payload = json.loads(user)
        return "Summary of stored results: " + payload["headline"]

    monkeypatch.setattr(llm, "_complete", grounded)
    body = (await ask(client, done["h"], "What changed between the selected dates?")).json()
    assert body["answer_source"] == "llm_narration"
    assert body["measured_facts"]  # deterministic facts always accompany prose
    off = (await ask(client, done["h"], "What changed between the selected dates?", narrate=False)).json()
    assert off["answer_source"] == "deterministic"


async def test_llm_failure_degrades_to_deterministic(client, done, monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(config.settings, "LLM_API_KEY", "test-key")

    async def boom(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(llm, "_complete", boom)
    r = await ask(client, done["h"], "What changed between the selected dates?")
    assert r.status_code == 200 and r.json()["answer_source"] == "deterministic"


async def test_analytics_respect_project_privacy(client, db, done):
    other = await make_user(db, "user")
    r = await client.post(f"{API}/analytics/query", headers=auth(other), json={"question": "summarize", "analysis_id": done["analysis"]["id"]})
    assert r.status_code == 404
    r = await client.post(f"{API}/analytics/query", headers=auth(other), json={"question": "What changed?"})
    assert r.status_code == 404  # nothing readable for this user -> no answer rather than someone else's data
    assert (await client.get(f"{API}/reports/analyses/{done['analysis']['id']}", headers=auth(other))).status_code == 404
    assert (await client.post(f"{API}/analytics/query", json={"question": "x"})).status_code == 401


async def test_overview_counts_only_readable_data(client, db, done):
    mine = (await client.get(f"{API}/analytics/overview", headers=done["h"])).json()
    assert mine["analyses"]["completed"] == 1 and mine["feature_count"] == len(done["features"])
    other = await make_user(db, "user")
    theirs = (await client.get(f"{API}/analytics/overview", headers=auth(other))).json()
    assert theirs["analyses"]["completed"] == 0 and theirs["feature_count"] == 0


async def test_reports_are_built_from_stored_results(client, done):
    base = f"{API}/reports/analyses/{done['analysis']['id']}"
    j = await client.get(base + "?format=json", headers=done["h"])
    assert j.status_code == 200
    rep = j.json()
    assert rep["summary"]["feature_count"] == len(done["features"]) and rep["is_demo"] is False
    assert rep["imagery"]["before"]["sha256"] and "severity is not a calibrated probability" in rep["disclaimer"]
    c = await client.get(base + "?format=csv", headers=done["h"])
    rows = list(csv.reader(io.StringIO(c.text)))
    assert rows[0] == ["section", "key", "value"] and any(r[:2] == ["summary", "feature_count"] and r[2] == str(len(done["features"])) for r in rows)
    p = await client.get(base + "?format=pdf", headers=done["h"])
    assert p.status_code == 200 and p.content[:5] == b"%PDF-" and p.headers["content-type"] == "application/pdf"
    assert (await client.get(base + "?format=docx", headers=done["h"])).status_code == 422
