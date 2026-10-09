"""The old test asserted that startup *ignores* an unavailable database and /health hard-coded "connected".
Readiness must now be truthful: a down database is reported, never papered over."""
import httpx
import pytest

from app import database


class _FailingEngine:
    def connect(self):
        return self

    async def __aenter__(self):
        raise OSError("database unavailable")

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_check_database_reports_unavailability(monkeypatch):
    monkeypatch.setattr(database, "engine", _FailingEngine())
    ok, error = await database.check_database()
    assert ok is False and "database unavailable" in error


@pytest.mark.asyncio
async def test_ready_endpoint_returns_503_when_database_is_down(monkeypatch):
    import app.api.system as system
    from app.main import app

    async def down():
        return False, "OSError: database unavailable"

    monkeypatch.setattr(system, "check_database", down)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/ready")
        live = await c.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded" and body["checks"]["database"]["ok"] is False
    assert live.status_code == 200  # liveness is independent of dependencies
