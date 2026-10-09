"""Configurable, documented severity tiers.

The tier is a *review-priority heuristic* derived from measured area, magnitude and (optionally) proximity to a
monitored boundary. It is not a probability, not a damage estimate and not calibrated against ground truth.
"""
from __future__ import annotations

from app.geo.config import SeverityConfig

TIERS = ("low", "medium", "high", "critical")


def severity_for(area_m2: float, magnitude: float | None, distance_to_boundary_m: float | None,
                 cfg: SeverityConfig) -> tuple[str, list[str]]:
    """Return (tier, human-readable reasons)."""
    if area_m2 >= cfg.area_m2_critical:
        idx, reasons = 3, [f"area {area_m2:,.0f} m2 >= {cfg.area_m2_critical:,.0f} m2 (critical-area band)"]
    elif area_m2 >= cfg.area_m2_high:
        idx, reasons = 2, [f"area {area_m2:,.0f} m2 >= {cfg.area_m2_high:,.0f} m2 (high-area band)"]
    elif area_m2 >= cfg.area_m2_medium:
        idx, reasons = 1, [f"area {area_m2:,.0f} m2 >= {cfg.area_m2_medium:,.0f} m2 (medium-area band)"]
    else:
        idx, reasons = 0, [f"area {area_m2:,.0f} m2 < {cfg.area_m2_medium:,.0f} m2 (low-area band)"]
    if magnitude is not None and magnitude >= cfg.magnitude_escalation and idx < 3:
        idx += 1
        reasons.append(f"magnitude {magnitude:.2f} >= {cfg.magnitude_escalation:.2f}: escalated one tier")
    if (cfg.escalate_on_proximity and distance_to_boundary_m is not None
            and distance_to_boundary_m <= cfg.proximity_escalation_m and idx < 3):
        idx += 1
        reasons.append(f"{distance_to_boundary_m:,.0f} m from a monitored boundary "
                       f"(<= {cfg.proximity_escalation_m:,.0f} m): escalated one tier")
    return TIERS[idx], reasons
