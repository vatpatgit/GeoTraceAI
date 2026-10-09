from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings

# Tests run each case on its own event loop; pooled asyncpg connections are loop-bound, so use no pool there.
_pool_kwargs = {"poolclass": NullPool} if settings.ENV == "test" else {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 10}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.LOG_LEVEL == "DEBUG"),
    future=True,
    **_pool_kwargs,
)

async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session."""
    async with async_session_maker() as session:
        yield session


async def check_database() -> tuple[bool, str | None]:
    """Real readiness probe: round-trips a query and verifies PostGIS is installed."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            version = await conn.scalar(text("SELECT postgis_version()"))
            if not version:
                return False, "PostGIS extension not installed"
        return True, None
    except Exception as exc:  # network / auth / missing extension
        return False, f"{type(exc).__name__}: {exc}"[:300]
