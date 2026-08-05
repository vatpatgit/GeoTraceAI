from uuid import UUID
from pydantic import BaseModel, model_validator

class ImageryRequest(BaseModel):
    """Schema for Sentinel Hub imagery request."""
    region_id: UUID | None = None
    bbox: list[float] | None = None
    date: str
    evalscript: str | None = None
    width: int = 512
    height: int = 512
    format: str = 'image/png'

    @model_validator(mode='after')
    def check_region_or_bbox(self):
        if not self.region_id and not self.bbox:
            raise ValueError("Must provide either region_id or bbox")
        if self.bbox and len(self.bbox) != 4:
            raise ValueError("bbox must contain exactly 4 elements: [min_lng, min_lat, max_lng, max_lat]")
        return self

class CatalogSearchRequest(BaseModel):
    """Schema for Sentinel Hub catalog search request."""
    region_id: UUID | None = None
    bbox: list[float] | None = None
    date_from: str
    date_to: str
    max_cloud_cover: float = 0.3
    limit: int = 10

class CatalogResult(BaseModel):
    """Schema for Sentinel Hub catalog search result."""
    id: str
    datetime: str
    cloud_cover: float
    geometry: dict

class CatalogSearchResponse(BaseModel):
    """Schema for Sentinel Hub catalog search response."""
    results: list[CatalogResult]
    total: int

class StatsRequest(BaseModel):
    """Schema for Sentinel Hub statistics request."""
    region_id: UUID | None = None
    bbox: list[float] | None = None
    date_from: str
    date_to: str
    evalscript: str | None = None
    interval: str = 'P5D'

class StatsDataPoint(BaseModel):
    """Schema for Sentinel Hub statistics data point."""
    date_from: str
    date_to: str
    mean: float
    min: float
    max: float
    stdev: float
    valid_pixels: int

class StatsResponse(BaseModel):
    """Schema for Sentinel Hub statistics response."""
    data: list[StatsDataPoint]
    region_id: UUID | None = None
    band: str
