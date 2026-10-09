"""GeoGuider orchestration: one chat turn = interpret -> (validated) workflow step -> tool calls -> reply.

The language model (when configured) only turns a message into a validated :class:`Intent`. Everything that follows - geocoding, catalogue
search, scene validation, job creation, statistics - comes from registered tools, and every state change goes through ``workflow.advance``.
"""
from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import llm
from app.config import settings
from app.geoguider import pairs as pairs_mod
from app.geoguider.intent import interpret
from app.geoguider.periods import resolve_period, sub_months
from app.geoguider.schemas import ROUTES, Intent, Option, Pending, WState, Workflow
from app.geoguider.tools import ToolContext, ToolResult, bbox_km2, registry
from app.geoguider.workflow import ACTIVE, RUNNING, InvalidTransition, advance, reset
from app.ml import registry as ml_registry
from app.models import User
from app.services import access
from app.services import analyses as analyses_svc

WELCOME = ("Hi, I'm GeoGuider, your AI geospatial copilot. Tell me what you want to investigate, and I'll help you find the right data, run supported GeoTraceAI "
           "analyses, visualize the results, and understand what they reveal.")


def today() -> date:
    return datetime.now(timezone.utc).date()


@dataclass
class Reply:
    text: str = ""
    blocks: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def extend(self, other: "Reply") -> "Reply":
        self.text = (self.text + "\n\n" + other.text).strip() if other.text else self.text
        self.blocks += other.blocks
        self.actions += other.actions
        self.suggestions = other.suggestions or self.suggestions
        return self


def _ha(m2: float | None) -> str:
    if m2 is None:
        return "n/a"
    return f"{m2 / 1e6:,.2f} km²" if m2 >= 1e6 else f"{m2 / 1e4:,.1f} ha"


def _d(iso: str | None) -> str:
    if not iso:
        return "unknown date"
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %b %Y")


def _err(res: ToolResult, what: str) -> Reply:
    return Reply(f"I couldn't {what}: {res.message}", blocks=[{"type": "error", "code": res.code, "message": res.message, "retryable": res.retryable}],
                 suggestions=["Try again"] if res.retryable else [])


