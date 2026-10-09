"""Workflow state machine. Transitions are validated here; neither the LLM nor the client can set a state directly."""
from __future__ import annotations

from datetime import datetime, timezone

from app.geoguider.schemas import WState, Workflow

S = WState
ALLOWED: dict[WState, set[WState]] = {
    S.IDLE: {S.INTENT_RESOLVED},
    S.INTENT_RESOLVED: {S.AOI_CONFIRMED, S.FAILED, S.CANCELLED},
    S.AOI_CONFIRMED: {S.SCENES_FOUND, S.INTENT_RESOLVED, S.FAILED, S.CANCELLED},
    S.SCENES_FOUND: {S.SCENES_SELECTED, S.AOI_CONFIRMED, S.FAILED, S.CANCELLED},
    S.SCENES_SELECTED: {S.PREPROCESSING, S.SCENES_FOUND, S.FAILED, S.CANCELLED},
    S.PREPROCESSING: {S.ANALYZING, S.RESULTS_READY, S.FAILED, S.CANCELLED},
    S.ANALYZING: {S.RESULTS_READY, S.FAILED, S.CANCELLED},
    S.RESULTS_READY: {S.COMPLETED},
    S.COMPLETED: set(),
    S.FAILED: {S.SCENES_SELECTED},  # retry with the selection that was kept
    S.CANCELLED: set(),
}
RUNNING = {S.PREPROCESSING, S.ANALYZING}
ACTIVE = {S.INTENT_RESOLVED, S.AOI_CONFIRMED, S.SCENES_FOUND, S.SCENES_SELECTED, S.PREPROCESSING, S.ANALYZING}


class InvalidTransition(Exception):
    pass


def advance(wf: Workflow, new: WState) -> Workflow:
    if new == wf.state:
        return wf
    if new not in ALLOWED[wf.state]:
        raise InvalidTransition(f"{wf.state.value} -> {new.value} is not allowed")
    wf.state = new
    wf.updated_at = datetime.now(timezone.utc).isoformat()
    return wf


def reset() -> Workflow:
    """A new request starts a fresh workflow (a user action, not a transition the model can request mid-flow)."""
    wf = Workflow()
    wf.updated_at = datetime.now(timezone.utc).isoformat()
    return wf
