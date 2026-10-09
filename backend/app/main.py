import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.api.system import VERSION
from app.api.system import router as system_router
from app.config import settings
from app.logging_config import configure_logging, request_id_var

logger = logging.getLogger("geotrace")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: logging, (dev) migrations, layer catalogue, embedded job worker. Shutdown: stop the worker."""
    configure_logging()
    stop = asyncio.Event()
    worker: asyncio.Task | None = None
    if settings.AUTO_MIGRATE:
        try:
            from app.migrate import upgrade_to_head

            note = await asyncio.to_thread(upgrade_to_head)
            logger.info("database migrations: %s", note)
        except Exception:
            logger.exception("database migration failed - /ready will report degraded")
    try:
        from app.layers.registry import sync_catalog

        await sync_catalog()
    except Exception:
        logger.exception("layer catalogue sync failed (continuing)")
    if settings.JOB_RUNNER == "embedded":
        from app.jobs.runner import run_loop

        worker = asyncio.create_task(run_loop(stop))
    weather_task: asyncio.Task | None = None
    if settings.JOB_RUNNER == "embedded" and settings.WEATHER_REFRESH_MINUTES > 0 and settings.OPENWEATHER_API_KEY:
        from app.jobs.weather_refresh import run_loop as weather_loop

        weather_task = asyncio.create_task(weather_loop(stop))
    logger.info("GeoTrace API %s started (env=%s, job_runner=%s)", VERSION, settings.ENV, settings.JOB_RUNNER)
    yield
    stop.set()
    if weather_task:
        weather_task.cancel()
    if worker:
        try:
            await asyncio.wait_for(worker, timeout=35)
        except asyncio.TimeoutError:
            worker.cancel()


app = FastAPI(
    title="GeoTrace API",
    description="Bi-temporal satellite change detection: imagery -> georeferenced change polygons -> alerts, analytics and exports.",
    version=VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Feature-Count", "X-Export-Id", "Content-Disposition"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        response = JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)
    finally:
        elapsed = (time.perf_counter() - start) * 1000
        if not request.url.path.startswith(("/health", "/ready")):
            logger.info("%s %s -> %s in %.0f ms", request.method, request.url.path, getattr(locals().get("response"), "status_code", "?"), elapsed)
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [{"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    return JSONResponse({"detail": "Validation failed", "errors": errors, "request_id": request_id_var.get()}, status_code=422)


app.include_router(api_router, prefix=settings.API_PREFIX)
app.include_router(system_router)  # /health and /ready at the root for orchestrators


@app.get("/")
async def root():
    return {"name": "GeoTrace API", "version": VERSION, "docs": "/docs", "api": settings.API_PREFIX}
