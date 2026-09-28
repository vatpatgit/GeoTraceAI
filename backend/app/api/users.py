from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import normalize_role, require_admin
from app.auth.password import hash_password
from app.database import get_db
from app.models import User
from app.schemas.auth import UserCreate, UserResponse, UserRoleUpdate, UserStatusUpdate, UserUpdate

router = APIRouter()
VALID_ROLES = {"admin", "administrator", "user", "researcher", "viewer"}


@router.get("/", response_model=list[UserResponse])
async def list_users(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    result = await db.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    if body.role.strip().lower() not in VALID_ROLES:
        raise HTTPException(status_code=422, detail="Invalid role")
    role = normalize_role(body.role)
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already exists")
    user = User(email=body.email, name=body.name, password_hash=hash_password(body.password), role=role.value)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: UUID, body: UserUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if body.name is not None:
        user.name = body.name
    if body.email is not None:
        user.email = body.email
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}/role", response_model=UserResponse)
async def update_role(user_id: UUID, body: UserRoleUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if body.role.strip().lower() not in VALID_ROLES:
        raise HTTPException(status_code=422, detail="Invalid role")
    role = normalize_role(body.role)
    if normalize_role(user.role).value == "admin" and role.value != "admin":
        admin_count = await db.scalar(select(func.count(User.id)).where(User.role.in_(["admin", "administrator"]), User.is_active.is_(True)))
        if admin_count <= 1:
            raise HTTPException(status_code=409, detail="Cannot demote the last active administrator")
    user.role = role.value
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}/status", response_model=UserResponse)
async def update_status(user_id: UUID, body: UserStatusUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not body.is_active and user.id == current_user.id:
        raise HTTPException(status_code=409, detail="An administrator cannot deactivate their own account")
    if not body.is_active and normalize_role(user.role).value == "admin":
        admin_count = await db.scalar(select(func.count(User.id)).where(User.role.in_(["admin", "administrator"]), User.is_active.is_(True)))
        if admin_count <= 1:
            raise HTTPException(status_code=409, detail="Cannot deactivate the last active administrator")
    user.is_active = body.is_active
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=409, detail="An administrator cannot delete their own account")
    if normalize_role(user.role).value == "admin":
        admin_count = await db.scalar(select(func.count(User.id)).where(User.role.in_(["admin", "administrator"]), User.is_active.is_(True)))
        if admin_count <= 1:
            raise HTTPException(status_code=409, detail="Cannot delete the last active administrator")
    await db.delete(user)
    await db.commit()