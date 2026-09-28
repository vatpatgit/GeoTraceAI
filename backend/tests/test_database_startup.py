import pytest

from app import database


class FakeConnection:
    async def __aenter__(self):
        raise OSError("database unavailable")

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_init_db_ignores_database_unavailability(monkeypatch):
    monkeypatch.setattr(database.engine, "begin", lambda: FakeConnection())

    await database.init_db()
