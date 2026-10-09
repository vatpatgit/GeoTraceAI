from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import mapping
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_authenticated_user, require_user_or_admin
from app.config import settings
from app.database import get_db
from app.geo import aoi as aoi_geo
from app.geo.errors import GeoProcessingError
from app.models import AnalysisJob, AreaOfInterest, Project, Region, User
from app.schemas.project import AoiCreate, AoiOut, ProjectCreate, ProjectOut, ProjectUpdate
from app.services import access

router = APIRouter()


def _project_out(p: Project, user: User, analysis_count: int = 0) -> ProjectOut:
    return ProjectOut(id=p.id, name=p.name, description=p.description, owner_id=p.owner_id, visibility=p.visibility,
                      is_demo=p.is_demo, created_at=p.created_at, updated_at=p.updated_at, analysis_count=analysis_count,
                      can_write=access.project_can_write(p, user))


@router.get("", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    stmt = (select(Project, func.count(AnalysisJob.id)).outerjoin(AnalysisJob, AnalysisJob.project_id == Project.id)
            .where(access.readable_projects_clause(user)).group_by(Project.id).order_by(Project.created_at))
    return [_project_out(p, user, n) for p, n in (await db.execute(stmt)).all()]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_user_or_admin)):
    p = Project(name=body.name, description=body.description, visibility=body.visibility, owner_id=user.id)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _project_out(p, user)


@router.post("/default", response_model=ProjectOut)
async def ensure_default_project(db: AsyncSession = Depends(get_db), user: User = Depends(require_user_or_admin)):
    """Idempotently return (creating on first use) the caller's personal workspace."""
    return _project_out(await access.default_project(db, user), user)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    p = await access.load_project(db, project_id, user)
    n = await db.scalar(select(func.count(AnalysisJob.id)).where(AnalysisJob.project_id == p.id)) or 0
    return _project_out(p, user, n)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: uuid.UUID, body: ProjectUpdate, db: AsyncSession = Depends(get_db),
                         user: User = Depends(require_user_or_admin)):
    p = await access.load_project(db, project_id, user, write=True)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(p, k, v)
    await db.commit()
    await db.refresh(p)
    return _project_out(p, user)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_user_or_admin)):
    from app import storage
    p = await access.load_project(db, project_id, user, write=True)
    active = await db.scalar(select(func.count(AnalysisJob.id)).where(
        AnalysisJob.project_id == p.id, AnalysisJob.status.notin_(["completed", "failed", "cancelled"])))
    if active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cancel running analyses before deleting the project.")
    job_ids = [r for (r,) in (await db.execute(select(AnalysisJob.id).where(AnalysisJob.project_id == p.id))).all()]
    from app.models import ImageryAsset
    asset_ids = [r for (r,) in (await db.execute(select(ImageryAsset.id).where(ImageryAsset.project_id == p.id))).all()]
    await db.delete(p)
    await db.commit()
    for jid in job_ids:
        storage.remove_tree(f"analyses/{jid}")
    for aid in asset_ids:
        storage.remove_tree(f"imagery/{aid}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------------------------------------------------- AOIs
def aoi_out(a: AreaOfInterest) -> AoiOut:
    g = to_shape(a.geometry)
    return AoiOut(id=a.id, project_id=a.project_id, name=a.name, geometry=mapping(g), bbox=list(g.bounds), area_km2=a.area_km2,
                  source=a.source, region_id=a.region_id, created_at=a.created_at)


@router.get("/{project_id}/aois", response_model=list[AoiOut])
async def list_aois(project_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    await access.load_project(db, project_id, user)
    rows = (await db.execute(select(AreaOfInterest).where(AreaOfInterest.project_id == project_id).order_by(AreaOfInterest.created_at))).scalars()
    return [aoi_out(a) for a in rows]


async def build_aoi_polygon(db: AsyncSession, body: AoiCreate):
    try:
        if body.geometry is not None:
            poly = aoi_geo.polygon_from_geojson(body.geometry)
        elif body.bbox is not None:
            poly = aoi_geo.bbox_polygon(body.bbox)
        elif body.center is not None:
            poly = aoi_geo.circle_polygon(body.center[0], body.center[1], body.radius_m)
        else:
            region = await db.get(Region, body.region_id)
            if region is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Region not found")
            poly = to_shape(region.geometry)
        return aoi_geo.finalize_aoi(poly, max_km2=settings.MAX_AOI_KM2)
    except GeoProcessingError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "message": str(exc), "details": exc.details}) from exc


@router.post("/{project_id}/aois", response_model=AoiOut, status_code=status.HTTP_201_CREATED)
async def create_aoi(project_id: uuid.UUID, body: AoiCreate, db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_user_or_admin)):
    await access.load_project(db, project_id, user, write=True)
    poly, km2 = await build_aoi_polygon(db, body)
    source = "region" if body.region_id else body.source
    a = AreaOfInterest(project_id=project_id, name=body.name, geometry=from_shape(poly, srid=4326), area_km2=km2,
                       source=source, region_id=body.region_id,
                       metadata_json={"center": body.center, "radius_m": body.radius_m} if body.center else None)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return aoi_out(a)


@router.delete("/{project_id}/aois/{aoi_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_aoi(project_id: uuid.UUID, aoi_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_user_or_admin)):
    await access.load_project(db, project_id, user, write=True)
    a = await db.get(AreaOfInterest, aoi_id)
    if a is None or a.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "AOI not found")
    await db.delete(a)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
