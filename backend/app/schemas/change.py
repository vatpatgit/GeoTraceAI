from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class ChangeEventResponse(BaseModel):
    """Schema for change event response."""
    id: UUID
    region_id: UUID
    change_type: str
    confidence: float
    area_affected_km2: float | None = None
    detected_at: datetime
    source: str
    ndvi_before: float | None = None
    ndvi_after: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ChangeEventCreate(BaseModel):
    """Schema for creating a change event."""
    region_id: UUID
    change_type: str
    confidence: float = Field(..., ge=0, le=1)
    area_affected_km2: float | None = None
    detected_at: datetime | None = None
    geometry: dict | None = None
    source: str = 'sentinel-2'
    ndvi_before: float | None = None
    ndvi_after: float | None = None

class ChangeSummary(BaseModel):
    """Schema for change event summary."""
    total_events: int
    total_area_affected_km2: float
    by_type: dict[str, int]
    by_region: dict[str, int]
    avg_confidence: float

class ChangeTimelinePoint(BaseModel):
    """Schema for change timeline point."""
    date: str
    count: int
    area_km2: float
    avg_confidence: float

class ChangeTimelineResponse(BaseModel):
    """Schema for change timeline response."""
    data: list[ChangeTimelinePoint]
    region_id: UUID | None = None
    change_type: str | None = None
