"""Liveness / readiness and a truthful system-status document for the UI (no hard-coded 'online' badges)."""
from __future__ import annotations

import os
import time

from fastapi import APIRouter, Depends, Response, status

from app import storage
from app.auth.dependencies import require_authenticated_user
from app.config import settings
from app.database import check_database
from app.ml.registry import ensure_ml_path, load_cards, torch_available
from app.models import User

router = APIRouter()
STARTED_AT = time.time()
VERSION = "2.0.0"


@router.get("/health", tags=["System"])
async def health():
    """Liveness only: the process is up. Use /ready for dependencies."""
    return {"status": "ok", "version": VERSION, "uptime_s": round(time.time() - STARTED_AT)}


def _storage_ok() -> tuple[bool, str | None]:
    try:
        root = storage.storage_root()
        probe = root / ".write_probe"
        probe.write_text("ok")
        probe.unlink()
        return True, None
    except Exception as exc:
        return False, str(exc)[:200]


@router.get("/ready", tags=["System"])
async def ready(response: Response):
    db_ok, db_err = await check_database()
    st_ok, st_err = _storage_ok()
    ok = db_ok and st_ok
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ok else "degraded",
            "checks": {"database": {"ok": db_ok, "error": db_err}, "storage": {"ok": st_ok, "error": st_err}}}


def gpu_info() -> dict:
    if not torch_available():
        return {"torch": False, "cuda": False, "device": None}
    import torch

    cuda = torch.cuda.is_available()
    return {"torch": True, "torch_version": torch.__version__, "cuda": cuda,
            "device": torch.cuda.get_device_name(0) if cuda else None}


@router.get("/system/status", tags=["System"])
async def system_status(user: User = Depends(require_authenticated_user)):
    from app.providers.registry import provider_status  # lazy

    db_ok, db_err = await check_database()
    st_ok, _ = _storage_ok()
    default_id, cards = load_cards()
    models = [c.public_dict() for c in cards.values()]
    return {
        "version": VERSION, "env": settings.ENV, "demo_mode": settings.DEMO_MODE,
        "database": {"ok": db_ok, "error": db_err}, "storage": {"ok": st_ok},
        "job_runner": settings.JOB_RUNNER, "job_concurrency": settings.JOB_CONCURRENCY,
        "ml": {"code_available": ensure_ml_path(), **gpu_info(), "default_model": default_id,
               "models": models, "any_model_ready": any(m["available"] for m in models)},
        "sentinel": await provider_status(),
        "weather": {"configured": bool(settings.OPENWEATHER_API_KEY), "scheduled_refresh_minutes": max(0, settings.WEATHER_REFRESH_MINUTES)},
        "llm": {"configured": settings.LLM_PROVIDER != "none" and bool(settings.LLM_API_KEY), "provider": settings.LLM_PROVIDER},
        "limits": {"max_upload_mb": settings.MAX_UPLOAD_MB, "max_raster_pixels": settings.MAX_RASTER_PIXELS, "max_aoi_km2": settings.MAX_AOI_KM2},
    }
