from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin, require_authenticated_user
from app.database import get_db
from app.layers import registry
from app.models import LayerCatalog, User
from app.schemas.common import ApiModel, UtcDateTime
from typing import Any

router = APIRouter()
STALE = timedelta(hours=6)


class LayerOut(ApiModel):
    id: str
    name: str
    group: str
    provider: str
    data_type: str
    render_type: str
    crs: str
    tile_url: str | None
    attribution: str
    limitations: list[str]
    legend: dict[str, Any] | None
    temporal: dict[str, Any] | None
    default_visible: bool
    default_opacity: float
    availability: str
    availability_detail: str | None
    last_checked_at: UtcDateTime | None
    last_updated_at: UtcDateTime | None
    max_zoom: int | None = None


def _out(r: LayerCatalog) -> LayerOut:
    cfg = r.config or {}
    return LayerOut(id=r.id, name=r.name, group=r.group, provider=r.provider, data_type=r.data_type, render_type=r.render_type, crs=r.crs,
                    tile_url=cfg.get("tile_url"), attribution=r.attribution, limitations=r.limitations or [], legend=r.legend, temporal=r.temporal,
                    default_visible=r.default_visible, default_opacity=r.default_opacity, availability=r.availability,
                    availability_detail=r.availability_detail, last_checked_at=r.last_checked_at, last_updated_at=r.last_updated_at,
                    max_zoom=cfg.get("max_zoom"))


@router.get("", response_model=list[LayerOut])
async def list_layers(db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    """Layer metadata + last-known availability. Stale probes are refreshed in the background (the response never waits)."""
    rows = list((await db.execute(select(LayerCatalog))).scalars())
    order = {d.id: i for i, d in enumerate(registry.REGISTRY)}
    rows.sort(key=lambda r: order.get(r.id, 999))
    now = datetime.now(timezone.utc)
    if any(r.last_checked_at is None or now - r.last_checked_at > STALE for r in rows):
        import asyncio

        asyncio.create_task(registry._safe_refresh())
    return [_out(r) for r in rows]


@router.post("/refresh", response_model=list[dict])
async def refresh(user: User = Depends(require_admin)):
    """Administrators can force a re-probe of every provider (waits for the result)."""
    return await registry.refresh_availability(probe=True)
