"""Programmatic Alembic helpers: ``python -m app.migrate`` upgrades the configured database to head.

Databases created by the legacy TerraTrack startup code (``create_all``) have the ``users`` table but no
``alembic_version`` table: they are stamped at the baseline revision first so only the GeoTrace revision is applied.
"""
from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.config import BACKEND_ROOT, settings

BASELINE_REVISION = "0001"


def _config(url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.attributes["url"] = url or settings.DATABASE_URL
    return cfg


def upgrade_to_head(url: str | None = None) -> str:
    """Upgrade (stamping legacy databases first). Returns a short description of what happened."""
    url = url or settings.DATABASE_URL
    sync = url.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    cfg = _config(url)
    note = "upgraded"
    if "users" in tables and "alembic_version" not in tables:
        command.stamp(cfg, BASELINE_REVISION)
        note = "stamped legacy TerraTrack database at baseline, then upgraded"
    command.upgrade(cfg, "head")
    return note


def main() -> int:
    print(upgrade_to_head())
    return 0


if __name__ == "__main__":
    sys.exit(main())