class Turn:
    """State and helpers for one conversation turn."""

    def __init__(self, db: AsyncSession, user: User, conv_id: uuid.UUID, wf: Workflow, ui):
        self.db, self.conv_id, self.wf, self.ui = db, conv_id, wf, ui
        self.ctx = ToolContext(db, user, conv_id)

    @property
    def user(self) -> User:
        return self.ctx.user

    async def tool(self, tool_name: str, /, **kw) -> ToolResult:
        return await registry.call(tool_name, kw, self.ctx)

    def to(self, state: WState) -> None:
        advance(self.wf, state)

    # ------------------------------------------------------------------------------------------------------------ entry points
    async def message(self, text: str) -> Reply:
        wf = self.wf
        low = text.strip().lower()
        hint = {"workflow_state": wf.state.value, "waiting_for": wf.pending.kind if wf.pending else None, "has_area": wf.aoi is not None}
        intent = await interpret(text, today(), hint)
        p = wf.pending

        if intent.intent_type == "cancel":
            return await self.cancel()
        if p and p.kind == "period":
            per = resolve_period(text, today())
            if per:
                return await self.set_period(per.start, per.end, per.label)
        if p and p.kind == "location" and (intent.intent_type == "unknown" or not intent.location_query) and 1 <= len(text.split()) <= 8 and intent.intent_type not in ("navigate", "help"):
            return await self.resolve_place(re.sub(r"^(in|at|near|around|for)\s+", "", text.strip(), flags=re.I).strip(" .?!"))
        if re.fullmatch(r"\s*(retry|try again)\s*[.!]?", low) and wf.state in (WState.AOI_CONFIRMED, WState.INTENT_RESOLVED):
            return await self.advance_flow()
        if intent.intent_type == "confirm" or (re.fullmatch(r"\s*(retry|try again)\s*[.!]?", low) and wf.state == WState.FAILED):
            return await self.confirm_text()
        if p and p.kind == "area_on_map" and self.ui.drawn_bbox and re.search(r"\b(use|selected|drawn|done|this|ok)\b", low):
            return await self.use_drawn_box()
        handler = {
            "change_analysis": self.start_flow, "compare_dates": self.start_flow, "find_imagery": self.start_flow, "weather_alerts": self.weather,
            "explain_results": self.explain, "ask_results": self.ask, "export_results": self.export, "navigate": self.navigate, "help": self.help,
        }.get(intent.intent_type)
        if handler is None:
            return self.unknown(intent)
        return await handler(intent)

    async def choose(self, pending_id: str, option_id: str) -> Reply:
        p = self.wf.pending
        if p is None or p.id != pending_id:
            return Reply("That choice is no longer current. Tell me what you'd like to do next.")
        opt = next((o for o in p.options if o.id == option_id), None)
        if opt is None:
            return Reply("That isn't one of the options I offered.")
        kind = p.kind
        if kind == "period":
            if opt.payload.get("months"):
                end = today()
                return await self.set_period(sub_months(end, int(opt.payload["months"])), end, opt.label.lower())
            return Reply("Tell me the dates, for example “between March 2019 and June 2023”.")
        if kind == "place_choice":
            pl = self.wf.places[int(opt.payload["index"])]
            self.wf.pending = None
            return await self.take_place(pl)
        if kind == "aoi_size":
            if opt.id == "map":
                return self.ask_area_on_map()
            return await self.create_aoi(opt.payload["bbox"], opt.payload["name"], self.wf.place["name"] if self.wf.place else None)
        if kind == "mode_choice":
            self.wf.mode = opt.payload["mode"]
            self.wf.pending = None
            return await self.advance_flow()
        if kind == "scene_choice":
            return await self.select_option(opt.id)
        if kind == "confirm_plan":
            if opt.id == "confirm":
                return await self.start_run()
            return await self.back_to_choice()
        return Reply("I can't act on that choice.")

    # ------------------------------------------------------------------------------------------------------------ flow: intent -> area -> period -> scenes
    async def start_flow(self, intent: Intent) -> Reply:
        old = self.wf
        if old.state in RUNNING:
            return Reply("An analysis is still running in this conversation. Say “cancel” to stop it, or wait for the results before starting another.", suggestions=["Cancel"])
        carry_area = old.aoi if not (intent.location_query or intent.use_current_area) else None
        carry_place = old.place if carry_area else None
        self.wf = wf = reset()
        wf.intent = intent.model_dump(mode="json")
        wf.max_cloud = intent.cloud_cover_limit if intent.cloud_cover_limit is not None else 30.0
        wf.mode = intent.analysis_mode or "two_date"
        if intent.start_date and intent.end_date:
            wf.period = {"start": intent.start_date.isoformat(), "end": intent.end_date.isoformat(), "label": intent.period_label or "the requested period"}
        elif intent.intent_type == "find_imagery":
            end = today()
            wf.period = {"start": (end.fromordinal(end.toordinal() - 60)).isoformat(), "end": end.isoformat(), "label": "the last 60 days (default for “recent”)"}
        if carry_area:
            wf.aoi, wf.place = carry_area, carry_place
        self.to(WState.INTENT_RESOLVED)
        head = Reply()
        if wf.period:
            head.text = (f"I'll analyze **{wf.period['label']}**: {_d(wf.period['start'])} to {_d(wf.period['end'])} (resolved from today's date, {today():%d %b %Y}). "
                         "I'll first check which satellite acquisitions really exist, then help you choose dates to compare.")
        if wf.mode in ("trend", "multi_period"):
            head.text += ("\n\nQuick note on scope: GeoTrace's change detection compares two dates at a time. I can't produce a continuous year-by-year trend model, but I can run "
                         "a short series of separate pairwise comparisons across the period and put them side by side.")
        if intent.location_query:
            return head.extend(await self.resolve_place(intent.location_query))
        if intent.use_current_area:
            if self.ui.drawn_bbox:
                return head.extend(await self.use_drawn_box())
            if old.aoi:
                wf.aoi, wf.place = old.aoi, old.place
            else:
                return head.extend(self.ask_area_on_map())
        return head.extend(await self.advance_flow())

    async def advance_flow(self) -> Reply:
        wf = self.wf
        if wf.aoi is None:
            if wf.place is not None:
                return await self.place_to_aoi()
            wf.pending = Pending(id=_pid(), kind="location", prompt="Which place or area should I look at? Name a city or region (or “lat, lon”), or draw a rectangle on the map.")
            return Reply(wf.pending.prompt, suggestions=["Mumbai", "Draw an area on the map"])
        if wf.period is None:
            return self.ask_period()
        if wf.state == WState.INTENT_RESOLVED:
            self.to(WState.AOI_CONFIRMED)
        if wf.state == WState.AOI_CONFIRMED:
            return await self.search()
        return Reply("Where would you like to continue?")

    def ask_period(self) -> Reply:
        self.wf.pending = Pending(id=_pid(), kind="period", prompt="What period should I analyze?", options=[
            Option(id="y1", label="Last year", payload={"months": 12}), Option(id="y5", label="Last 5 years", payload={"months": 60}),
            Option(id="y10", label="Last 10 years", payload={"months": 120})])
        return Reply("What period should I analyze? Pick one below, or give custom dates such as “between March 2019 and June 2023”.",
                     blocks=[self._choices()], suggestions=["Past 5 years", "Between 2019 and 2024"])

    async def set_period(self, start: date, end: date, label: str) -> Reply:
        if (end - start).days < 10:
            return Reply("That period is too short to compare two satellite observations. Give me at least a couple of weeks.")
        self.wf.period = {"start": start.isoformat(), "end": end.isoformat(), "label": label}
        self.wf.pending = None
        r = Reply(f"I'll analyze **{label}**: {start:%d %b %Y} to {end:%d %b %Y} (resolved from today's date, {today():%d %b %Y}).")
        return r.extend(await self.advance_flow())

    async def resolve_place(self, query: str) -> Reply:
        res = await self.tool("resolve_location", query=query)
        if not res.ok:
            self.wf.pending = Pending(id=_pid(), kind="location", prompt="Try a different place name.")
            return _err(res, f"look up “{query}”")
        cands = res.data["candidates"]
        if not cands:
            self.wf.pending = Pending(id=_pid(), kind="location", prompt="Try a different place name.")
            return Reply(f"I couldn't find a place called “{query}”. Try a more specific name, a “lat, lon” pair, or draw an area on the map.", suggestions=["Draw an area on the map"])
        self.wf.places = cands[:4]
        ambiguous = len(cands) > 1 and (cands[0]["importance"] - cands[1]["importance"]) < 0.08 and cands[0]["name"].split(",")[0] != cands[1]["name"].split(",")[0]
        if ambiguous:
            self.wf.pending = Pending(id=_pid(), kind="place_choice", prompt=f"“{query}” matches several places. Which one do you mean?", options=[
                Option(id=f"p{i}", label=pl["name"][:150], description=f"{pl['category']}/{pl['kind']}", payload={"index": i}) for i, pl in enumerate(self.wf.places)])
            return Reply(self.wf.pending.prompt, blocks=[self._choices()])
        return await self.take_place(cands[0])

    async def take_place(self, pl: dict[str, Any]) -> Reply:
        self.wf.place = pl
        r = Reply(f"Resolved the place to **{pl['name']}** (from OpenStreetMap/Nominatim).")
        if self.wf.state == WState.IDLE:
            self.to(WState.INTENT_RESOLVED)
        return r.extend(await self.advance_flow())

    async def place_to_aoi(self) -> Reply:
        pl = self.wf.place
        km2 = bbox_km2(pl["bbox"])
        if km2 <= settings.GEOGUIDER_MAX_AOI_KM2:
            return await self.create_aoi(pl["bbox"], pl["name"].split(",")[0], pl["name"])
        lat, lon = pl["lat"], pl["lon"]
        opts = []
        for km in (10, 20):
            dlat = km / 110.57 / 2
            dlon = km / (111.32 * math.cos(math.radians(lat))) / 2
            opts.append(Option(id=f"c{km}", label=f"Central {km} × {km} km around {pl['name'].split(',')[0]}", description=f"≈ {km * km} km²",
                               payload={"bbox": [round(lon - dlon, 5), round(lat - dlat, 5), round(lon + dlon, 5), round(lat + dlat, 5)], "name": f"{pl['name'].split(',')[0]} (central {km} km)"}))
        opts.append(Option(id="map", label="I'll select the area on the map", description="Draw a rectangle, then tell me to use it"))
        self.wf.pending = Pending(id=_pid(), kind="aoi_size", prompt="Choose the area to analyze.", options=opts)
        return Reply(f"The boundary of {pl['name'].split(',')[0]} is about {km2:,.0f} km², more than the {settings.GEOGUIDER_MAX_AOI_KM2:,.0f} km² I process in one analysis "
                     "(satellite scenes are downloaded and analysed at 10 m resolution). Which area should I use?", blocks=[self._choices()])

    def ask_area_on_map(self) -> Reply:
        self.wf.pending = Pending(id=_pid(), kind="area_on_map", prompt="Draw a rectangle on the map, then tell me to use it.")
        return Reply("Draw a rectangle on the map (I've switched the draw tool on). When you've drawn it, say “use it” and I'll continue.",
                     actions=[{"type": "start_draw"}], suggestions=["Use the selected area"])

    async def use_drawn_box(self) -> Reply:
        b = self.ui.drawn_bbox
        if not b:
            return self.ask_area_on_map()
        self.wf.pending = None
        if self.wf.state == WState.IDLE:
            self.to(WState.INTENT_RESOLVED)
        return await self.create_aoi([round(v, 5) for v in b], "Selected area", None)

    async def create_aoi(self, bbox: list[float], name: str, place: str | None) -> Reply:
        res = await self.tool("create_or_update_aoi", name=name, bbox=bbox, place=place)
        if not res.ok:
            if res.code == "aoi_too_large" and self.wf.place:
                return await self.place_to_aoi()
            return _err(res, "prepare that area")
        self.wf.aoi = res.data
        self.wf.pending = None
        a = res.data
        r = Reply(f"Area of interest ready: **{a['name']}**, {a['area_km2']:,.1f} km² (west {a['bbox'][0]}, south {a['bbox'][1]}, east {a['bbox'][2]}, north {a['bbox'][3]}). It is shown on the map.",
                  blocks=[{"type": "aoi", "aoi": {k: a[k] for k in ("id", "name", "bbox", "area_km2")}}],
                  actions=[{"type": "show_aoi", "bbox": a["bbox"], "aoi_id": a["id"], "name": a["name"]}])
        if self.wf.state == WState.INTENT_RESOLVED:
            if self.wf.period is None:
                return r.extend(self.ask_period())
            self.to(WState.AOI_CONFIRMED)
        elif self.wf.state == WState.IDLE:
            self.to(WState.INTENT_RESOLVED)
        return r.extend(await self.advance_flow())

    # ------------------------------------------------------------------------------------------------------------ catalogue search and selection
    async def search(self) -> Reply:
        wf = self.wf
        find_only = (wf.intent or {}).get("intent_type") == "find_imagery"
        start, end = date.fromisoformat(wf.period["start"]), date.fromisoformat(wf.period["end"])
        span = (end - start).days
        n = 1 if find_only else (max(2, min(settings.GEOGUIDER_SEARCH_WINDOWS, math.ceil(span / 365))) if span > 400 else 2)
        res = await self.tool("search_satellite_scenes", bbox=wf.aoi["bbox"], start=start.isoformat(), end=end.isoformat(), max_cloud=wf.max_cloud, windows=n)
        if not res.ok:
            return _err(res, "search the satellite catalogue")
        wins = res.data["windows"]
        wf.failed_windows = res.data["failed_windows"]
        wf.coverage = [{k: w[k] for k in ("start", "end", "count", "best_cloud", "failed", "truncated")} for w in wins]
        self.to(WState.SCENES_FOUND)
        total = sum(w["count"] for w in wins)
        have = sum(1 for w in wins if w["count"])
        cov = {"type": "coverage", "provider": res.data["provider"], "max_cloud": wf.max_cloud, "rows": wf.coverage}
        text = (f"I searched the {res.data['provider']} Sentinel-2 L2A catalogue for **{wf.aoi['name']}**, {start:%d %b %Y} to {end:%d %b %Y}, in {len(wins)} sub-period(s) "
                f"(cloud ≤ {wf.max_cloud:.0f}%): **{total} scene(s)**, with data in {have} of {len(wins)} sub-periods.")
        if wf.failed_windows:
            text += f" {wf.failed_windows} sub-period search(es) failed, so those gaps are unknown rather than empty."
        if any(w["truncated"] for w in wins):
            text += " Some sub-periods hit the provider's 100-result page limit, so the lists there are partial."
        if find_only:
            allsc = sorted((s for w in wins for s in w["scenes"]), key=lambda s: s["acquired_at"], reverse=True)[:8]
            if not allsc:
                return Reply(text + " Nothing matched. Try a longer period or a higher cloud limit.", blocks=[cov], suggestions=["Allow up to 60% cloud cover"])
            return Reply(text + " The most recent ones are listed below.", blocks=[cov, {"type": "scene_list", "scenes": allsc}],
                         suggestions=["Compare the oldest and newest of these", "Analyze changes in this area"])
        opts = pairs_mod.build_options(wins, wf.mode, settings.GEOGUIDER_MAX_PAIRS)
        if not opts:
            return Reply(text + " That isn't enough to build a before/after pair: I need usable scenes in at least two different sub-periods. "
                         "Widening the period or the cloud limit may help. I won't substitute scenes you didn't choose.", blocks=[cov],
                         suggestions=["Allow up to 60% cloud cover", "Analyze a longer period"])
        wf.pair_options = opts
        labels = []
        for o in opts:
            first, last = o["pairs"][0], o["pairs"][-1]
            lab = (f"{'Recommended: ' if o['recommended'] else ''}" + (f"{len(o['pairs'])} consecutive comparisons, {_d(first['before']['acquired_at'])} → {_d(last['after']['acquired_at'])}"
                                                                         if o["kind"] == "series" else f"{_d(first['before']['acquired_at'])} → {_d(first['after']['acquired_at'])}"))
            labels.append(Option(id=o["id"], label=lab, description=_pair_desc(o)))
        wf.pending = Pending(id=_pid(), kind="scene_choice", prompt="Choose the scenes to compare.", options=labels)
        text += (" Ten years is far too many scenes to analyze one by one, so I rank candidate pairs by cloud cover, AOI coverage, and similar time of year "
                 "(to limit seasonal differences). Review the options and pick one, or say “run it” to take the recommended pair.")
        return Reply(text, blocks=[cov, {"type": "scene_pairs", "options": opts}, self._choices()], suggestions=["Run it"])

    async def select_option(self, option_id: str) -> Reply:
        wf = self.wf
        opt = next((o for o in wf.pair_options if o["id"] == option_id), None)
        if opt is None:
            return Reply("That isn't one of the scene options I found.")
        for pr in opt["pairs"]:
            v = await self.tool("select_satellite_scenes", before=_ref(pr["before"]), after=_ref(pr["after"]), max_cloud=wf.max_cloud)
            if not v.ok:
                return _err(v, "use those scenes")
        wf.selection = opt
        self.to(WState.SCENES_SELECTED)
        return self.plan_reply()

    def plan_reply(self) -> Reply:
        wf = self.wf
        opt = wf.selection
        card = ml_registry.get_card(settings.GEOGUIDER_MODEL_ID)
        rows = [["Area", f"{wf.aoi['name']} ({wf.aoi['area_km2']:,.1f} km²)"], ["Period requested", f"{_d(wf.period['start'])} to {_d(wf.period['end'])}"]]
        for i, pr in enumerate(opt["pairs"], 1):
            rows.append([f"Comparison {i}" if len(opt["pairs"]) > 1 else "Scenes", f"{_d(pr['before']['acquired_at'])} (cloud {_c(pr['before'])}) → {_d(pr['after']['acquired_at'])} (cloud {_c(pr['after'])})"])
        rows += [["Mode", "Series of separate two-date comparisons" if opt["kind"] == "series" else "Two-date comparison"],
                 ["Model", f"{settings.GEOGUIDER_MODEL_ID}" + (f" (trained at {card.trained_gsd_m:g} m)" if card else "")],
                 ["Analyses started", str(len(opt["pairs"]))],
                 ["Outputs", "Change polygons, area statistics, map layers, GeoJSON / GeoPackage / CSV export"],
                 ["Note", "Imagery download and preprocessing run inside the background job; I'll report its real stages."]]
        wf.pending = Pending(id=_pid(), kind="confirm_plan", prompt="Start this analysis?", options=[Option(id="confirm", label="Start analysis"), Option(id="back", label="Choose different scenes")])
        return Reply("I found suitable imagery for these dates. Review the plan and start the analysis when you're ready.", blocks=[{"type": "plan", "rows": rows}, self._choices()], suggestions=["Run it", "Cancel"])

    async def back_to_choice(self) -> Reply:
        wf = self.wf
        self.to(WState.SCENES_FOUND)
        wf.selection = None
        labels = [Option(id=o["id"], label=f"{_d(o['pairs'][0]['before']['acquired_at'])} → {_d(o['pairs'][-1]['after']['acquired_at'])}", description=_pair_desc(o)) for o in wf.pair_options]
        wf.pending = Pending(id=_pid(), kind="scene_choice", prompt="Choose the scenes to compare.", options=labels)
        return Reply("No problem — choose again.", blocks=[{"type": "scene_pairs", "options": wf.pair_options}, self._choices()])

    async def confirm_text(self) -> Reply:
        wf = self.wf
        if wf.state == WState.FAILED and wf.selection:
            self.to(WState.SCENES_SELECTED)
            return await self.start_run()
        p = wf.pending
        if p is None:
            return Reply("There's nothing waiting for confirmation. What would you like to look into?")
        if p.kind == "scene_choice":
            rec = next((o for o in wf.pair_options if o.get("recommended")), None)
            return await self.select_option(rec["id"]) if rec else Reply("Please pick one of the options.")
        if p.kind == "confirm_plan":
            return await self.start_run()
        return Reply(p.prompt, blocks=[self._choices()] if p.options else [])

    async def start_run(self) -> Reply:
        wf = self.wf
        if wf.state != WState.SCENES_SELECTED or not wf.selection or wf.job_ids:
            return Reply("There's no confirmed plan waiting to start (it may already be running).")
        pairs = [{"before": _ref(p["before"]), "after": _ref(p["after"])} for p in wf.selection["pairs"]]
        res = await self.tool("run_change_detection", aoi_id=wf.aoi["id"], pairs=pairs, max_cloud=wf.max_cloud, label=(wf.aoi["name"] or "GeoGuider")[:60])
        if not res.ok:
            wf.error = res.message
            wf.pending = None
            self.to(WState.FAILED)
            return _err(res, "start the analysis")
        wf.job_ids = [a["analysis_id"] for a in res.data["analyses"]]
        wf.pending = None
        wf.results_announced = False
        self.to(WState.PREPROCESSING)
        return Reply(f"Started {len(wf.job_ids)} analysis job(s) with model {res.data['model_id']}. Progress below is read live from the job queue; I'll post the results here when they finish.",
                     blocks=[{"type": "progress", "analysis_ids": wf.job_ids}], actions=[{"type": "track_analyses", "analysis_ids": wf.job_ids}], suggestions=["Cancel"])

    # ------------------------------------------------------------------------------------------------------------ job sync / results
    async def sync(self) -> Reply | None:
        wf = self.wf
        if wf.state not in RUNNING or not wf.job_ids:
            return None
        res = await self.tool("get_analysis_status", analysis_ids=wf.job_ids)
        if not res.ok:
            return None
        jobs = res.data["jobs"]
        st = [j["status"] for j in jobs]
        active = [s for s in st if s not in ("completed", "failed", "cancelled", "unavailable")]
        if active:
            early = {"queued", "validating", "acquiring_imagery", "preprocessing"}
            target = WState.PREPROCESSING if any(s in early for s in active) else WState.ANALYZING
            if target != wf.state:
                self.to(target)
            return None
        done = [j["id"] for j in jobs if j["status"] == "completed"]
        failed = [j for j in jobs if j["status"] in ("failed", "unavailable")]
        if done:
            self.to(WState.RESULTS_READY)
            wf.last_analysis_id = done[-1]
            wf.results_announced = True
            r = await self.results(done)
            if failed:
                r.text += f"\n\n{len(failed)} of {len(jobs)} analyses did not finish: " + "; ".join(f"{j.get('name') or j['id'][:8]}: {j.get('error') or 'failed'}" for j in failed)
            self.to(WState.COMPLETED)
            return r
        if all(s == "cancelled" for s in st):
            self.to(WState.CANCELLED)
            return Reply("The analysis was cancelled; the job has stopped. No results were produced.", suggestions=["Start again"])
        wf.error = "; ".join(f"{j.get('name') or j['id'][:8]}: {j.get('error') or j['status']}" for j in failed) or "the job failed"
        self.to(WState.FAILED)
        return Reply(f"The analysis failed: {wf.error}. Nothing was produced. You can say “retry” to run the same selection again.",
                     blocks=[{"type": "error", "code": "analysis_failed", "message": wf.error, "retryable": True}], suggestions=["Retry"])

    async def results(self, ids: list[str]) -> Reply:
        sections, comp = [], []
        for aid in ids:
            st = await self.tool("get_change_statistics", analysis_id=aid)
            if not st.ok:
                return _err(st, "read the results")
            ft = await self.tool("get_detected_features", analysis_id=aid, n=5)
            feats = ft.data["items"] if ft.ok else []
            sections.append(self._result_block(aid, st.data, feats))
            comp.append([f"{_d(st.data.get('before_date'))} → {_d(st.data.get('after_date'))}", st.data["feature_count"], st.data["total_changed_area_m2"]])
        first = sections[-1]
        head = first["headline"] if len(ids) == 1 else f"{len(ids)} analyses finished. " + " ".join(s["headline"] for s in sections)
        blocks: list[dict[str, Any]] = [{"type": "result", **s} for s in sections]
        if len(ids) > 1:
            blocks.insert(0, {"type": "period_summary", "rows": [[a, b, _ha(c)] for a, b, c in comp]})
        return Reply(head, blocks=blocks, actions=[{"type": "open_analysis", "analysis_id": ids[-1]}],
                     suggestions=["What changed the most?", "Show the five largest polygons", "What are the limitations?", "Export the results"])

    def _result_block(self, aid: str, s: dict[str, Any], feats: list[dict[str, Any]]) -> dict[str, Any]:
        n, area, analysed = s["feature_count"], s["total_changed_area_m2"], s.get("analyzed_area_m2")
        card = ml_registry.get_card(s.get("model_id"))
        observed = [f"Sentinel-2 L2A imagery acquired {_d(s.get('before_date'))} (before) and {_d(s.get('after_date'))} (after).",
                    f"Area analysed: {_ha(analysed)}." if analysed else "Analysed area not recorded."]
        computed = [f"{n} change polygon(s) covering {_ha(area)}." + (f" That is {100 * area / analysed:.2f}% of the analysed area." if analysed and area else "")]
        for sev in ("critical", "high", "medium", "low"):
            if sev in s["by_severity"]:
                v = s["by_severity"][sev]
                computed.append(f"{v['count']} {sev}-severity polygon(s), {_ha(v['area_m2'])} (severity is a heuristic priority tier, not a probability).")
        for f in feats:
            computed.append(f"#{f['seq']}: {_ha(f['area_m2'])} in the {f['position'] or 'area'} (lon {f['centroid'][0]}, lat {f['centroid'][1]}).")
        predictions = [f"Polygons were produced by the learned change-detection model {s.get('model_id') or s.get('method')}; model scores are uncalibrated and are not probabilities."]
        if card and card.metrics_note:
            predictions.append(card.metrics_note)
        interpretation = (["These are candidate differences between two observations. Imagery alone cannot establish what caused them, and a polygon is not confirmation of construction, "
                           "destruction or any specific event."] if n else ["No change above the detection threshold was found between these two scenes. That is a valid result, not an error."])
        limits = ["Different dates mean different seasons, crop cycles, tides, shadows and sun angles; these produce differences that are not real land change.",
                  "Residual cloud, haze or misregistration between scenes can create false detections; 10 m pixels cannot resolve small structures."] + list(card.limitations[:2] if card else [])
        limits += [w for w in s.get("warnings", [])][:3]
        if s.get("is_demo"):
            limits.insert(0, "This analysis is built from DEMO (synthetic) data.")
        return {"analysis_id": aid, "name": s["name"], "headline": s["facts"][0] if s.get("facts") else f"{n} polygons.", "model_id": s.get("model_id"), "feature_count": n,
                "changed_area_m2": area, "sections": {"observed": observed, "computed": computed, "predictions": predictions, "interpretation": interpretation, "limitations": limits}}

    # ------------------------------------------------------------------------------------------------------------ cancel
    async def cancel(self) -> Reply:
        wf = self.wf
        if wf.state in RUNNING and wf.job_ids:
            n = 0
            for jid in wf.job_ids:
                try:
                    job = await access.load_analysis(self.db, uuid.UUID(jid), self.user, write=True)
                    if job.status not in ("completed", "failed", "cancelled"):
                        await analyses_svc.request_cancel(self.db, job)
                        n += 1
                except Exception:
                    continue
            return Reply(f"Cancellation requested for {n} running job(s). A job stops at its next safe checkpoint, so it may take a moment; I'll confirm once it has actually stopped.")
        if wf.state in ACTIVE:
            wf.pending = None
            self.to(WState.CANCELLED)
            return Reply("Cancelled. Nothing was started.", suggestions=["Show me changes in Mumbai over the past 10 years"])
        return Reply("There's nothing running to cancel.")

    # ------------------------------------------------------------------------------------------------------------ other intents
    async def _target_analysis(self) -> str | None:
        if self.ui.active_analysis_id:
            return str(self.ui.active_analysis_id)
        if self.wf.last_analysis_id:
            return self.wf.last_analysis_id
        h = await self.tool("get_analysis_history", limit=1, only_completed=True)
        return h.data["analyses"][0]["id"] if h.ok and h.data["analyses"] else None

    async def explain(self, intent: Intent) -> Reply:
        aid = await self._target_analysis()
        if not aid:
            return Reply("I don't see any completed analysis in your workspace yet. Ask me to analyze an area and I'll run one.", suggestions=["Show me changes in Mumbai over the past 10 years"])
        r = await self.results([aid])
        r.text = "Here's what the stored results of your analysis say.\n\n" + r.text
        self.wf.last_analysis_id = aid
        return r

    async def ask(self, intent: Intent) -> Reply:
        aid = await self._target_analysis()
        q = intent.question or ""
        if not aid:
            return Reply("There are no completed analyses to answer from yet.", suggestions=["Show me changes in Mumbai over the past 10 years"])
        if re.search(r"limitation|caveat|reliab|trust", q, re.I):
            st = await self.tool("get_change_statistics", analysis_id=aid)
            if not st.ok:
                return _err(st, "read the results")
            blk = self._result_block(aid, st.data, [])
            return Reply("Limitations of this analysis:\n- " + "\n- ".join(blk["sections"]["limitations"] + blk["sections"]["predictions"]),
                         suggestions=["What changed the most?", "Export the results"])
        if re.search(r"first and last|compare the first", q, re.I) and len(self.wf.job_ids) >= 2:
            r = await self.results([self.wf.job_ids[0], self.wf.job_ids[-1]])
            r.text = "Comparing the first and last selected periods: " + r.text
            return r
        res = await self.tool("query_analysis_results", analysis_id=aid, question=q)
        if not res.ok:
            return _err(res, "answer that")
        d = res.data
        if not d["understood"]:
            return Reply(d["answer"] or "I can answer questions such as: largest changes, area by severity, changes near a boundary, vegetation or built-up change.", suggestions=d["suggestions"][:4])
        acts = [{"type": "open_analysis", "analysis_id": aid}]
        ref = next((x for x in d["references"] if x.get("centroid")), None)
        if ref:
            acts.append({"type": "zoom_to", "center": ref["centroid"], "label": ref["label"]})
        return Reply(d["answer"], blocks=[{"type": "facts", "facts": d["facts"], "caveats": d["caveats"], "source": d["answer_source"]}], actions=acts, suggestions=d["suggestions"][:4])

    async def export(self, intent: Intent) -> Reply:
        aid = await self._target_analysis()
        if not aid:
            return Reply("There are no completed analyses to export yet.")
        fmts = [intent.export_format] if intent.export_format else ["geojson", "gpkg", "csv", "pdf"]
        items = []
        for f in fmts:
            res = await self.tool("export_analysis_results", analysis_id=aid, format=f)
            if res.ok:
                items.append(res.data)
            elif len(fmts) == 1:
                return _err(res, "prepare that export")
        if not items:
            return Reply("This analysis has no exportable polygons.")
        acts = [{"type": "download_export", "path": items[0]["path"], "format": items[0]["format"], "name": items[0]["name"]}] if intent.export_format else []
        return Reply(f"Export ready for “{items[0]['name']}” ({items[0]['feature_count']} polygons). Files contain the computed polygons and their metadata.",
                     blocks=[{"type": "export", "items": items}], actions=acts)

    async def weather(self, intent: Intent) -> Reply:
        aoi = self.wf.aoi
        if intent.location_query:
            r = await self.tool("resolve_location", query=intent.location_query)
            if not r.ok or not r.data["candidates"]:
                return Reply(f"I couldn't find “{intent.location_query}”.")
            pl = r.data["candidates"][0]
            c = await self.tool("create_or_update_aoi", name=pl["name"].split(",")[0], bbox=pl["bbox"], place=pl["name"], purpose="weather")
            if not c.ok:
                return _err(c, "prepare that area")
            aoi = c.data
        elif self.ui.drawn_bbox and not aoi:
            c = await self.tool("create_or_update_aoi", name="Selected area", bbox=[round(v, 5) for v in self.ui.drawn_bbox], purpose="weather")
            if not c.ok:
                return _err(c, "prepare that area")
            aoi = c.data
        elif self.ui.active_aoi_id:
            aoi = {"id": str(self.ui.active_aoi_id)}
        if not aoi:
            return Reply("Which area? Name a place or draw a rectangle on the map first.", suggestions=["Show weather alerts for Mumbai"])
        res = await self.tool("get_weather_alerts", aoi_id=aoi["id"], refresh=True)
        if not res.ok:
            return _err(res, "check weather alerts")
        d = res.data
        if not d["configured"]:
            txt = "The OpenWeather alerts integration isn't configured on this server (no OPENWEATHER_API_KEY), so I can't fetch live alerts. Any alerts already stored for this area are shown below."
        elif not d["alerts"]:
            txt = f"OpenWeather reports no active alerts for {d['aoi']['name']} right now ({d['note'] or 'stored result'})."
        else:
            txt = f"{len(d['alerts'])} active weather alert(s) for {d['aoi']['name']} ({d['note'] or 'stored result'})."
        txt += " Weather alerts are forecasts from a weather service; they are separate from satellite observations and from AI-detected changes, and an overlap in dates does not show one caused the other."
        return Reply(txt, blocks=[{"type": "weather", "alerts": d["alerts"], "configured": d["configured"], "aoi": d["aoi"]["name"]}],
                     actions=[{"type": "show_aoi", "bbox": d["aoi"]["bbox"], "aoi_id": d["aoi"]["id"], "name": d["aoi"]["name"]}, {"type": "show_weather"}])

    async def navigate(self, intent: Intent) -> Reply:
        res = await self.tool("navigate_to_page", route=intent.navigate_to, panel=intent.panel)
        if not res.ok:
            return _err(res, "open that page")
        return Reply(f"Opening {res.data['label']}. Our conversation stays here.", actions=[{"type": "navigate", "route": res.data["route"], "panel": res.data["panel"]}])

    async def help(self, intent: Intent) -> Reply:
        cap = await capabilities()
        lines = [f"- Search real Sentinel-2 scenes and compare two dates with change detection: {'available' if cap['change_detection'] else 'not available on this server (' + cap['why_no_change'] + ')'}",
                 f"- Show results on the 2D map and 3D globe, summarise them, answer questions about them and export GeoJSON/GPKG/CSV: {'available' if cap['results'] else 'unavailable'}",
                 f"- Weather alerts (OpenWeather): {'available' if cap['weather'] else 'not configured (OPENWEATHER_API_KEY)'}",
                 "- Open pages of the app for you.", "- Not implemented: continuous multi-year trend modelling, NDVI/rainfall/air-quality values for an area."]
        return Reply((intent.reply + "\n\n" if intent.reply and intent.source == "llm" else "") + "Here's what I can do right now:\n" + "\n".join(lines),
                     suggestions=["Show me changes in Mumbai over the past 10 years", "Find recent Sentinel-2 imagery for my selected area", "Explain my latest analysis"])

    def unknown(self, intent: Intent) -> Reply:
        base = "I'm not sure what you'd like to do. "
        if self.wf.pending:
            return Reply(base + self.wf.pending.prompt, blocks=[self._choices()] if self.wf.pending.options else [])
        return Reply(base + "I can analyze changes in an area over time, find satellite imagery, show weather alerts, explain or export your results, or open a page.",
                     suggestions=["Analyze changes in Mumbai over the past 5 years", "What can you do?"])

    def _choices(self) -> dict[str, Any]:
        p = self.wf.pending
        return {"type": "choices", "pending_id": p.id, "kind": p.kind, "prompt": p.prompt, "options": [o.model_dump(include={"id", "label", "description"}) for o in p.options]}


