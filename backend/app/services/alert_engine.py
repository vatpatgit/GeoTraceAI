import logging
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import AlertConfig, AlertHistory, ChangeEvent, Region

logger = logging.getLogger(__name__)

class AlertEngine:
    """Service to evaluate change events against alert configurations and generate alerts."""
    
    async def evaluate_change_event(self, db: AsyncSession, change_event: ChangeEvent) -> List[AlertHistory]:
        """
        Evaluates a single change event against active alert configs.
        Creates and returns AlertHistory records if criteria are met.
        """
        try:
            # Query active alert configs
            stmt = select(AlertConfig).where(AlertConfig.is_active == True)
            result = await db.execute(stmt)
            configs = result.scalars().all()
            
            # Fetch region for meaningful alert messages (ignore errors if not found)
            region_name = str(change_event.region_id)
            if change_event.region_id:
                try:
                    reg_stmt = select(Region).where(Region.id == change_event.region_id)
                    reg_res = await db.execute(reg_stmt)
                    region = reg_res.scalar_one_or_none()
                    if region and hasattr(region, "name") and region.name:
                        region_name = region.name
                except Exception as e:
                    logger.debug(f"Could not fetch region name for alert: {e}")
            
            created_alerts = []
            for config in configs:
                # Basic matching logic: region_id match (if specified), event_type match (if specified)
                if config.region_id and config.region_id != change_event.region_id:
                    continue
                    
                if hasattr(config, "change_type") and config.change_type and config.change_type != change_event.change_type:
                    continue
                    
                # Threshold check
                threshold = config.threshold
                if change_event.confidence < threshold:
                    continue
                    
                # Determine severity
                if change_event.confidence >= 0.9:
                    severity = "critical"
                elif change_event.confidence >= 0.7:
                    severity = "warning"
                else:
                    severity = "info"
                    
                # Generate human-readable message
                friendly_type = str(change_event.change_type).replace('_', ' ').title() if change_event.change_type else "Change"
                message = f"High confidence {friendly_type.lower()} detected in {region_name} (confidence: {change_event.confidence:.2f})"
                
                # Create AlertHistory record
                alert = AlertHistory(
                    alert_config_id=config.id,
                    change_event_id=change_event.id,
                    severity=severity,
                    message=message,
                    is_read=False
                )
                db.add(alert)
                created_alerts.append(alert)
                
            if created_alerts:
                await db.commit()
                for alert in created_alerts:
                    await db.refresh(alert)
                    
            return created_alerts
            
        except Exception as e:
            logger.error(f"Error evaluating change event in AlertEngine: {e}")
            await db.rollback()
            raise
