from enum import Enum
from typing import Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User
from app.auth.jwt_handler import verify_token
import logging

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


def normalize_role(role: str) -> UserRole:
    """Normalize legacy role names without trusting roles from the client."""
    normalized = role.strip().lower()
    if normalized in {"admin", "administrator"}:
        return UserRole.ADMIN
    if normalized in {"user", "researcher"}:
        return UserRole.USER
    return UserRole.VIEWER

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    """
    FastAPI dependency for auth.
    Extracts user_id from token, queries User from DB, and returns it.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = verify_token(token)
    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception
        
    try:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error fetching user in dependencies: {e}")
        raise credentials_exception

    if user is None:
        raise credentials_exception

    if getattr(user, "is_active", True) is False:
        raise credentials_exception
        
    return user


def require_role(*allowed_roles: UserRole) -> Callable:
    """Create a dependency that enforces roles after authentication."""
    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if normalize_role(current_user.role) not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return dependency


require_authenticated_user = get_current_user
require_admin = require_role(UserRole.ADMIN)
require_user_or_admin = require_role(UserRole.ADMIN, UserRole.USER)
