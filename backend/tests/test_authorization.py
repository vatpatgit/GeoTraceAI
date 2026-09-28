import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-at-least-32-characters-long")

import pytest
from fastapi import HTTPException

from app.auth.dependencies import UserRole, normalize_role, require_role


@pytest.mark.parametrize(
    ("stored_role", "expected"),
    [("admin", UserRole.ADMIN), ("administrator", UserRole.ADMIN), ("researcher", UserRole.USER), ("user", UserRole.USER), ("viewer", UserRole.VIEWER)],
)
def test_legacy_roles_are_normalized(stored_role, expected):
    assert normalize_role(stored_role) is expected


@pytest.mark.asyncio
async def test_role_dependency_rejects_viewer_for_admin_action():
    dependency = require_role(UserRole.ADMIN)

    class Viewer:
        role = "viewer"

    with pytest.raises(HTTPException) as error:
        await dependency(Viewer())

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_role_dependency_allows_admin():
    dependency = require_role(UserRole.ADMIN)

    class Admin:
        role = "admin"

    assert await dependency(Admin()) is not None