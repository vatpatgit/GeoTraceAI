from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import AlertConfig, AlertHistory, User
from app.schemas import AlertConfigCreate, AlertConfigUpdate, AlertConfigResponse, AlertHistoryResponse, AlertListResponse
from app.auth.dependencies import get_current_user

router = APIRouter()

@router.get("/config", response_model=list[AlertConfigResponse])
async def list_alert_configs(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List user's alert configs."""
    result = await db.execute(select(AlertConfig).where(AlertConfig.user_id == current_user.id))
    return list(result.scalars().all())

@router.post("/config", response_model=AlertConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_config(body: AlertConfigCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Create config for current user."""
    new_config = AlertConfig(
        user_id=current_user.id,
        region_id=body.region_id,
        change_type=body.change_type,
        threshold=body.threshold,
        is_active=True
    )
    db.add(new_config)
    await db.commit()
    await db.refresh(new_config)
    return new_config

@router.put("/config/{config_id}", response_model=AlertConfigResponse)
async def update_alert_config(config_id: str, body: AlertConfigUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Update config."""
    result = await db.execute(select(AlertConfig).where(AlertConfig.id == config_id))
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert config not found")
    if config.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        
    if body.region_id is not None:
        config.region_id = body.region_id
    if body.change_type is not None:
        config.change_type = body.change_type
    if body.threshold is not None:
        config.threshold = body.threshold
    if body.is_active is not None:
        config.is_active = body.is_active
        
    await db.commit()
    await db.refresh(config)
    return config

@router.delete("/config/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_config(config_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete config."""
    result = await db.execute(select(AlertConfig).where(AlertConfig.id == config_id))
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert config not found")
    if config.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        
    await db.delete(config)
    await db.commit()

@router.get("/history", response_model=AlertListResponse)
async def list_alert_history(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """All alerts for user."""
    query = (
        select(AlertHistory)
        .join(AlertConfig, AlertHistory.alert_config_id == AlertConfig.id)
        .where(AlertConfig.user_id == current_user.id)
    )
    
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0
    
    unread_query = query.where(AlertHistory.is_read == False)
    unread_result = await db.execute(select(func.count()).select_from(unread_query.subquery()))
    unread = unread_result.scalar() or 0
    
    result = await db.execute(query.order_by(AlertHistory.created_at.desc()).limit(limit).offset(offset))
    alerts = result.scalars().all()
    
    return AlertListResponse(alerts=list(alerts), total=total, unread=unread)

@router.get("/", response_model=AlertListResponse)
async def list_active_alerts(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List active (unread) alerts for user."""
    query = (
        select(AlertHistory)
        .join(AlertConfig, AlertHistory.alert_config_id == AlertConfig.id)
        .where(AlertConfig.user_id == current_user.id)
        .where(AlertHistory.is_read == False)
    )
    
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0
    
    result = await db.execute(query.order_by(AlertHistory.created_at.desc()).limit(limit).offset(offset))
    alerts = result.scalars().all()
    
    return AlertListResponse(alerts=list(alerts), total=total, unread=total)

@router.post("/{alert_id}/dismiss", response_model=AlertHistoryResponse)
async def dismiss_alert(alert_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Mark alert as read."""
    result = await db.execute(
        select(AlertHistory)
        .join(AlertConfig, AlertHistory.alert_config_id == AlertConfig.id)
        .where(AlertHistory.id == alert_id)
        .where(AlertConfig.user_id == current_user.id)
    )
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found or not authorized")
        
    alert.is_read = True
    await db.commit()
    await db.refresh(alert)
    return alert
