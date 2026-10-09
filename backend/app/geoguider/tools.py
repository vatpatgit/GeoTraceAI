"""Approved tool registry. Every tool has a strict input model, a permission level, a timeout and structured output.

The model may only *name* tools; the backend validates the input, checks the caller's role and ownership, bounds execution time and
records an audit entry. Tools wrap existing GeoTrace services; they never run model-generated code, SQL, shell commands or URLs.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Literal

from fastapi import HTTPException
from geoalchemy2.shape import from_shape, to_shape
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.geo import aoi as aoi_geo
from app.geoguider import pairs as pairs_mod
from app.geoguider.schemas import PANELS, ROUTES
from app.ml import registry as ml_registry
from app.models import AnalysisJob, AreaOfInterest, Project, User
from app.providers import geocode
from app.providers.base import ProviderError
from app.providers.sentinel import get_provider
from app.services import access
from app.services import sentinel as sentinel_svc

logger = logging.getLogger(__name__)
Permission = Literal["read", "write", "expensive"]


class ToolError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


@dataclass
class ToolContext:
    db: AsyncSession
    user: User
    conversation_id: uuid.UUID | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)
    user_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        self.user_id = self.user.id


async def _recover(ctx: ToolContext) -> None:
    """Roll the session back after a failed tool and reload the user (a rollback expires loaded objects, which async code cannot lazy-load)."""
    await ctx.db.rollback()
    ctx.user = await ctx.db.get(User, ctx.user_id)


@dataclass
class ToolResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    code: str | None = None
    message: str | None = None
    retryable: bool = False


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    permission: Permission
    timeout_s: float
    fn: Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, input_model: type[BaseModel], permission: Permission = "read", timeout_s: float = 60.0):
        def deco(fn):
            if name in self._tools:
                raise ValueError(f"duplicate tool {name}")
            self._tools[name] = Tool(name, description, input_model, permission, timeout_s, fn)
            return fn
        return deco

    def names(self) -> list[str]:
        return sorted(self._tools)

    def describe(self) -> list[dict[str, Any]]:
        return [{"name": t.name, "description": t.description, "permission": t.permission, "timeout_s": t.timeout_s,
                 "input_schema": t.input_model.model_json_schema()} for t in self._tools.values()]

    async def call(self, name: str, raw: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        tool = self._tools.get(name)
        entry: dict[str, Any] = {"tool": name, "permission": tool.permission if tool else None, "at": datetime.now(timezone.utc).isoformat(), "input": _summarise(raw)}

        def finish(res: ToolResult) -> ToolResult:
            entry.update(ok=res.ok, code=res.code, ms=int((time.monotonic() - started) * 1000))
            ctx.trace.append(entry)
            logger.info("geoguider tool=%s ok=%s code=%s ms=%d user=%s", name, res.ok, res.code, entry["ms"], ctx.user_id)
            return res

        if tool is None:
            return finish(ToolResult(False, code="unknown_tool", message="That operation is not available."))
        if tool.permission != "read" and not access.can_write_role(ctx.user):
            return finish(ToolResult(False, code="forbidden", message="Your role is read-only, so GeoGuider cannot start or change anything for you."))
        try:
            params = tool.input_model.model_validate(raw)
        except ValidationError as exc:
            err = exc.errors()[0]
            return finish(ToolResult(False, code="invalid_input", message=f"{'.'.join(str(p) for p in err['loc']) or 'input'}: {err['msg']}"))
        try:
            data = await asyncio.wait_for(tool.fn(ctx, params), timeout=tool.timeout_s)
            return finish(ToolResult(True, data=data))
        except ToolError as exc:
            await _recover(ctx)
            return finish(ToolResult(False, code=exc.code, message=exc.message, retryable=exc.retryable))
        except ProviderError as exc:
            await _recover(ctx)
            return finish(ToolResult(False, code=exc.code, message=str(exc), retryable=exc.status in (429, 502, 503, 504)))
        except aoi_geo.AoiError as exc:
            await _recover(ctx)
            return finish(ToolResult(False, code=getattr(exc, "code", "bad_aoi"), message=str(exc)))
        except HTTPException as exc:
            await _recover(ctx)
            d = exc.detail
            msg = d.get("message") if isinstance(d, dict) else str(d)
            return finish(ToolResult(False, code=(d.get("code") if isinstance(d, dict) else None) or f"http_{exc.status_code}", message=msg or "The request was refused."))
        except asyncio.TimeoutError:
            await _recover(ctx)
            return finish(ToolResult(False, code="timeout", message="That took too long and was stopped. Try a smaller area or period.", retryable=True))
        except Exception:  # never leak internals to the user
            logger.exception("geoguider tool %s crashed", name)
            await _recover(ctx)
            return finish(ToolResult(False, code="internal_error", message="Something went wrong while running that step. It was logged; please try again."))


def _summarise(raw: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in (raw or {}).items():
        s = v if isinstance(v, (int, float, bool)) or v is None else str(v)
        out[k] = s if not isinstance(s, str) else (s[:80] + ("…" if len(s) > 80 else ""))
    return out


registry = Registry()
BBox = list[float]


def _check_bbox(v: list[float]) -> list[float]:
    w, s, e, n = v
    if not (-180 <= w < e <= 180 and -85 <= s < n <= 85):
        raise ValueError("bbox must be [west, south, east, north] in degrees with west < east and south < north")
    return v


# ----------------------------------------------------------------------------------------------------------------- geography
class ResolveLocationIn(BaseModel):
    query: str = Field(min_length=2, max_length=120)


@registry.register("resolve_location", "Find places matching a name (or parse 'lat, lon') and return candidate boundaries as bounding boxes.", ResolveLocationIn, "read", 30)
async def resolve_location(ctx: ToolContext, p: ResolveLocationIn) -> dict[str, Any]:
    pt = geocode.parse_coordinates(p.query)
    if pt:
        lat, lon = pt
        d = 0.02
        place = geocode.Place(f"Point {lat:.4f}, {lon:.4f}", lat, lon, (max(-180, lon - d), max(-85, lat - d), min(180, lon + d), min(85, lat + d)), "coordinates", "point", 1.0)
        return {"candidates": [place.public()], "from_coordinates": True}
    found = await geocode.search(p.query, limit=5)
    return {"candidates": [pl.public() for pl in found], "from_coordinates": False}


class AoiIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    bbox: list[float] = Field(min_length=4, max_length=4)
    place: str | None = Field(default=None, max_length=200)
    purpose: Literal["analysis", "weather"] = "analysis"

    @field_validator("bbox")
    @classmethod
    def _bb(cls, v):
        return _check_bbox(v)


def bbox_km2(b: list[float]) -> float:
    return aoi_geo.finalize_aoi(aoi_geo.bbox_polygon(b), max_km2=1e9)[1]


@registry.register("create_or_update_aoi", "Create (or reuse) a saved area of interest from a bounding box in the user's own workspace.", AoiIn, "write", 30)
async def create_or_update_aoi(ctx: ToolContext, p: AoiIn) -> dict[str, Any]:
    poly, km2 = aoi_geo.finalize_aoi(aoi_geo.bbox_polygon(p.bbox), max_km2=settings.MAX_AOI_KM2)
    limit = settings.GEOGUIDER_MAX_AOI_KM2 if p.purpose == "analysis" else min(settings.WEATHER_MAX_AOI_KM2, settings.MAX_AOI_KM2)
    if km2 > limit:
        raise ToolError("aoi_too_large", f"That area is {km2:,.0f} km², above the {limit:,.0f} km² limit for this task. Choose a smaller area.")
    project = await access.default_project(ctx.db, ctx.user)
    key = hashlib.sha1(",".join(f"{v:.5f}" for v in p.bbox).encode()).hexdigest()[:16]
    rows = (await ctx.db.execute(select(AreaOfInterest).where(AreaOfInterest.project_id == project.id, AreaOfInterest.source == "geoguider"))).scalars().all()
    row = next((r for r in rows if (r.metadata_json or {}).get("bbox_key") == key), None)
    if row is None:
        row = AreaOfInterest(project_id=project.id, name=p.name[:120], geometry=from_shape(poly, srid=4326), area_km2=km2, source="geoguider",
                             metadata_json={"bbox_key": key, "place": p.place, "created_via": "geoguider"})
        ctx.db.add(row)
        await ctx.db.commit()
        await ctx.db.refresh(row)
    return aoi_dict(row)


def aoi_dict(row: AreaOfInterest) -> dict[str, Any]:
    g = to_shape(row.geometry)
    return {"id": str(row.id), "project_id": str(row.project_id), "name": row.name, "bbox": [round(v, 5) for v in g.bounds], "area_km2": round(row.area_km2, 2), "geometry": mapping(g)}


class AoiIdIn(BaseModel):
    aoi_id: uuid.UUID


async def load_aoi(ctx: ToolContext, aoi_id: uuid.UUID) -> AreaOfInterest:
    row = await ctx.db.get(AreaOfInterest, aoi_id)
    if row is None:
        raise ToolError("aoi_not_found", "That area of interest was not found.")
    try:
        await access.load_project(ctx.db, row.project_id, ctx.user)
    except HTTPException:
        raise ToolError("aoi_not_found", "That area of interest was not found.")  # same answer as missing: no existence leak
    return row


@registry.register("get_aoi_metadata", "Return the name, bounds and area of one of the user's areas of interest.", AoiIdIn, "read", 15)
async def get_aoi_metadata(ctx: ToolContext, p: AoiIdIn) -> dict[str, Any]:
    return aoi_dict(await load_aoi(ctx, p.aoi_id))


# ----------------------------------------------------------------------------------------------------------------- satellite catalogue
class SearchIn(BaseModel):
    bbox: list[float] = Field(min_length=4, max_length=4)
    start: date
    end: date
    max_cloud: float = Field(default=30.0, ge=0, le=100)
    windows: int = Field(default=2, ge=1, le=24)

    @field_validator("bbox")
    @classmethod
    def _bb(cls, v):
        return _check_bbox(v)

    @model_validator(mode="after")
    def _ordered(self):
        if self.start >= self.end:
            raise ValueError("start must be before end")
        if self.end > datetime.now(timezone.utc).date():
            raise ValueError("end is in the future")
        return self


def split_windows(start: date, end: date, n: int) -> list[tuple[date, date]]:
    total = (end - start).days + 1
    n = max(1, min(n, total))
    edges = [start + timedelta(days=round(i * total / n)) for i in range(n)] + [end + timedelta(days=1)]
    return [(edges[i], edges[i + 1] - timedelta(days=1)) for i in range(n) if edges[i] <= edges[i + 1] - timedelta(days=1)]


def card(s) -> dict[str, Any]:
    return {"product_id": s.product_id, "collection": s.collection, "provider": s.provider,
            "acquired_at": s.acquired_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "cloud_cover_pct": None if s.cloud_cover_pct is None else round(s.cloud_cover_pct, 1),
            "coverage_of_aoi_pct": None if s.coverage_of_aoi_pct is None else round(s.coverage_of_aoi_pct, 1),
            "platform": s.platform, "resolution_m": s.resolution_m, "processing_level": s.processing_level}


@registry.register("search_satellite_scenes", "Search the configured Sentinel-2 L2A catalogue in several sub-periods and report real scenes per period (no imagery is downloaded).",
                   SearchIn, "read", 150)
async def search_satellite_scenes(ctx: ToolContext, p: SearchIn) -> dict[str, Any]:
    provider = get_provider()
    if provider is None:
        raise ToolError("provider_not_configured", "No satellite catalogue is configured on this server (SENTINEL_PROVIDER), so I cannot look up real imagery.")
    aoi_poly = aoi_geo.bbox_polygon(p.bbox)
    gj = mapping(aoi_poly)
    sem = asyncio.Semaphore(3)
    errors: list[ProviderError] = []

    async def one(a: date, b: date) -> dict[str, Any]:
        s0, s1 = sentinel_svc.window_bounds(a, b)
        async with sem:
            try:
                raw = await provider.search(gj, s0, s1, max_cloud_pct=p.max_cloud, limit=100, collection="sentinel-2-l2a")
            except ProviderError as exc:
                errors.append(exc)
                return {"start": a.isoformat(), "end": b.isoformat(), "scenes": [], "failed": True, "truncated": False, "count": 0, "best_cloud": None}
        grouped = [s for s in sentinel_svc.group_scenes(raw, aoi_poly) if s.cloud_cover_pct is None or s.cloud_cover_pct <= p.max_cloud]
        cards = [card(s) for s in grouped]
        cards.sort(key=lambda c: (c["cloud_cover_pct"] if c["cloud_cover_pct"] is not None else 100, -(c["coverage_of_aoi_pct"] or 0)))
        clouds = [c["cloud_cover_pct"] for c in cards if c["cloud_cover_pct"] is not None]
        return {"start": a.isoformat(), "end": b.isoformat(), "count": len(cards), "best_cloud": min(clouds) if clouds else None,
                "truncated": len(raw) >= 100, "failed": False, "scenes": cards[:25]}

    windows = await asyncio.gather(*(one(a, b) for a, b in split_windows(p.start, p.end, p.windows)))
    if errors and all(w["failed"] for w in windows):
        raise errors[0]
    return {"provider": provider.name, "windows": windows, "failed_windows": sum(1 for w in windows if w["failed"]), "max_cloud": p.max_cloud,
            "imagery_configured": bool(getattr(provider, "imagery_configured", getattr(provider, "_process", None) is not None))}


class SceneRef(BaseModel):
    product_id: str = Field(min_length=3, max_length=200)
    acquired_at: datetime
    cloud_cover_pct: float | None = None
    coverage_of_aoi_pct: float | None = None


class SelectIn(BaseModel):
    before: SceneRef
    after: SceneRef
    max_cloud: float = Field(default=30.0, ge=0, le=100)


@registry.register("select_satellite_scenes", "Validate a chosen before/after scene pair (order, separation, cloud, AOI coverage, retrieval availability). Never substitutes scenes.",
                   SelectIn, "read", 15)
async def select_satellite_scenes(ctx: ToolContext, p: SelectIn) -> dict[str, Any]:
    gap = (p.after.acquired_at - p.before.acquired_at).days
    if gap < pairs_mod.MIN_SEPARATION_DAYS:
        raise ToolError("date_order", f"The after scene must be at least {pairs_mod.MIN_SEPARATION_DAYS} days after the before scene (these are {gap} days apart).")
    warnings: list[str] = []
    for label, s in (("before", p.before), ("after", p.after)):
        if s.coverage_of_aoi_pct is not None and s.coverage_of_aoi_pct < pairs_mod.MIN_COVERAGE_PCT:
            raise ToolError("poor_coverage", f"The {label} scene covers only {s.coverage_of_aoi_pct:.0f}% of the area.")
        if s.coverage_of_aoi_pct is not None and s.coverage_of_aoi_pct < 95:
            warnings.append(f"The {label} scene covers {s.coverage_of_aoi_pct:.0f}% of the area; the rest cannot be analysed.")
        if s.cloud_cover_pct is not None and s.cloud_cover_pct > p.max_cloud:
            warnings.append(f"The {label} scene is {s.cloud_cover_pct:.0f}% cloudy (limit {p.max_cloud:.0f}%).")
    provider = get_provider()
    if provider is None or not getattr(provider, "imagery_configured", getattr(provider, "_process", None) is not None):
        raise ToolError("imagery_not_configured", "Imagery retrieval is not configured on this server (Sentinel OAuth client credentials), so scenes can be listed but not downloaded.")
    return {"valid": True, "separation_days": gap, "warnings": warnings}


# ----------------------------------------------------------------------------------------------------------------- analysis
class PairIn(BaseModel):
    before: SceneRef
    after: SceneRef


class RunIn(BaseModel):
    aoi_id: uuid.UUID
    pairs: list[PairIn] = Field(min_length=1)
    max_cloud: float = Field(default=30.0, ge=0, le=100)
    label: str | None = Field(default=None, max_length=80)

    @field_validator("pairs")
    @classmethod
    def _cap(cls, v):
        if len(v) > settings.GEOGUIDER_MAX_PAIRS:
            raise ValueError(f"at most {settings.GEOGUIDER_MAX_PAIRS} pairs per request")
        return v


@registry.register("run_change_detection", "Queue real change-detection analyses (scene retrieval, preprocessing, learned model, polygons) for chosen scene pairs.",
                   RunIn, "expensive", 90)
async def run_change_detection(ctx: ToolContext, p: RunIn) -> dict[str, Any]:
    from app.api import sentinel as sentinel_api  # local import: avoids an import cycle through app.api
    from app.schemas.sentinel import AcquireRequest

    model_id = settings.GEOGUIDER_MODEL_ID
    if not ml_registry.learned_ready(model_id):
        raise ToolError("model_unavailable", f"The change-detection model '{model_id}' is not available on this server (PyTorch or the checkpoint is missing), so I cannot run an analysis. "
                                             "Nothing was started and no result was produced.")
    row = await load_aoi(ctx, p.aoi_id)
    created = []
    for i, pr in enumerate(p.pairs):
        name = f"{p.label or 'GeoGuider'} {pr.before.acquired_at:%Y-%m-%d} → {pr.after.acquired_at:%Y-%m-%d}"
        req = AcquireRequest(project_id=row.project_id, aoi_id=row.id, before_product_id=pr.before.product_id, after_product_id=pr.after.product_id,
                             max_cloud_cover_pct=p.max_cloud, name=name[:160], config={"detection": {"method": "learned_siamese", "model_id": model_id}})
        res = await sentinel_api.acquire(req, ctx.db, ctx.user)
        created.append({"analysis_id": str(res.analysis_id), "before_product_id": res.before_product_id, "after_product_id": res.after_product_id})
    return {"analyses": created, "model_id": model_id}


class StatusIn(BaseModel):
    analysis_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)


@registry.register("get_analysis_status", "Return the real job state of analyses the user owns or can read.", StatusIn, "read", 15)
async def get_analysis_status(ctx: ToolContext, p: StatusIn) -> dict[str, Any]:
    out = []
    for aid in p.analysis_ids:
        try:
            job = await access.load_analysis(ctx.db, aid, ctx.user)
        except HTTPException:
            out.append({"id": str(aid), "status": "unavailable", "progress": 0.0, "stage": None, "error": "not found"})
            continue
        await ctx.db.refresh(job)
        err = (job.error or {}).get("message") if isinstance(job.error, dict) else None
        out.append({"id": str(job.id), "name": job.name, "status": job.status, "progress": round(job.progress or 0.0, 3), "stage": job.stage_message, "error": err,
                    "before_date": job.before_date.isoformat() if job.before_date else None, "after_date": job.after_date.isoformat() if job.after_date else None})
    return {"jobs": out}


class AnalysisIn(BaseModel):
    analysis_id: uuid.UUID


async def load_completed(ctx: ToolContext, analysis_id: uuid.UUID) -> AnalysisJob:
    try:
        job = await access.load_analysis(ctx.db, analysis_id, ctx.user)
    except HTTPException:
        raise ToolError("analysis_not_found", "I could not find that analysis in your workspace.")
    if job.status != "completed":
        raise ToolError("analysis_not_ready", f"That analysis is '{job.status}', so there are no final results yet.")
    return job


@registry.register("get_change_statistics", "Computed statistics for a completed analysis: polygon count, changed area, share of area, severity/category split.", AnalysisIn, "read", 30)
async def get_change_statistics(ctx: ToolContext, p: AnalysisIn) -> dict[str, Any]:
    from app.analytics import queries
    job = await load_completed(ctx, p.analysis_id)
    res = await queries.summarize_analysis(ctx.db, job, n=1)
    d = dict(res.data)
    d.update(name=job.name, model_id=job.model_id, method=job.method, input_type=job.input_type, is_demo=job.is_demo,
             grid=(job.processing or {}).get("grid"), warnings=[w.get("message") for w in (job.warnings or []) if w.get("level") != "info"][:6],
             bounds=job.bounds_wgs84, facts=res.facts, caveats=res.caveats)
    for k in ("before_date", "after_date"):
        v = d.get(k)
        d[k] = v.isoformat() if hasattr(v, "isoformat") else v
    return d


class FeaturesIn(BaseModel):
    analysis_id: uuid.UUID
    n: int = Field(default=5, ge=1, le=20)


@registry.register("get_detected_features", "Largest detected change polygons of a completed analysis with centroid and position inside the area.", FeaturesIn, "read", 30)
async def get_detected_features(ctx: ToolContext, p: FeaturesIn) -> dict[str, Any]:
    from app.analytics import queries
    job = await load_completed(ctx, p.analysis_id)
    res = await queries.largest_changes(ctx.db, job, n=p.n)
    bounds = job.bounds_wgs84
    items = []
    for it in res.data["items"]:
        c = it["centroid"]
        items.append({**{k: it[k] for k in ("id", "seq", "category", "severity", "area_m2", "magnitude", "confidence")}, "centroid": [round(c[0], 5), round(c[1], 5)],
                      "position": pairs_mod.locate_in_bbox(c[0], c[1], bounds) if bounds else None})
    return {"items": items}


class QueryIn(BaseModel):
    analysis_id: uuid.UUID | None = None
    question: str = Field(min_length=2, max_length=500)


@registry.register("query_analysis_results", "Answer a question about stored results through the existing analytics engine (approved operations only).", QueryIn, "read", 60)
async def query_analysis_results(ctx: ToolContext, p: QueryIn) -> dict[str, Any]:
    from app.analytics.service import _jsonable, run_query
    from app.schemas.analytics import AnalyticsQueryRequest
    if p.analysis_id:
        await access.load_analysis(ctx.db, p.analysis_id, ctx.user)
    res = await run_query(ctx.db, ctx.user, AnalyticsQueryRequest(question=p.question, analysis_id=p.analysis_id, narrate=True))
    return _jsonable({"understood": res.understood, "operation": res.operation, "answer": res.answer, "answer_source": res.answer_source, "facts": res.measured_facts,
                      "caveats": res.caveats, "references": [r.model_dump() for r in res.references][:8], "suggestions": res.suggestions})


class HistoryIn(BaseModel):
    limit: int = Field(default=5, ge=1, le=10)
    only_completed: bool = False


@registry.register("get_analysis_history", "List the user's most recent analyses.", HistoryIn, "read", 15)
async def get_analysis_history(ctx: ToolContext, p: HistoryIn) -> dict[str, Any]:
    q = select(AnalysisJob).join(Project, Project.id == AnalysisJob.project_id).where(access.readable_projects_clause(ctx.user))
    if p.only_completed:
        q = q.where(AnalysisJob.status == "completed")
    rows = (await ctx.db.execute(q.order_by(AnalysisJob.created_at.desc()).limit(p.limit))).scalars().all()
    return {"analyses": [{"id": str(j.id), "name": j.name, "status": j.status, "created_at": j.created_at.isoformat(),
                          "before_date": j.before_date.isoformat() if j.before_date else None, "after_date": j.after_date.isoformat() if j.after_date else None,
                          "is_demo": j.is_demo} for j in rows]}


# ----------------------------------------------------------------------------------------------------------------- weather / export / navigation
class WeatherIn(BaseModel):
    aoi_id: uuid.UUID
    refresh: bool = False


@registry.register("get_weather_alerts", "Stored (and optionally freshly fetched) OpenWeather alerts for one of the user's areas. Weather alerts are not satellite detections.",
                   WeatherIn, "read", 45)
async def get_weather_alerts(ctx: ToolContext, p: WeatherIn) -> dict[str, Any]:
    from app.models import WeatherAlert
    from app.providers.openweather import OpenWeatherAlerts
    from app.services.weather_alerts import refresh_aoi
    row = await load_aoi(ctx, p.aoi_id)
    configured = OpenWeatherAlerts().configured
    note = None
    if p.refresh and configured and access.can_write_role(ctx.user):
        res = await refresh_aoi(ctx.db, row)
        note = "served from the stored result (checked recently)" if res.cached else "fetched from OpenWeather just now"
    elif p.refresh and not configured:
        note = "OpenWeather is not configured on this server (OPENWEATHER_API_KEY), so no fresh check was possible"
    alerts = (await ctx.db.execute(select(WeatherAlert).where(WeatherAlert.aoi_id == row.id, WeatherAlert.status == "active")
                                   .order_by(WeatherAlert.severity.desc(), WeatherAlert.last_seen_at.desc()).limit(10))).scalars().all()
    return {"configured": configured, "aoi": aoi_dict(row), "note": note,
            "alerts": [{"id": str(a.id), "title": a.title, "severity": a.severity, "source": a.source, "tags": a.tags,
                        "start": a.start_time.isoformat() if a.start_time else None, "end": a.end_time.isoformat() if a.end_time else None} for a in alerts]}


class ExportIn(BaseModel):
    analysis_id: uuid.UUID
    format: Literal["geojson", "gpkg", "csv", "pdf"] = "geojson"


@registry.register("export_analysis_results", "Authorise and describe a download of a completed analysis' computed polygons (GeoJSON / GeoPackage / CSV) or its report (PDF).",
                   ExportIn, "read", 30)
async def export_analysis_results(ctx: ToolContext, p: ExportIn) -> dict[str, Any]:
    from sqlalchemy import func

    from app.models import ChangeFeature
    job = await load_completed(ctx, p.analysis_id)
    n = await ctx.db.scalar(select(func.count()).select_from(ChangeFeature).where(ChangeFeature.analysis_id == job.id)) or 0
    if p.format != "pdf" and n == 0:
        raise ToolError("nothing_to_export", "This analysis found no change polygons, so there is nothing to export (the PDF report is still available).")
    return {"analysis_id": str(job.id), "name": job.name, "format": p.format, "feature_count": n,
            "path": f"/reports/analyses/{job.id}?format=pdf" if p.format == "pdf" else f"/analyses/{job.id}/export?format={p.format}"}


class NavIn(BaseModel):
    route: str
    panel: str | None = None

    @field_validator("route")
    @classmethod
    def _r(cls, v):
        if v not in ROUTES:
            raise ValueError("unknown page")
        return v

    @field_validator("panel")
    @classmethod
    def _p(cls, v):
        if v is not None and v not in PANELS:
            raise ValueError("unknown panel")
        return v


@registry.register("navigate_to_page", "Return a validated navigation instruction for an existing application page (the UI maps the key to its own route).", NavIn, "read", 5)
async def navigate_to_page(ctx: ToolContext, p: NavIn) -> dict[str, Any]:
    return {"route": p.route, "panel": p.panel, "label": ROUTES[p.route]}
