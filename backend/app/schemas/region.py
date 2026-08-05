from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class RegionCreate(BaseModel):
    """Schema for creating a region."""
    name: str
    description: str | None = None
    geometry: dict
    risk_level: str = 'medium'

class RegionUpdate(BaseModel):
    """Schema for updating a region."""
    name: str | None = None
    description: str | None = None
    risk_level: str | None = None

class RegionResponse(BaseModel):
    """Schema for region response."""
    id: UUID
    name: str
    description: str | None
    geometry: dict | None
    center_lat: float
    center_lng: float
    area_km2: float
    risk_level: str
    metadata_json: dict | None = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class RegionListResponse(BaseModel):
    """Schema for list of regions response."""
    regions: list[RegionResponse]
    total: int
