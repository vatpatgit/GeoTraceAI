import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Region, User
from app.schemas import RegionCreate, RegionUpdate, RegionResponse, RegionListResponse
from app.auth.dependencies import require_authenticated_user, require_admin
from app.utils.geojson_utils import validate_geojson_polygon, calculate_area_km2

router = APIRouter()

@router.get("/", response_model=RegionListResponse)
async def list_regions(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_authenticated_user)):
    """List all regions."""
    result = await db.execute(
        select(
            Region, 
            func.ST_AsGeoJSON(Region.geometry).label('geojson_geom')
        )
    )
    rows = result.all()
    
    regions = []
    for region, geojson_geom in rows:
        region_dict = {
            "id": region.id,
            "name": region.name,
            "description": region.description,
            "center_lat": region.center_lat,
            "center_lng": region.center_lng,
            "area_km2": region.area_km2,
            "risk_level": region.risk_level,
            "metadata_json": region.metadata_json,
            "created_at": region.created_at,
            "geometry": json.loads(geojson_geom) if geojson_geom else None
        }
        regions.append(region_dict)
    
    return RegionListResponse(regions=regions, total=len(regions))

@router.get("/{region_id}", response_model=RegionResponse)
async def get_region(region_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_authenticated_user)):
    """Get single region by UUID."""
    result = await db.execute(
        select(
            Region, 
            func.ST_AsGeoJSON(Region.geometry).label('geojson_geom')
        ).where(Region.id == region_id)
    )
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found")
        
    region, geojson_geom = row
    
    region_dict = {
        "id": region.id,
        "name": region.name,
        "description": region.description,
        "center_lat": region.center_lat,
        "center_lng": region.center_lng,
        "area_km2": region.area_km2,
        "risk_level": region.risk_level,
        "metadata_json": region.metadata_json,
        "created_at": region.created_at,
        "geometry": json.loads(geojson_geom) if geojson_geom else None
    }
    return region_dict

@router.post("/", response_model=RegionResponse, status_code=status.HTTP_201_CREATED)
async def create_region(body: RegionCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    """Create a new region."""
    is_valid = validate_geojson_polygon(body.geometry)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid GeoJSON Polygon")
        
    coords = body.geometry.get("coordinates", [])[0]
    lats = [c[1] for c in coords]
    lngs = [c[0] for c in coords]
    center_lat = sum(lats) / len(lats)
    center_lng = sum(lngs) / len(lngs)
    
    area = calculate_area_km2(body.geometry)
    
    new_region = Region(
        name=body.name,
        description=body.description,
        center_lat=center_lat,
        center_lng=center_lng,
        area_km2=area,
        risk_level=body.risk_level,
        geometry=func.ST_GeomFromGeoJSON(json.dumps(body.geometry))
    )
    db.add(new_region)
    await db.commit()
    
    result = await db.execute(
        select(
            Region, 
            func.ST_AsGeoJSON(Region.geometry).label('geojson_geom')
        ).where(Region.id == new_region.id)
    )
    row = result.first()
    region, geojson_geom = row
    
    region_dict = {
        "id": region.id,
        "name": region.name,
        "description": region.description,
        "center_lat": region.center_lat,
        "center_lng": region.center_lng,
        "area_km2": region.area_km2,
        "risk_level": region.risk_level,
        "metadata_json": region.metadata_json,
        "created_at": region.created_at,
        "geometry": json.loads(geojson_geom) if geojson_geom else None
    }
    return region_dict

@router.put("/{region_id}", response_model=RegionResponse)
async def update_region(region_id: str, body: RegionUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    """Update a region."""
    result = await db.execute(select(Region).where(Region.id == region_id))
    region = result.scalar_one_or_none()
    
    if not region:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found")
        
    if body.name is not None:
        region.name = body.name
    if body.description is not None:
        region.description = body.description
    if body.risk_level is not None:
        region.risk_level = body.risk_level
        
    await db.commit()
    
    result = await db.execute(
        select(
            Region, 
            func.ST_AsGeoJSON(Region.geometry).label('geojson_geom')
        ).where(Region.id == region_id)
    )
    row = result.first()
    region_obj, geojson_geom = row
    
    region_dict = {
        "id": region_obj.id,
        "name": region_obj.name,
        "description": region_obj.description,
        "center_lat": region_obj.center_lat,
        "center_lng": region_obj.center_lng,
        "area_km2": region_obj.area_km2,
        "risk_level": region_obj.risk_level,
        "metadata_json": region_obj.metadata_json,
        "created_at": region_obj.created_at,
        "geometry": json.loads(geojson_geom) if geojson_geom else None
    }
    return region_dict

@router.delete("/{region_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_region(region_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    """Delete a region."""
    result = await db.execute(select(Region).where(Region.id == region_id))
    region = result.scalar_one_or_none()
    
    if not region:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found")
        
    await db.delete(region)
    await db.commit()
