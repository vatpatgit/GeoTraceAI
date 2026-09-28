import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date

from app.database import get_db
from app.models import ChangeEvent, User
from app.schemas import ChangeEventCreate, ChangeEventResponse, ChangeSummary, ChangeTimelinePoint, ChangeTimelineResponse
from app.auth.dependencies import require_authenticated_user, require_admin
from app.services.alert_engine import AlertEngine

router = APIRouter()

@router.get("/summary", response_model=ChangeSummary)
async def get_summary(
    region_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_user)
):
    """Aggregated summary."""
    query = select(ChangeEvent)
    
    if region_id:
        query = query.where(ChangeEvent.region_id == region_id)
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.where(ChangeEvent.detected_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.where(ChangeEvent.detected_at <= dt_to)
        except ValueError:
            pass

    # Basic stats
    stats_query = select(
        func.count().label("total_events"),
        func.coalesce(func.sum(ChangeEvent.area_affected_km2), 0).label("total_area"),
        func.coalesce(func.avg(ChangeEvent.confidence), 0).label("avg_conf")
    ).select_from(query.subquery())
    
    stats_res = await db.execute(stats_query)
    stats = stats_res.first()
    
    total_events = stats.total_events
    total_area_affected_km2 = stats.total_area
    avg_confidence = stats.avg_conf

    # By type
    type_query = select(
        ChangeEvent.change_type,
        func.count().label("count")
    ).select_from(query.subquery()).group_by(ChangeEvent.change_type)
    type_res = await db.execute(type_query)
    by_type = {row.change_type: row.count for row in type_res.all()}

    # By region
    region_query = select(
        ChangeEvent.region_id,
        func.count().label("count")
    ).select_from(query.subquery()).group_by(ChangeEvent.region_id)
    region_res = await db.execute(region_query)
    by_region = {str(row.region_id): row.count for row in region_res.all()}

    return ChangeSummary(
        total_events=total_events,
        total_area_affected_km2=total_area_affected_km2,
        by_type=by_type,
        by_region=by_region,
        avg_confidence=avg_confidence
    )

@router.get("/timeline", response_model=ChangeTimelineResponse)
async def get_timeline(
    region_id: str | None = None,
    change_type: str | None = None,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_user)
):
    """Time-series data."""
    query = select(
        cast(ChangeEvent.detected_at, Date).label("date"),
        func.count().label("count"),
        func.coalesce(func.sum(ChangeEvent.area_affected_km2), 0).label("area"),
        func.coalesce(func.avg(ChangeEvent.confidence), 0).label("conf")
    )
    
    if region_id:
        query = query.where(ChangeEvent.region_id == region_id)
    if change_type:
        query = query.where(ChangeEvent.change_type == change_type)
        
    query = query.group_by(cast(ChangeEvent.detected_at, Date)).order_by(cast(ChangeEvent.detected_at, Date))
    
    result = await db.execute(query)
    rows = result.all()
    
    data = []
    for r in rows:
        data.append(ChangeTimelinePoint(
            date=r.date.isoformat(),
            count=r.count,
            area_km2=r.area,
            avg_confidence=r.conf
        ))
        
    return ChangeTimelineResponse(
        data=data,
        region_id=region_id,
        change_type=change_type
    )

@router.get("/", response_model=list[ChangeEventResponse])
async def list_changes(
    region_id: str | None = None,
    change_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_confidence: float | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_user)
):
    """List change events with filters."""
    query = select(
        ChangeEvent,
        func.ST_AsGeoJSON(ChangeEvent.geometry).label('geojson_geom')
    )
    
    if region_id:
        query = query.where(ChangeEvent.region_id == region_id)
    if change_type:
        query = query.where(ChangeEvent.change_type == change_type)
    if min_confidence is not None:
        query = query.where(ChangeEvent.confidence >= min_confidence)
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.where(ChangeEvent.detected_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.where(ChangeEvent.detected_at <= dt_to)
        except ValueError:
            pass
            
    query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    rows = result.all()
    
    events = []
    for event, geojson_geom in rows:
        event_dict = {
            "id": event.id,
            "region_id": event.region_id,
            "change_type": event.change_type,
            "confidence": event.confidence,
            "area_affected_km2": event.area_affected_km2,
            "detected_at": event.detected_at,
            "source": event.source,
            "ndvi_before": event.ndvi_before,
            "ndvi_after": event.ndvi_after,
            "metadata_json": event.metadata_json,
            "created_at": event.created_at,
            "geometry": json.loads(geojson_geom) if geojson_geom else None
        }
        events.append(event_dict)
        
    return events

@router.get("/{change_id}", response_model=ChangeEventResponse)
async def get_change(change_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_authenticated_user)):
    """Get single change event."""
    result = await db.execute(
        select(
            ChangeEvent,
            func.ST_AsGeoJSON(ChangeEvent.geometry).label('geojson_geom')
        ).where(ChangeEvent.id == change_id)
    )
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change event not found")
        
    event, geojson_geom = row
    event_dict = {
        "id": event.id,
        "region_id": event.region_id,
        "change_type": event.change_type,
        "confidence": event.confidence,
        "area_affected_km2": event.area_affected_km2,
        "detected_at": event.detected_at,
        "source": event.source,
        "ndvi_before": event.ndvi_before,
        "ndvi_after": event.ndvi_after,
        "metadata_json": event.metadata_json,
        "created_at": event.created_at,
        "geometry": json.loads(geojson_geom) if geojson_geom else None
    }
    return event_dict

@router.post("/", response_model=ChangeEventResponse, status_code=status.HTTP_201_CREATED)
async def create_change(body: ChangeEventCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    """Create change event."""
    geom = None
    if body.geometry:
        geom = func.ST_GeomFromGeoJSON(json.dumps(body.geometry))
        
    new_event = ChangeEvent(
        region_id=body.region_id,
        change_type=body.change_type,
        confidence=body.confidence,
        area_affected_km2=body.area_affected_km2,
        detected_at=body.detected_at or func.now(),
        source=body.source,
        ndvi_before=body.ndvi_before,
        ndvi_after=body.ndvi_after,
        geometry=geom
    )
    
    db.add(new_event)
    await db.commit()
    await db.refresh(new_event)
    
    # Call AlertEngine
    engine = AlertEngine()
    await engine.evaluate_change_event(db, new_event)
    
    # Fetch for response
    result = await db.execute(
        select(
            ChangeEvent,
            func.ST_AsGeoJSON(ChangeEvent.geometry).label('geojson_geom')
        ).where(ChangeEvent.id == new_event.id)
    )
    row = result.first()
    event, geojson_geom = row
    event_dict = {
        "id": event.id,
        "region_id": event.region_id,
        "change_type": event.change_type,
        "confidence": event.confidence,
        "area_affected_km2": event.area_affected_km2,
        "detected_at": event.detected_at,
        "source": event.source,
        "ndvi_before": event.ndvi_before,
        "ndvi_after": event.ndvi_after,
        "metadata_json": event.metadata_json,
        "created_at": event.created_at,
        "geometry": json.loads(geojson_geom) if geojson_geom else None
    }
    return event_dict
