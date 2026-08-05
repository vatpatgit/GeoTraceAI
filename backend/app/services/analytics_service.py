import logging
from uuid import UUID
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.models import Region, ChangeEvent, AlertHistory

logger = logging.getLogger(__name__)

class AnalyticsService:
    """Service for retrieving system-wide and region-specific analytics."""
    
    async def get_overview(self, db: AsyncSession) -> Dict[str, Any]:
        """Count total regions, change events, area affected, unread alerts, and avg confidence."""
        try:
            # Total regions
            regions_count = await db.scalar(select(func.count(Region.id)))
            
            # Events stats
            events_stats = await db.execute(
                select(
                    func.count(ChangeEvent.id),
                    func.sum(ChangeEvent.area_affected_km2),
                    func.avg(ChangeEvent.confidence)
                )
            )
            total_events, total_area, avg_confidence = events_stats.first()
            
            # Unread alerts
            alerts_count = await db.scalar(
                select(func.count(AlertHistory.id)).where(AlertHistory.is_read == False)
            )
            
            return {
                "total_regions": regions_count or 0,
                "total_change_events": total_events or 0,
                "total_area_affected": total_area or 0.0,
                "avg_confidence": avg_confidence or 0.0,
                "unread_alerts": alerts_count or 0
            }
        except Exception as e:
            logger.error(f"Error in get_overview analytics: {e}")
            raise

    async def get_region_analytics(self, db: AsyncSession, region_id: UUID) -> Dict[str, Any]:
        """Get region-specific stats: events, area, avg confidence, breakdown, and recent events."""
        try:
            # Region stats
            stats = await db.execute(
                select(
                    func.count(ChangeEvent.id),
                    func.sum(ChangeEvent.area_affected_km2),
                    func.avg(ChangeEvent.confidence)
                ).where(ChangeEvent.region_id == region_id)
            )
            total_events, total_area, avg_confidence = stats.first()
            
            # Breakdown by type
            type_breakdown = await db.execute(
                select(
                    ChangeEvent.change_type,
                    func.count(ChangeEvent.id)
                ).where(ChangeEvent.region_id == region_id)
                .group_by(ChangeEvent.change_type)
            )
            breakdown = {row[0]: row[1] for row in type_breakdown.all()}
            
            # Recent 10 events
            recent_events = await db.scalars(
                select(ChangeEvent)
                .where(ChangeEvent.region_id == region_id)
                .order_by(desc(ChangeEvent.created_at))
                .limit(10)
            )
            
            recent_list = []
            for event in recent_events:
                recent_list.append({
                    "id": str(event.id),
                    "change_type": event.change_type,
                    "confidence": event.confidence,
                    "area_affected_km2": event.area_affected_km2,
                    "date": event.created_at.isoformat() if event.created_at else None
                })
                
            return {
                "region_id": str(region_id),
                "total_events": total_events or 0,
                "total_area_affected": total_area or 0.0,
                "avg_confidence": avg_confidence or 0.0,
                "type_breakdown": breakdown,
                "recent_events": recent_list
            }
        except Exception as e:
            logger.error(f"Error in get_region_analytics: {e}")
            raise

    async def get_trends(self, db: AsyncSession, region_id: Optional[UUID] = None, days: int = 30) -> List[Dict[str, Any]]:
        """Get daily aggregated change data for the last N days."""
        try:
            start_date = datetime.now(timezone.utc) - timedelta(days=days)
            
            # Group by exact date string from the timestamp
            stmt = select(
                func.date(ChangeEvent.created_at).label("date"),
                func.count(ChangeEvent.id).label("count"),
                func.sum(ChangeEvent.area_affected_km2).label("area"),
                func.avg(ChangeEvent.confidence).label("avg_confidence")
            ).where(ChangeEvent.created_at >= start_date)
            
            if region_id:
                stmt = stmt.where(ChangeEvent.region_id == region_id)
                
            stmt = stmt.group_by(func.date(ChangeEvent.created_at)).order_by(func.date(ChangeEvent.created_at))
            
            result = await db.execute(stmt)
            
            trends = []
            for row in result.all():
                trends.append({
                    "date": str(row.date),
                    "count": row.count,
                    "area": float(row.area) if row.area is not None else 0.0,
                    "avg_confidence": float(row.avg_confidence) if row.avg_confidence is not None else 0.0
                })
                
            return trends
        except Exception as e:
            logger.error(f"Error in get_trends analytics: {e}")
            raise
