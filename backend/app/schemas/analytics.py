from uuid import UUID
from pydantic import BaseModel
from .change import ChangeEventResponse

class OverviewMetrics(BaseModel):
    """Schema for overview metrics."""
    total_regions: int
    total_change_events: int
    total_area_affected_km2: float
    active_alerts: int
    unread_alerts: int
    avg_confidence: float

class RegionAnalytics(BaseModel):
    """Schema for region analytics."""
    region_id: UUID
    region_name: str
    total_events: int
    total_area_affected_km2: float
    avg_confidence: float
    risk_level: str
    by_type: dict[str, int]
    recent_events: list[ChangeEventResponse]

class TrendPoint(BaseModel):
    """Schema for a point in a trend line."""
    date: str
    value: float
    label: str | None = None

class TrendsResponse(BaseModel):
    """Schema for trends response."""
    metric: str
    data: list[TrendPoint]
    region_id: UUID | None = None