def _pid() -> str:
    return uuid.uuid4().hex[:12]


def _c(card: dict[str, Any]) -> str:
    v = card.get("cloud_cover_pct")
    return "n/a" if v is None else f"{v:.0f}%"


def _ref(card: dict[str, Any]) -> dict[str, Any]:
    return {k: card.get(k) for k in ("product_id", "acquired_at", "cloud_cover_pct", "coverage_of_aoi_pct")}


def _pair_desc(o: dict[str, Any]) -> str:
    p = o["pairs"][0]
    if o["kind"] == "series":
        return "Separate pairwise comparisons across the period (not a continuous trend model)."
    return f"cloud {_c(p['before'])} / {_c(p['after'])}, {p['seasonal_gap_days']} days apart in the seasonal cycle, {p['separation_days']:,} days between scenes"


async def capabilities() -> dict[str, Any]:
    from app.providers.openweather import OpenWeatherAlerts
    from app.providers.sentinel import get_provider
    prov = get_provider()
    imagery = bool(prov and getattr(prov, "imagery_configured", getattr(prov, "_process", None) is not None))
    model = ml_registry.learned_ready(settings.GEOGUIDER_MODEL_ID)
    why = "no satellite provider configured" if prov is None else "no imagery credentials" if not imagery else "model unavailable" if not model else ""
    return {"change_detection": bool(prov and imagery and model), "why_no_change": why, "results": True, "weather": OpenWeatherAlerts().configured,
            "catalogue": prov is not None, "imagery": imagery, "model": model, "geocoder": settings.GEOCODER_PROVIDER != "none", "llm": llm.llm_enabled()}
