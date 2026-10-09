"""PostGIS-backed test fixtures.

A throwaway database is required (see docs): ``docker run -p 55432:5432 -e POSTGRES_USER=geotrace
-e POSTGRES_PASSWORD=geotrace_test -e POSTGRES_DB=geotrace_test postgis/postgis:15-3.4``.
The schema is dropped and rebuilt through the real Alembic migrations, and the target database name must contain
"test" so this can never wipe a real database.
"""
import os
import shutil
from pathlib import Path

import psycopg2
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.config import settings

TEST_URL = settings.DATABASE_URL


def _sync_dsn(url: str) -> dict:
    u = make_url(url)
    return dict(host=u.host, port=u.port, user=u.username, password=u.password, dbname=u.database)


def _db_available() -> tuple[bool, str]:
    try:
        u = make_url(TEST_URL)
        if "test" not in (u.database or ""):
            return False, f"refusing to run DB tests against non-test database {u.database!r}"
        conn = psycopg2.connect(connect_timeout=3, **_sync_dsn(TEST_URL))
        conn.close()
        return True, ""
    except Exception as exc:
        return False, f"PostGIS test database unavailable: {exc}"


def pytest_collection_modifyitems(config, items):
    ok, reason = _db_available()
    if ok:
        return
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if "tests/db" in str(item.fspath).replace("\\", "/") or item.get_closest_marker("db"):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def migrated_database():
    from app.migrate import upgrade_to_head

    conn = psycopg2.connect(**_sync_dsn(TEST_URL))
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP SCHEMA public CASCADE")
    cur.execute("CREATE SCHEMA public")
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    conn.close()
    upgrade_to_head(TEST_URL)
    storage = Path(settings.STORAGE_DIR)
    shutil.rmtree(storage, ignore_errors=True)
    storage.mkdir(parents=True, exist_ok=True)
    yield TEST_URL
    shutil.rmtree(storage, ignore_errors=True)


DATA_TABLES = (
    "alert_incidents", "alert_rules", "analysis_exports", "analysis_events", "change_features", "analysis_jobs",
    "weather_alert_events", "weather_alerts", "weather_aoi_state",
    "satellite_acquisitions", "imagery_assets", "areas_of_interest", "projects", "layer_catalog", "regions", "users",
)


@pytest_asyncio.fixture
async def db(migrated_database):
    """An AsyncSession; all rows are removed after each test (cheap isolation that still allows real commits)."""
    from app.database import async_session_maker

    async with async_session_maker() as session:
        yield session
    async with async_session_maker() as cleanup:
        await cleanup.execute(text("TRUNCATE " + ", ".join(DATA_TABLES) + " RESTART IDENTITY CASCADE"))
        await cleanup.commit()
    storage = Path(settings.STORAGE_DIR)
    for child in storage.glob("*"):
        shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)


# ---------------------------------------------------------------------------------------------------- API helpers
import uuid as _uuid  # noqa: E402

import httpx  # noqa: E402

from app.auth.jwt_handler import create_access_token  # noqa: E402
from app.auth.password import hash_password  # noqa: E402
from app.models import User  # noqa: E402


async def make_user(db, role: str = "user", email: str | None = None, active: bool = True) -> User:
    u = User(email=email or f"{role}-{_uuid.uuid4().hex[:6]}@example.test", password_hash=hash_password("Passw0rd!Passw0rd!"),
             name=f"{role.title()} Tester", role=role, is_active=active)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def auth(user: User) -> dict:
    return {"Authorization": "Bearer " + create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})}


@pytest_asyncio.fixture
async def client(migrated_database):
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c
