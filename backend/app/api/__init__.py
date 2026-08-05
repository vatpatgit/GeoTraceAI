from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.regions import router as regions_router
from app.api.changes import router as changes_router
from app.api.alerts import router as alerts_router
from app.api.analytics import router as analytics_router
from app.api.sentinel import router as sentinel_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(regions_router, prefix="/regions", tags=["Regions"])
api_router.include_router(changes_router, prefix="/changes", tags=["Changes"])
api_router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(sentinel_router, prefix="/sentinel", tags=["Sentinel Hub"])
