"""Pure helpers: score scene pairs, pick representative dates, describe where a point lies inside an AOI."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

MIN_SEPARATION_DAYS = 3
MIN_COVERAGE_PCT = 50.0


def _dt(card: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(card["acquired_at"].replace("Z", "+00:00")).astimezone(timezone.utc)


def doy_gap(a: datetime, b: datetime) -> int:
    """Calendar distance in days between the two dates' positions in the year (0-182): a proxy for seasonal mismatch."""
    d = abs(a.timetuple().tm_yday - b.timetuple().tm_yday)
    return min(d, 365 - d)


def _cloud(c: dict[str, Any]) -> float:
    v = c.get("cloud_cover_pct")
    return 50.0 if v is None else float(v)


def _cov(c: dict[str, Any]) -> float:
    v = c.get("coverage_of_aoi_pct")
    return 100.0 if v is None else float(min(v, 100.0))


def score_pair(b: dict[str, Any], a: dict[str, Any]) -> float | None:
    """Lower is better; None when the pair is unusable (wrong order, too close in time, poor coverage)."""
    db, da = _dt(b), _dt(a)
    if (da - db).days < MIN_SEPARATION_DAYS:
        return None
    if _cov(b) < MIN_COVERAGE_PCT or _cov(a) < MIN_COVERAGE_PCT:
        return None
    return _cloud(b) + _cloud(a) + 0.5 * ((100 - _cov(b)) + (100 - _cov(a))) + 0.2 * doy_gap(db, da)


def best_pairs(before_pool: list[dict[str, Any]], after_pool: list[dict[str, Any]], n: int = 3) -> list[tuple[float, dict[str, Any], dict[str, Any]]]:
    scored = []
    for b in before_pool:
        for a in after_pool:
            s = score_pair(b, a)
            if s is not None:
                scored.append((s, b, a))
    scored.sort(key=lambda t: t[0])
    out, used_b, used_a = [], set(), set()
    for s, b, a in scored:  # distinct scenes across the alternatives, so the options are genuinely different
        if b["product_id"] in used_b or a["product_id"] in used_a:
            continue
        out.append((s, b, a))
        used_b.add(b["product_id"])
        used_a.add(a["product_id"])
        if len(out) >= n:
            break
    return out


def pair_card(b: dict[str, Any], a: dict[str, Any]) -> dict[str, Any]:
    return {"before": b, "after": a, "seasonal_gap_days": doy_gap(_dt(b), _dt(a)), "separation_days": (_dt(a) - _dt(b)).days}


def build_options(windows: list[dict[str, Any]], mode: str, max_pairs: int) -> list[dict[str, Any]]:
    """Selectable scene sets from per-window candidates. Always includes the two-date alternatives; adds a consecutive-dates set for
    multi_period / trend requests (clearly a series of separate pairwise comparisons, not a continuous trend model)."""
    usable = [w for w in windows if w.get("scenes")]
    if len(usable) < 2:
        return []
    opts: list[dict[str, Any]] = []
    for i, (s, b, a) in enumerate(best_pairs(usable[0]["scenes"], usable[-1]["scenes"], 3)):
        opts.append({"id": f"pair{i + 1}", "kind": "two_date", "recommended": False, "score": round(s, 1), "pairs": [pair_card(b, a)]})
    if mode in ("multi_period", "trend") and len(usable) >= 3:
        k = min(max_pairs + 1, len(usable))
        idx = sorted({round(i * (len(usable) - 1) / (k - 1)) for i in range(k)})
        first = min(usable[0]["scenes"], key=_cloud)
        ref = _dt(first)
        chosen = [first]
        for j in idx[1:]:
            pool = usable[j]["scenes"]
            chosen.append(min(pool, key=lambda c: _cloud(c) + 0.2 * doy_gap(_dt(c), ref) + 0.5 * (100 - _cov(c))))
        pairs = []
        for b, a in zip(chosen, chosen[1:]):
            if score_pair(b, a) is None:
                pairs = []
                break
            pairs.append(pair_card(b, a))
        if pairs:
            opts.insert(0, {"id": "series", "kind": "series", "recommended": False, "score": None, "pairs": pairs})
    if opts:
        opts[0]["recommended"] = True
    return opts


def locate_in_bbox(lon: float, lat: float, bbox: list[float]) -> str:
    """Plain-language position of a point inside a bounding box (computed, e.g. 'north-eastern part')."""
    w, s, e, n = bbox
    fx = (lon - w) / (e - w) if e > w else 0.5
    fy = (lat - s) / (n - s) if n > s else 0.5
    ns = "north" if fy > 2 / 3 else "south" if fy < 1 / 3 else ""
    ew = "east" if fx > 2 / 3 else "west" if fx < 1 / 3 else ""
    if not ns and not ew:
        return "central part"
    return (f"{ns}-{ew}ern" if ns and ew else f"{ns or ew}ern") + " part"
