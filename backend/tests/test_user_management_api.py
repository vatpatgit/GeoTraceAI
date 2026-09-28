import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-at-least-32-characters-long")

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.auth.dependencies import get_current_user
from app.auth.password import hash_password
from app.database import get_db
from app.models import User


class Result:
    def __init__(self, values=None, scalar_value=None):
        self.values = values or []
        self.scalar_value = scalar_value

    def scalars(self):
        return self

    def all(self):
        return self.values

    def scalar_one_or_none(self):
        return self.scalar_value


class FakeDatabase:
    def __init__(self, users=None, login_user=None, active_admin_count=2):
        self.users = {user.id: user for user in users or []}
        self.login_user = login_user
        self.active_admin_count = active_admin_count

    async def execute(self, statement):
        if self.login_user is not None:
            return Result(scalar_value=self.login_user)
        return Result(values=list(self.users.values()))

    async def scalar(self, statement):
        return self.active_admin_count if "count" in str(statement).lower() else None

    async def get(self, model, user_id):
        return self.users.get(UUID(str(user_id)))

    def add(self, user):
        if user.id is None:
            user.id = uuid4()
        if user.is_active is None:
            user.is_active = True
        if user.created_at is None:
            user.created_at = datetime.now(timezone.utc)
        self.users[user.id] = user

    async def refresh(self, user):
        self.users[user.id] = user

    async def commit(self):
        return None

    async def delete(self, user):
        self.users.pop(user.id, None)


@pytest.fixture
def users():
    admin = User(id=uuid4(), email="admin@example.test", name="Admin", role="admin", is_active=True, created_at=datetime.now(timezone.utc))
    target = User(id=uuid4(), email="target@example.test", name="Target", role="viewer", is_active=True, created_at=datetime.now(timezone.utc))
    return admin, target


@pytest.fixture
def app_and_db(users):
    admin, target = users
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(users_router, prefix="/users")
    database = FakeDatabase([admin, target])
    current_user = {"value": admin}

    async def override_db():
        yield database

    async def override_current_user():
        return current_user["value"]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_current_user
    return app, database, current_user, admin, target


async def request(app, method, path, **kwargs):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
async def test_unauthenticated_user_management_returns_401(app_and_db):
    app, *_ = app_and_db
    app.dependency_overrides.pop(get_current_user)
    response = await request(app, "GET", "/users/")
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["user", "researcher", "viewer"])
@pytest.mark.parametrize("method,path", [
    ("GET", "/users/"),
    ("POST", "/users/"),
    ("PATCH", "/users/00000000-0000-0000-0000-000000000001/role"),
    ("PATCH", "/users/00000000-0000-0000-0000-000000000001/status"),
    ("DELETE", "/users/00000000-0000-0000-0000-000000000001"),
])
async def test_non_admin_user_management_returns_403(app_and_db, role, method, path):
    app, _, current_user, _, _ = app_and_db
    current_user["value"].role = role
    payload = {"name": "New User", "email": "new@example.test", "password": "secure-password", "role": "viewer"} if method == "POST" else {"role": "viewer"} if path.endswith("/role") else {"is_active": False} if path.endswith("/status") else None
    response = await request(app, method, path, json=payload) if payload is not None else await request(app, method, path)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_use_all_user_management_endpoints(app_and_db):
    app, database, _, admin, target = app_and_db
    assert (await request(app, "GET", "/users/")).status_code == 200

    created = await request(app, "POST", "/users/", json={"name": "New User", "email": "new@example.com", "password": "secure-password", "role": "viewer"})
    assert created.status_code == 201, created.text
    created_id = created.json()["id"]

    assert (await request(app, "PATCH", f"/users/{created_id}", json={"name": "Renamed", "email": "renamed@example.com"})).status_code == 200
    assert (await request(app, "PATCH", f"/users/{created_id}/role", json={"role": "user"})).status_code == 200
    assert (await request(app, "PATCH", f"/users/{created_id}/status", json={"is_active": False})).status_code == 200
    assert (await request(app, "DELETE", f"/users/{created_id}")).status_code == 204
    assert UUID(created_id) not in database.users
    assert target.id in database.users
    assert admin.id in database.users


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["role", "status", "delete"])
async def test_last_active_administrator_cannot_be_removed(app_and_db, endpoint):
    app, database, _, admin, target = app_and_db
    target.role = "admin"
    database.active_admin_count = 1
    path = f"/users/{target.id}/{endpoint}" if endpoint != "delete" else f"/users/{target.id}"
    payload = {"role": "viewer"} if endpoint == "role" else {"is_active": False} if endpoint == "status" else None
    response = await request(app, "PATCH" if endpoint != "delete" else "DELETE", path, json=payload) if payload is not None else await request(app, "DELETE", path)
    assert response.status_code == 409
    assert "administrator" in response.json()["detail"].lower()
    assert admin.id in database.users


@pytest.mark.asyncio
async def test_inactive_user_cannot_authenticate():
    inactive = User(
        id=uuid4(),
        email="inactive@example.test",
        name="Inactive",
        role="user",
        is_active=False,
        password_hash=hash_password("correct-password"),
        created_at=datetime.now(timezone.utc),
    )
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    database = FakeDatabase(login_user=inactive)

    async def override_db():
        yield database

    app.dependency_overrides[get_db] = override_db
    response = await request(app, "POST", "/auth/login", data={"username": inactive.email, "password": "correct-password"})
    assert response.status_code == 401
