from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import User, Region, ChangeEvent, AlertConfig, AlertHistory
from app.auth.dependencies import get_current_user
from app.schemas.analytics import OverviewMetrics, RegionAnalytics, TrendPoint, TrendsResponse

router = APIRouter()


@router.get("/overview", response_model=OverviewMetrics)
async def get_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard overview metrics."""
    # Count regions
    total_regions = await db.scalar(select(func.count(Region.id))) or 0
    
    # Change event stats
    result = await db.execute(
        select(
            func.count(ChangeEvent.id),
            func.coalesce(func.sum(ChangeEvent.area_affected_km2), 0.0),
            func.coalesce(func.avg(ChangeEvent.confidence), 0.0),
        )
    )
    row = result.one()
    total_events = row[0] or 0
    total_area = float(row[1])
    avg_confidence = float(row[2])
    
    # Alert counts
    active_alerts = await db.scalar(
        select(func.count(AlertConfig.id)).where(AlertConfig.is_active == True)
    ) or 0
    
    unread_alerts = await db.scalar(
        select(func.count(AlertHistory.id)).where(AlertHistory.is_read == False)
    ) or 0
    
    return OverviewMetrics(
        total_regions=total_regions,
        total_change_events=total_events,
        total_area_affected_km2=total_area,
        active_alerts=active_alerts,
        unread_alerts=unread_alerts,
        avg_confidence=round(avg_confidence, 4),
    )


@router.get("/region/{region_id}", response_model=RegionAnalytics)
async def get_region_analytics(
    region_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get analytics for a specific region."""
    # Verify region exists
    region = await db.get(Region, region_id)
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")
    
    # Stats
    result = await db.execute(
        select(
            func.count(ChangeEvent.id),
            func.coalesce(func.sum(ChangeEvent.area_affected_km2), 0.0),
            func.coalesce(func.avg(ChangeEvent.confidence), 0.0),
        ).where(ChangeEvent.region_id == region_id)
    )
    row = result.one()
    
    # Breakdown by type
    type_result = await db.execute(
        select(ChangeEvent.change_type, func.count(ChangeEvent.id))
        .where(ChangeEvent.region_id == region_id)
        .group_by(ChangeEvent.change_type)
    )
    by_type = {r[0]: r[1] for r in type_result.all()}
    
    # Recent events
    recent_result = await db.execute(
        select(ChangeEvent)
        .where(ChangeEvent.region_id == region_id)
        .order_by(ChangeEvent.detected_at.desc())
        .limit(10)
    )
    recent_events = [
        {
            "id": str(e.id),
            "change_type": e.change_type,
            "confidence": e.confidence,
            "area_affected_km2": e.area_affected_km2,
            "detected_at": e.detected_at.isoformat() if e.detected_at else None,
        }
        for e in recent_result.scalars().all()
    ]
    
    return RegionAnalytics(
        region_id=region_id,
        region_name=region.name,
        total_events=row[0] or 0,
        total_area_affected_km2=float(row[1]),
        avg_confidence=round(float(row[2]), 4),
        risk_level=region.risk_level,
        by_type=by_type,
        recent_events=recent_events,
    )


@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    region_id: UUID | None = Query(None),
    days: int = Query(30, ge=1, le=365),
    metric: str = Query("changes"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get trend data for charts."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import Date, cast
    
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    stmt = select(
        cast(ChangeEvent.detected_at, Date).label("date"),
        func.count(ChangeEvent.id).label("count"),
        func.coalesce(func.sum(ChangeEvent.area_affected_km2), 0.0).label("area"),
        func.coalesce(func.avg(ChangeEvent.confidence), 0.0).label("avg_conf"),
    ).where(ChangeEvent.detected_at >= start_date)
    
    if region_id:
        stmt = stmt.where(ChangeEvent.region_id == region_id)
    
    stmt = stmt.group_by(cast(ChangeEvent.detected_at, Date)).order_by(cast(ChangeEvent.detected_at, Date))
    
    result = await db.execute(stmt)
    
    data = []
    for row in result.all():
        value = float(row.count) if metric == "changes" else float(row.area) if metric == "area" else float(row.avg_conf)
        data.append(TrendPoint(date=str(row.date), value=value))
    
    return TrendsResponse(metric=metric, data=data, region_id=region_id)
