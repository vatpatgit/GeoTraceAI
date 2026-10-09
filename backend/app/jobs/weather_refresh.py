"""Optional scheduled refresh of AOIs that have weather monitoring turned on (embedded runner; interval >= 15 min)."""
from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.database import async_session_maker
from app.models import AreaOfInterest
from app.providers.base import ProviderError
from app.providers.openweather import AoiGeometryError, OpenWeatherAlerts
from app.services.weather_alerts import monitored_aois, refresh_aoi

logger = logging.getLogger(__name__)
MIN_INTERVAL_MIN = 15
PAUSE_BETWEEN_AOIS_S = 1.5  # spread calls out; the provider's rate limits are not published


async def refresh_all_once() -> dict[str, int]:
    client = OpenWeatherAlerts()
    out = {"aois": 0, "new": 0, "updated": 0, "errors": 0}
    if not client.configured:
        return out
    async with async_session_maker() as db:
        aois = await monitored_aois(db)
    for aoi in aois:
        async with async_session_maker() as db:
            try:
                row = await db.get(AreaOfInterest, aoi.id)
                if row is None:
                    continue
                r = await refresh_aoi(db, row, client=client)
                out["aois"] += 1
                out["new"] += r.new
                out["updated"] += r.updated
            except (ProviderError, AoiGeometryError) as exc:
                out["errors"] += 1
                logger.warning("weather refresh failed for AOI %s: %s", aoi.id, str(exc)[:160])
        await asyncio.sleep(PAUSE_BETWEEN_AOIS_S)
    return out


async def run_loop(stop: asyncio.Event) -> None:
    minutes = max(MIN_INTERVAL_MIN, settings.WEATHER_REFRESH_MINUTES)
    logger.info("weather refresh scheduler started (every %d min)", minutes)
    while not stop.is_set():
        try:
            summary = await refresh_all_once()
            logger.info("weather refresh: %s", summary)
        except Exception:
            logger.exception("weather refresh cycle failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=minutes * 60)
        except asyncio.TimeoutError:
            pass
