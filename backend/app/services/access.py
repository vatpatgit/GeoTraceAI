"""Resource-level authorization (role checks live in ``app.auth.dependencies``; this adds *ownership* rules).

Policy
  * admin  : everything.
  * user   : create/modify their own projects, imagery, analyses and alert rules; read shared projects.
  * viewer : read-only access to shared projects (and nothing private to others).
  * A project is readable by its owner, admins, and - when ``visibility == 'shared'`` - any authenticated user.
    Only the owner (or an admin) can write. Missing and forbidden private resources both return 404 so existence is not leaked.
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import UserRole, normalize_role
from app.models import AnalysisJob, ImageryAsset, Project, User


def is_admin(user: User) -> bool:
    return normalize_role(user.role) is UserRole.ADMIN


def can_write_role(user: User) -> bool:
    return normalize_role(user.role) in (UserRole.ADMIN, UserRole.USER)


def require_writer(user: User) -> None:
    if not can_write_role(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role is read-only.")


def readable_projects_clause(user: User):
    if is_admin(user):
        return True
    return or_(Project.owner_id == user.id, Project.visibility == "shared")


def project_can_write(project: Project, user: User) -> bool:
    return can_write_role(user) and (is_admin(user) or project.owner_id == user.id)


async def load_project(db: AsyncSession, project_id: uuid.UUID, user: User, *, write: bool = False) -> Project:
    project = await db.get(Project, project_id)
    readable = project is not None and (is_admin(user) or project.owner_id == user.id or project.visibility == "shared")
    if not readable:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if write and not project_can_write(project, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have write access to this project.")
    return project


async def load_analysis(db: AsyncSession, analysis_id: uuid.UUID, user: User, *, write: bool = False) -> AnalysisJob:
    job = await db.get(AnalysisJob, analysis_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    await load_project(db, job.project_id, user, write=write)
    return job


async def load_asset(db: AsyncSession, asset_id: uuid.UUID, user: User, *, write: bool = False) -> ImageryAsset:
    asset = await db.get(ImageryAsset, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagery asset not found")
    if asset.project_id is None:
        if not (is_admin(user) or asset.created_by == user.id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagery asset not found")
    else:
        await load_project(db, asset.project_id, user, write=write)
    return asset


async def default_project(db: AsyncSession, user: User) -> Project:
    """The user's personal workspace (created on first use)."""
    existing = await db.scalar(
        select(Project).where(Project.owner_id == user.id, Project.name == "My workspace").order_by(Project.created_at).limit(1)
    )
    if existing:
        return existing
    project = Project(name="My workspace", description="Default personal workspace", owner_id=user.id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project
