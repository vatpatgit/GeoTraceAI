from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import ApiModel


class AnalyticsQueryRequest(ApiModel):
    question: str | None = Field(default=None, max_length=1000, description="Natural-language question (mapped to an approved operation)")
    spec: dict[str, Any] | None = Field(default=None, description="Structured query spec (skips language parsing)")
    analysis_id: UUID | None = None
    project_id: UUID | None = None
    narrate: bool = Field(default=True, description="Allow optional LLM narration of the computed result")


class Reference(ApiModel):
    kind: Literal["feature", "analysis", "region"]
    id: UUID
    label: str
    centroid: list[float] | None = None
    analysis_id: UUID | None = None


class AnalyticsQueryResponse(ApiModel):
    question: str | None
    interpreted_as: dict[str, Any]
    operation: str
    understood: bool
    data: dict[str, Any]
    answer: str
    answer_source: Literal["deterministic", "llm_narration"]
    measured_facts: list[str]
    caveats: list[str]
    references: list[Reference]
    suggestions: list[str] = Field(default_factory=list)
