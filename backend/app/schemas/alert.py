from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class AlertConfigCreate(BaseModel):
    """Schema for creating an alert config."""
    region_id: UUID | None = None
    change_type: str | None = None
    threshold: float = Field(default=0.7, ge=0, le=1)

class AlertConfigUpdate(BaseModel):
    """Schema for updating an alert config."""
    region_id: UUID | None = None
    change_type: str | None = None
    threshold: float | None = Field(default=None, ge=0, le=1)
    is_active: bool | None = None

class AlertConfigResponse(BaseModel):
    """Schema for alert config response."""
    id: UUID
    user_id: UUID
    region_id: UUID | None
    change_type: str | None
    threshold: float
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class AlertHistoryResponse(BaseModel):
    """Schema for alert history response."""
    id: UUID
    alert_config_id: UUID
    change_event_id: UUID
    severity: str
    message: str
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class AlertListResponse(BaseModel):
    """Schema for list of alerts response."""
    alerts: list[AlertHistoryResponse]
    total: int
    unread: int
