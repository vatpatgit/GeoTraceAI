"""Live hazard feed client (earthquakes, fire hotspots, storms). Server-side only; the base URL comes from configuration.

The feed aggregates public datasets (USGS earthquakes, NASA FIRMS fire hotspots, NASA EONET events). Its schema is undocumented, so every
record is parsed defensively and anything unrecognised is skipped, never guessed. Text from the feed is untrusted: control characters are
stripped and lengths bounded before it is stored or shown.

Not used (and why): ``/air-quality`` returned no stations when checked, so its schema could not be verified; ``/radar`` lists country-level
internet outages (IODA) at country centroids, which cannot be matched to an AOI meaningfully.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.providers import http
from app.providers.base import ProviderError, ProviderNotConfigured
from app.providers.geocode import clean

logger = logging.getLogger(__name__)
KINDS = ("earthquake", "fire", "storm")
MAX_RECORDS = 6000
_ENDPOINT = {"earthquake": ("earthquakes", "earthquakes"), "fire": ("fires", "fires"), "storm": ("weather", "events")}  # kind -> (path, list key)


@dataclass(frozen=True)
class HazardEvent:
    kind: str
    external_id: str  # fires have none upstream (aggregated per AOI and day by the service)
    title: str
    lat: float
    lon: float
    occurred_at: datetime | None
    severity_hint: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeedResult:
    events: dict[str, list[HazardEvent]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)  # kind -> user-safe reason (that kind is unknown, not "empty")


def _num(v: Any) -> float | None:
    try:
        f = float(v)
        return f if f == f and abs(f) < 1e15 else None
    except (TypeError, ValueError):
        return None


def _point(r: dict[str, Any]) -> tuple[float, float] | None:
    lat, lon = _num(r.get("lat")), _num(r.get("lng", r.get("lon")))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def parse_earthquakes(rows: list[Any]) -> list[HazardEvent]:
    out = []
    for r in rows[:MAX_RECORDS]:
        if not isinstance(r, dict):
            continue
        pt, mag, t = _point(r), _num(r.get("magnitude")), _num(r.get("time"))
        if pt is None or mag is None or t is None or not r.get("id"):
            continue
        place = clean(str(r.get("place") or "unknown location"), 120)
        url = str(r.get("url") or "")
        out.append(HazardEvent("earthquake", clean(str(r["id"]), 100), f"M{mag:.1f} earthquake, {place}", pt[0], pt[1], datetime.fromtimestamp(t / 1000, tz=timezone.utc),
                               details={"magnitude": mag, "depth_km": _num(r.get("depth")), "place": place, "tsunami_flag": bool(r.get("tsunami")),
                                        "usgs_alert": clean(str(r["alert"]), 20) if r.get("alert") else None, "felt_reports": r.get("felt") if isinstance(r.get("felt"), int) else None,
                                        "url": url if url.startswith("https://earthquake.usgs.gov/") else None, "source": "USGS"}))
    return out


def parse_fires(rows: list[Any]) -> list[HazardEvent]:
    out = []
    for r in rows[:MAX_RECORDS * 10]:
        if not isinstance(r, dict):
            continue
        pt, date = _point(r), str(r.get("date") or "")
        if pt is None or len(date) != 10:
            continue
        hhmm = str(r.get("time") or "0000").zfill(4)
        try:
            when = datetime.strptime(f"{date} {hhmm}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        out.append(HazardEvent("fire", "", "fire hotspot", pt[0], pt[1], when,
                               details={"frp_mw": _num(r.get("frp")), "confidence": clean(str(r.get("confidence", "")), 12), "brightness_k": _num(r.get("brightness")), "date": date}))
    return out


def parse_storms(rows: list[Any]) -> list[HazardEvent]:
    out = []
    for r in rows[:MAX_RECORDS]:
        if not isinstance(r, dict):
            continue
        pt = _point(r)
        if pt is None or not r.get("id") or not r.get("title"):
            continue
        when = None
        try:
            when = datetime.fromisoformat(str(r.get("date")).replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            pass
        src = str(r.get("source") or "")
        out.append(HazardEvent("storm", clean(str(r["id"]), 100), clean(str(r["title"]), 200), pt[0], pt[1], when, clean(str(r.get("severity") or ""), 10) or None,
                               details={"category": clean(str(r.get("type") or r.get("category") or ""), 60), "provider": clean(str(r.get("provider") or ""), 40),
                                        "source_url": src if src.startswith("https://") else None}))
    return out


_PARSERS = {"earthquake": parse_earthquakes, "fire": parse_fires, "storm": parse_storms}


async def fetch_feed(kinds: tuple[str, ...] = KINDS) -> FeedResult:
    if settings.HAZARD_FEED_PROVIDER == "none":
        raise ProviderNotConfigured("The live hazard feed is disabled on this server (HAZARD_FEED_PROVIDER=none).")
    base = settings.HAZARD_FEED_URL.rstrip("/")
    res = FeedResult()

    async def one(kind: str) -> None:
        path, key = _ENDPOINT[kind]
        try:
            r = await http.request("GET", f"{base}/{path}", retries=2, timeout=settings.HAZARD_TIMEOUT_S, headers={"User-Agent": settings.GEOCODER_USER_AGENT, "Accept": "application/json"})
            body = r.json()
            rows = body.get(key) if isinstance(body, dict) else None
            if not isinstance(rows, list):
                raise ProviderError("The hazard feed answered in an unexpected format.", code="feed_bad_format")
            res.events[kind] = _PARSERS[kind](rows)
        except ProviderError as exc:
            res.errors[kind] = str(exc)[:200]
        except ValueError:
            res.errors[kind] = "The hazard feed returned unreadable data."
        except Exception:  # never let one feed break the others
            logger.exception("hazard feed %s failed", kind)
            res.errors[kind] = "The hazard feed failed unexpectedly."

    await asyncio.gather(*(one(k) for k in kinds))
    if len(res.errors) == len(kinds):
        raise ProviderError("The live hazard feed is unreachable: " + "; ".join(sorted(set(res.errors.values()))), code="feed_unavailable", status=502)
    return res
