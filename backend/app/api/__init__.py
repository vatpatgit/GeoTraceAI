from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.regions import router as regions_router
from app.api.alerts import router as alerts_router
from app.api.users import router as users_router
from app.api.projects import router as projects_router
from app.api.imagery import router as imagery_router
from app.api.analyses import router as analyses_router
from app.api.system import router as system_router
from app.api.analytics import router as analytics_router, reports_router
from app.api.layers import router as layers_router
from app.api.sentinel import router as sentinel_router
from app.api.weather import router as weather_router
from app.api.geoguider import router as geoguider_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(users_router, prefix="/users", tags=["Users"])
api_router.include_router(regions_router, prefix="/regions", tags=["Monitored regions"])
api_router.include_router(projects_router, prefix="/projects", tags=["Projects & AOIs"])
api_router.include_router(imagery_router, prefix="/imagery", tags=["Imagery"])
api_router.include_router(analyses_router, prefix="/analyses", tags=["Analyses"])
api_router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(sentinel_router, prefix="/sentinel", tags=["Sentinel"])
api_router.include_router(weather_router, prefix="/weather-alerts", tags=["Weather alerts"])
api_router.include_router(geoguider_router, prefix="/geoguider", tags=["GeoGuider"])
api_router.include_router(layers_router, prefix="/layers", tags=["Layers"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(reports_router, prefix="/reports", tags=["Reports"])
api_router.include_router(system_router)  # /api/v1/health, /api/v1/ready, /api/v1/system/status
