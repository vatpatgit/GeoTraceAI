"""Validated structures: the intent extracted from a message, the workflow state, and the chat API payloads."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.common import ApiModel, UtcDateTime

_CTRL = re.compile(r"[\x00-\x1f\x7f]")

IntentType = Literal["change_analysis", "compare_dates", "find_imagery", "weather_alerts", "explain_results", "ask_results", "export_results",
                     "navigate", "help", "confirm", "cancel", "unknown"]

# Frontend route KEYS (the UI maps a key to its own path); anything else is rejected, so a message can never cause an arbitrary redirect.
ROUTES: dict[str, str] = {
    "dashboard": "Overview", "map": "Globe / map", "analyses": "Analyses", "new_analysis": "New analysis", "regions": "Monitored regions",
    "changes": "Change intelligence", "alerts": "Alerts", "analytics": "Analytics", "reports": "Reports", "settings": "Settings", "image_compare": "Image compare",
}
PANELS = ("quick", "layers")


class Intent(ApiModel):
    intent_type: IntentType = "unknown"
    location_query: str | None = Field(default=None, max_length=120)
    use_current_area: bool = False
    start_date: date | None = None
    end_date: date | None = None
    period_label: str | None = Field(default=None, max_length=80)
    analysis_mode: Literal["two_date", "multi_period", "trend"] | None = None
    preferred_sensor: str | None = Field(default="sentinel-2", max_length=40)
    cloud_cover_limit: float | None = Field(default=None, ge=0, le=100)
    requested_outputs: list[str] = Field(default_factory=list, max_length=8)
    export_format: Literal["geojson", "gpkg", "csv", "pdf"] | None = None
    navigate_to: str | None = None
    panel: str | None = None
    question: str | None = Field(default=None, max_length=500)
    reply: str | None = Field(default=None, max_length=800)  # LLM prose for help / general questions only; never carries data
    requires_clarification: bool = False
    clarification_question: str | None = Field(default=None, max_length=300)
    proposed_actions: list[str] = Field(default_factory=list, max_length=6)
    source: Literal["llm", "rules"] = "rules"

    @field_validator("location_query", "question", "reply", "clarification_question", "period_label", mode="before")
    @classmethod
    def _clean(cls, v):
        if v is None:
            return None
        v = _CTRL.sub(" ", str(v)).strip()
        return v or None

    @field_validator("navigate_to")
    @classmethod
    def _route(cls, v):
        if v is not None and v not in ROUTES:
            raise ValueError(f"unknown route {v!r}")
        return v

    @field_validator("panel")
    @classmethod
    def _panel(cls, v):
        if v is not None and v not in PANELS:
            raise ValueError(f"unknown panel {v!r}")
        return v

    @model_validator(mode="after")
    def _dates(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date is after end_date")
        today = datetime.now(timezone.utc).date()
        if self.end_date and self.end_date > today:
            self.end_date = today
        return self


class WState(str, Enum):
    IDLE = "IDLE"
    INTENT_RESOLVED = "INTENT_RESOLVED"
    AOI_CONFIRMED = "AOI_CONFIRMED"
    SCENES_FOUND = "SCENES_FOUND"
    SCENES_SELECTED = "SCENES_SELECTED"
    PREPROCESSING = "PREPROCESSING"
    ANALYZING = "ANALYZING"
    RESULTS_READY = "RESULTS_READY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Option(ApiModel):
    id: str = Field(max_length=60)
    label: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=400)
    payload: dict[str, Any] = Field(default_factory=dict)


class Pending(ApiModel):
    """What the assistant is waiting for. Option ids are validated against this record, never taken on trust from the client."""
    id: str
    kind: Literal["location", "period", "place_choice", "aoi_size", "mode_choice", "scene_choice", "confirm_plan", "area_on_map"]
    prompt: str
    options: list[Option] = Field(default_factory=list)


class Workflow(ApiModel):
    state: WState = WState.IDLE
    intent: dict[str, Any] | None = None
    place: dict[str, Any] | None = None  # resolved place: name, lat, lon, bbox
    places: list[dict[str, Any]] = Field(default_factory=list)
    aoi: dict[str, Any] | None = None  # persisted AOI: id, name, bbox, area_km2
    period: dict[str, Any] | None = None  # start, end, label
    mode: Literal["two_date", "multi_period", "trend"] = "two_date"
    max_cloud: float = 30.0
    coverage: list[dict[str, Any]] = Field(default_factory=list)
    failed_windows: int = 0
    pair_options: list[dict[str, Any]] = Field(default_factory=list)  # candidate scene sets the user may choose between
    selection: dict[str, Any] | None = None  # the chosen option (a list of consecutive pairs)
    job_ids: list[str] = Field(default_factory=list)
    pending: Pending | None = None
    results_announced: bool = False
    last_analysis_id: str | None = None
    error: str | None = None
    updated_at: str | None = None


class UiContext(ApiModel):
    page: str | None = Field(default=None, max_length=60)
    active_analysis_id: UUID | None = None
    drawn_bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    active_aoi_id: UUID | None = None


class ChoicePick(ApiModel):
    pending_id: str = Field(max_length=60)
    option_id: str = Field(max_length=60)


class ChatRequest(ApiModel):
    conversation_id: UUID | None = None
    message: str | None = Field(default=None, max_length=4000)
    choice: ChoicePick | None = None
    ui: UiContext = Field(default_factory=UiContext)

    @model_validator(mode="after")
    def _one(self):
        if not (self.message and self.message.strip()) and self.choice is None:
            raise ValueError("Provide a message or a choice.")
        return self


class MessageOut(ApiModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    created_at: UtcDateTime


class WorkflowOut(ApiModel):
    conversation_id: UUID
    state: WState
    pending: Pending | None = None
    job_ids: list[str] = Field(default_factory=list)
    jobs: list[dict[str, Any]] = Field(default_factory=list)  # real analysis-job states
    cancellable: bool = False
    aoi: dict[str, Any] | None = None
    period: dict[str, Any] | None = None
    error: str | None = None


class ChatResponse(ApiModel):
    conversation_id: UUID
    messages: list[MessageOut]  # the user's message (if any) and the assistant's reply, in order
    workflow: WorkflowOut
    suggestions: list[str] = Field(default_factory=list)


class StatusOut(ApiModel):
    enabled: bool
    llm: dict[str, Any]
    geocoder: dict[str, Any]
    satellite: dict[str, Any]
    weather: dict[str, Any]
    model: dict[str, Any]
    capabilities: dict[str, bool]


class ConversationOut(ApiModel):
    id: UUID
    title: str
    updated_at: UtcDateTime
    messages: list[MessageOut] = Field(default_factory=list)
    workflow: WorkflowOut | None = None
