import json
from uuid import UUID
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import io
import logging

from app.database import get_db
from app.models import User, Region
from app.auth.dependencies import require_authenticated_user
from app.services.sentinel_hub import SentinelHubService
from app.schemas.sentinel import (
    ImageryRequest, CatalogSearchRequest, CatalogSearchResponse, CatalogResult,
    StatsRequest, StatsResponse, StatsDataPoint,
)
from app.utils.geojson_utils import bbox_from_geojson

logger = logging.getLogger(__name__)
router = APIRouter()
sentinel_service = SentinelHubService()


async def _resolve_region_bbox(db: AsyncSession, region_id: UUID) -> list[float]:
    """Get bbox [min_lng, min_lat, max_lng, max_lat] from a region's geometry."""
    result = await db.execute(
        select(func.ST_AsGeoJSON(Region.geometry)).where(Region.id == region_id)
    )
    geojson_str = result.scalar_one_or_none()
    if not geojson_str:
        raise HTTPException(status_code=404, detail="Region not found")
    geojson = json.loads(geojson_str)
    return bbox_from_geojson(geojson)


async def _resolve_region_geometry(db: AsyncSession, region_id: UUID) -> dict:
    """Get GeoJSON geometry dict from a region."""
    result = await db.execute(
        select(func.ST_AsGeoJSON(Region.geometry)).where(Region.id == region_id)
    )
    geojson_str = result.scalar_one_or_none()
    if not geojson_str:
        raise HTTPException(status_code=404, detail="Region not found")
    return json.loads(geojson_str)


@router.post("/imagery")
async def get_imagery(
    body: ImageryRequest,
    current_user: User = Depends(require_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch satellite imagery via Sentinel Hub Process API."""
    bbox = body.bbox
    if body.region_id and not bbox:
        bbox = await _resolve_region_bbox(db, body.region_id)
    if not bbox:
        raise HTTPException(status_code=400, detail="Must provide region_id or bbox")
    
    try:
        image_bytes = await sentinel_service.get_imagery(
            bbox=bbox,
            date=body.date,
            evalscript=body.evalscript,
            width=body.width,
            height=body.height,
            format=body.format,
        )
        return StreamingResponse(
            io.BytesIO(image_bytes),
            media_type=body.format,
            headers={"Content-Disposition": f"inline; filename=imagery_{body.date}.png"},
        )
    except Exception as e:
        logger.error(f"Sentinel Hub imagery error: {e}")
        raise HTTPException(status_code=502, detail=f"Sentinel Hub error: {str(e)}")


@router.post("/search", response_model=CatalogSearchResponse)
async def search_catalog(
    body: CatalogSearchRequest,
    current_user: User = Depends(require_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    """Search for available satellite images via Catalog API."""
    bbox = body.bbox
    if body.region_id and not bbox:
        bbox = await _resolve_region_bbox(db, body.region_id)
    if not bbox:
        raise HTTPException(status_code=400, detail="Must provide region_id or bbox")
    
    try:
        raw = await sentinel_service.search_catalog(
            bbox=bbox,
            date_from=body.date_from,
            date_to=body.date_to,
            max_cloud_cover=body.max_cloud_cover,
            limit=body.limit,
        )
        features = raw.get("features", [])
        results = []
        for f in features:
            props = f.get("properties", {})
            results.append(CatalogResult(
                id=f.get("id", ""),
                datetime=props.get("datetime", ""),
                cloud_cover=props.get("eo:cloud_cover", 0.0),
                geometry=f.get("geometry", {}),
            ))
        return CatalogSearchResponse(results=results, total=len(results))
    except Exception as e:
        logger.error(f"Sentinel Hub catalog error: {e}")
        raise HTTPException(status_code=502, detail=f"Sentinel Hub error: {str(e)}")


@router.post("/stats", response_model=StatsResponse)
async def get_stats(
    body: StatsRequest,
    current_user: User = Depends(require_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    """Get statistics via Sentinel Hub Statistical API."""
    geometry = None
    if body.region_id:
        geometry = await _resolve_region_geometry(db, body.region_id)
    elif body.bbox:
        # Convert bbox to a polygon geometry
        min_lng, min_lat, max_lng, max_lat = body.bbox
        geometry = {
            "type": "Polygon",
            "coordinates": [[
                [min_lng, min_lat], [max_lng, min_lat],
                [max_lng, max_lat], [min_lng, max_lat],
                [min_lng, min_lat],
            ]]
        }
    if not geometry:
        raise HTTPException(status_code=400, detail="Must provide region_id or bbox")
    
    try:
        raw = await sentinel_service.get_statistics(
            geometry=geometry,
            date_from=body.date_from,
            date_to=body.date_to,
            evalscript=body.evalscript,
            interval=body.interval,
        )
        # Parse Sentinel Hub stats response
        data_points = []
        for interval_data in raw.get("data", []):
            interval_info = interval_data.get("interval", {})
            outputs = interval_data.get("outputs", {})
            ndvi_stats = outputs.get("ndvi", {}).get("bands", {}).get("B0", {}).get("stats", {})
            if not ndvi_stats:
                # Try first output key
                for output_key, output_val in outputs.items():
                    bands = output_val.get("bands", {})
                    for band_key, band_val in bands.items():
                        ndvi_stats = band_val.get("stats", {})
                        break
                    break
            data_points.append(StatsDataPoint(
                date_from=interval_info.get("from", ""),
                date_to=interval_info.get("to", ""),
                mean=ndvi_stats.get("mean", 0.0),
                min=ndvi_stats.get("min", 0.0),
                max=ndvi_stats.get("max", 0.0),
                stdev=ndvi_stats.get("stDev", 0.0),
                valid_pixels=ndvi_stats.get("sampleCount", 0),
            ))
        return StatsResponse(data=data_points, region_id=body.region_id, band="ndvi")
    except Exception as e:
        logger.error(f"Sentinel Hub stats error: {e}")
        raise HTTPException(status_code=502, detail=f"Sentinel Hub error: {str(e)}")


@router.get("/ndvi/{region_id}", response_model=StatsResponse)
async def get_ndvi(
    region_id: UUID,
    current_user: User = Depends(require_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    """Convenience: Get last 30 days of NDVI stats for a region."""
    geometry = await _resolve_region_geometry(db, region_id)
    now = datetime.now(timezone.utc)
    date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = now.strftime("%Y-%m-%d")
    
    try:
        raw = await sentinel_service.get_statistics(
            geometry=geometry,
            date_from=date_from,
            date_to=date_to,
            evalscript=None,
            interval="P5D",
        )
        data_points = []
        for interval_data in raw.get("data", []):
            interval_info = interval_data.get("interval", {})
            outputs = interval_data.get("outputs", {})
            ndvi_stats = {}
            for output_key, output_val in outputs.items():
                for band_key, band_val in output_val.get("bands", {}).items():
                    ndvi_stats = band_val.get("stats", {})
                    break
                break
            data_points.append(StatsDataPoint(
                date_from=interval_info.get("from", ""),
                date_to=interval_info.get("to", ""),
                mean=ndvi_stats.get("mean", 0.0),
                min=ndvi_stats.get("min", 0.0),
                max=ndvi_stats.get("max", 0.0),
                stdev=ndvi_stats.get("stDev", 0.0),
                valid_pixels=ndvi_stats.get("sampleCount", 0),
            ))
        return StatsResponse(data=data_points, region_id=region_id, band="ndvi")
    except Exception as e:
        logger.error(f"NDVI fetch error: {e}")
        raise HTTPException(status_code=502, detail=f"Sentinel Hub error: {str(e)}")
