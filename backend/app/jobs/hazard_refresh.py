"""Optional scheduled hazard refresh for every saved AOI (embedded runner; interval >= 2 min). One upstream fetch serves all AOIs."""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.config import settings
from app.database import async_session_maker
from app.models import AreaOfInterest
from app.providers.base import ProviderError
from app.services import hazards as svc

logger = logging.getLogger(__name__)
MIN_INTERVAL_MIN = 2


async def refresh_all_once() -> dict:
    async with async_session_maker() as db:
        aois = list((await db.execute(select(AreaOfInterest).limit(2000))).scalars())
        sm = await svc.refresh_for(db, aois, force=True)
    return {"aois": sm.aois, "new": sm.new, "updated": sm.updated, "expired": sm.expired, "errors": sm.errors}


async def run_loop(stop: asyncio.Event) -> None:
    minutes = max(MIN_INTERVAL_MIN, settings.HAZARD_REFRESH_MINUTES)
    logger.info("hazard refresh scheduler started (every %d min)", minutes)
    while not stop.is_set():
        try:
            logger.info("hazard refresh: %s", await refresh_all_once())
        except ProviderError as exc:
            logger.warning("hazard refresh skipped: %s", str(exc)[:200])
        except Exception:
            logger.exception("hazard refresh cycle failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=minutes * 60)
        except asyncio.TimeoutError:
            pass
