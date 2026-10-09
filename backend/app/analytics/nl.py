"""Deterministic question -> approved-operation parser (no model involved).

The output is a ``QuerySpec`` whose fields are validated by Pydantic; SQL is never produced from text.
"""
from __future__ import annotations

import re
import uuid
from typing import Literal

from pydantic import BaseModel, Field

Operation = Literal[
    "summarize_analysis", "largest_changes", "changes_by_region", "near_boundary", "needs_review", "compare_analyses",
    "vegetation_summary", "built_up_change", "confidence_distribution", "explain_feature", "history", "overview",
]


class QuerySpec(BaseModel):
    operation: Operation
    analysis_id: uuid.UUID | None = None
    compare_to_analysis_id: uuid.UUID | None = None
    feature_id: uuid.UUID | None = None
    region_id: uuid.UUID | None = None
    n: int = Field(default=5, ge=1, le=50)
    category: str | None = Field(default=None, max_length=40)
    min_severity: Literal["low", "medium", "high", "critical"] | None = None
    distance_m: float | None = Field(default=None, gt=0, le=500_000)
    order: Literal["area", "severity"] = "area"


SUGGESTIONS = [
    "What changed between the selected dates?",
    "Summarize the most significant changes in this analysis",
    "Which are the 5 largest changes?",
    "Which high-severity detections are within 1 km of a monitored boundary?",
    "Which detections require human review?",
    "How much vegetation changed?",
    "Compare this analysis with the previous run",
    "Which regions have the largest changed area?",
]

_NUM = r"(\d+(?:\.\d+)?)"


def parse_question(q: str, regions: list[tuple[uuid.UUID, str]]) -> tuple[QuerySpec | None, list[str]]:
    """Returns (spec | None, notes about how the question was interpreted)."""
    t = " " + re.sub(r"\s+", " ", q.lower()).strip() + " "
    notes: list[str] = []
    spec: dict = {}

    region = next(((rid, name) for rid, name in sorted(regions, key=lambda r: -len(r[1])) if name.lower() in t), None)
    if region:
        spec["region_id"] = region[0]
        notes.append(f"region '{region[1]}'")
    m = re.search(r"(?:top|largest|biggest|first)\s+(\d{1,2})|(\d{1,2})\s+(?:largest|biggest|most|highest)", t)
    if m:
        spec["n"] = int(m.group(1) or m.group(2))
    sev = next((s for s in ("critical", "high", "medium", "low") if re.search(rf"\b{s}[- ]?(?:severity|priority)?\b", t) and s in t), None)
    if sev and ("severity" in t or "priority" in t or sev in ("critical",) or f"{sev}-severity" in t or f"{sev} severity" in t):
        spec["min_severity"] = sev
    d = re.search(rf"(?:within|inside|near|closer than|less than)\s+{_NUM}\s*(km|kilomet\w+|m|metres|meters)\b", t)
    if d:
        spec["distance_m"] = float(d.group(1)) * (1000.0 if d.group(2).startswith("k") else 1.0)

    def has(*words: str) -> bool:
        return any(w in t for w in words)

    if has("compare", "previous run", "previous analysis", "versus", " vs ", "since the last", "earlier run"):
        op = "compare_analyses"
    elif has("history", "over time", "trend", "timeline of analyses", "each run"):
        op = "history"
    elif has("require human review", "need review", "needs review", "unreviewed", "to review", "review queue", "human review", "not reviewed"):
        op = "needs_review"
    elif has("boundary", "boundaries", "near ", "within ", "close to") and (d or region or has("monitored")):
        op = "near_boundary"
    elif has("which region", "by region", "per region", "each region", "regions have", "compare regions", "region with") or (region and has("how much", "area", "changed")):
        op = "changes_by_region"
    elif has("built-up", "built up", "builtup", "building", "urban", "construction", "settlement"):
        op = "built_up_change"
    elif has("vegetation", "ndvi", "deforest", "forest", "greenness", "tree"):
        op = "vegetation_summary"
    elif has("confidence", "certain", "reliab", "score distribution", "how sure"):
        op = "confidence_distribution"
    elif has("largest", "biggest", "highest severity", "most severe", "worst", "top ", "most significant"):
        op = "largest_changes"
        if has("severity", "severe", "worst", "critical", "priority"):
            spec["order"] = "severity"
    elif has("what changed", "summar", "overview", "changes between", "significant change", "what happened", "how much changed", "total change", "tell me about"):
        op = "summarize_analysis"
    elif has("explain", "why is this", "this detection", "this change", "selected change"):
        op = "explain_feature"
    else:
        return None, []
    if has("vegetation loss", "vegetation decrease", "deforest"):
        spec["category"] = "vegetation_decrease"
    elif has("vegetation gain", "vegetation increase", "regrowth"):
        spec["category"] = "vegetation_increase"
    elif has("building"):
        spec["category"] = "building_change"
    if op == "near_boundary":
        spec.setdefault("distance_m", 1000.0)
        spec.setdefault("min_severity", "high")
        if "distance_m" not in {k for k in spec if d}:
            notes.append("default distance 1 km")
    return QuerySpec(operation=op, **spec), notes
