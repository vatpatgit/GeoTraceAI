"""Seed a clearly-labelled demonstration workspace.

    DEMO_MODE=true python -m app.demo.seed --owner-email you@example.com [--reset]

What it creates (all flagged ``is_demo``; the UI shows a DEMO badge and exports carry the flag):
  * a shared project "GeoTrace demo (synthetic data)";
  * two synthetic 4-band 10 m scene pairs over one AOI with *known* changes (see ``app.geo.synthetic``);
  * two analyses produced by running the REAL pipeline (alignment -> detection -> polygons) on those scenes;
  * a monitored "demo reserve" region and one alert rule, so alerts/analytics have something to show.
The imagery is synthetic noise-and-rectangles, NOT satellite data. Nothing here pretends otherwise.
"""
from __future__ import annotations

import argparse
import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from geoalchemy2.shape import from_shape
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform as shp_transform
from sqlalchemy import select
from starlette.datastructures import UploadFile

from app.config import settings
from app.database import async_session_maker
from app.geo.synthetic import ChangeSpec, make_synthetic_pair
from app.jobs.runner import drain
from app.models import AlertRule, AnalysisJob, Project, Region, User
from app.schemas.analysis import AnalysisCreate
from app.services import analyses as analysis_svc
from app.services.imagery import ingest_upload

DEMO_PROJECT = "GeoTrace demo (synthetic data)"
# Centre of the demo scene. A real-looking location so basemaps are meaningful; the *imagery* is synthetic.
LON, LAT, EPSG = -62.30, -10.90, 32720

SET_A = (
    ChangeSpec("vegetation_loss", (60, 120), (80, 160)),
    ChangeSpec("built", (200, 240), (300, 360)),
    ChangeSpec("vegetation_gain", (330, 380), (60, 110)),
    ChangeSpec("built", (400, 420), (400, 430)),
)
SET_B = SET_A[:2] + (  # the first two persist (re-detected), plus new ones and a larger clearing
    ChangeSpec("vegetation_loss", (130, 210), (60, 150)),
    ChangeSpec("built", (300, 330), (200, 250)),
    ChangeSpec("vegetation_loss", (440, 500), (300, 420)),
)


async def _upload(db, user, project, path: Path, date: datetime):
    with path.open("rb") as fh:
        up = UploadFile(file=fh, filename=path.name)
        asset, _, _ = await ingest_upload(db, user, project, up, acquisition_start=date, kind="synthetic", is_demo=True)
    return asset


async def seed(owner_email: str, reset: bool = False) -> None:
    if not settings.DEMO_MODE:
        raise SystemExit("Refusing to seed demo data: set DEMO_MODE=true (never in production).")
    async with async_session_maker() as db:
        owner = await db.scalar(select(User).where(User.email == owner_email))
        if owner is None:
            raise SystemExit(f"user {owner_email} not found (create it with: python -m app.cli create-user ...)")
        existing = await db.scalar(select(Project).where(Project.name == DEMO_PROJECT, Project.owner_id == owner.id))
        if existing and not reset:
            print("demo project already exists; use --reset to rebuild")
            return
        if existing:
            from app import storage
            from app.models import ImageryAsset

            for aid in [r for (r,) in (await db.execute(select(ImageryAsset.id).where(ImageryAsset.project_id == existing.id))).all()]:
                storage.remove_tree(f"imagery/{aid}")
            for jid in [r for (r,) in (await db.execute(select(AnalysisJob.id).where(AnalysisJob.project_id == existing.id))).all()]:
                storage.remove_tree(f"analyses/{jid}")
            await db.delete(existing)
            await db.commit()

        project = Project(name=DEMO_PROJECT, description="Synthetic scenes with known changes, processed by the real pipeline. Not real satellite data.",
                          owner_id=owner.id, visibility="shared", is_demo=True)
        db.add(project)
        await db.commit()
        await db.refresh(project)

        to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{EPSG}", always_xy=True)
        cx, cy = to_utm.transform(LON, LAT)
        origin = (round(cx - 2560, -1), round(cy + 2560, -1))  # 5.12 km square, upper-left corner
        to_wgs = Transformer.from_crs(f"EPSG:{EPSG}", "EPSG:4326", always_xy=True)
        scene_poly = shp_transform(to_wgs.transform, box(origin[0], origin[1] - 5120, origin[0] + 5120, origin[1]))
        # "Demo reserve": the western half of the scene (so some detections fall inside / near it)
        reserve = shp_transform(to_wgs.transform, box(origin[0], origin[1] - 5120, origin[0] + 2600, origin[1]))
        if not await db.scalar(select(Region.id).where(Region.name == "Demo reserve (synthetic)")):
            db.add(Region(name="Demo reserve (synthetic)", description="Monitored boundary used by the demo alert rule. Synthetic.",
                          geometry=from_shape(reserve, srid=4326), center_lat=LAT, center_lng=LON - 0.012, area_km2=13.4,
                          risk_level="high", metadata_json={"demo": True}))
        await db.commit()
        reserve_row = await db.scalar(select(Region).where(Region.name == "Demo reserve (synthetic)"))

        with tempfile.TemporaryDirectory(prefix="geotrace-demo-") as tmp:
            tmp = Path(tmp)
            dates = [datetime(2024, 1, 12, 10, 0, tzinfo=timezone.utc), datetime(2024, 7, 18, 10, 0, tzinfo=timezone.utc),
                     datetime(2025, 1, 9, 10, 0, tzinfo=timezone.utc)]
            # t0 -> t1 changes SET_A ; t1 -> t2 changes SET_B (relative to the t1 look)
            p01 = make_synthetic_pair(tmp / "p01", origin=origin, epsg=EPSG, seed=7, changes=SET_A, name="t0_t1")
            p12 = make_synthetic_pair(tmp / "p12", origin=origin, epsg=EPSG, seed=7, changes=SET_B, name="t1_t2")
            assets = {
                "t0": await _upload(db, owner, project, p01.before, dates[0]),
                "t1": await _upload(db, owner, project, p01.after, dates[1]),
                "t1b": await _upload(db, owner, project, p12.before, dates[1]),
                "t2": await _upload(db, owner, project, p12.after, dates[2]),
            }
            # Always mark the monitored-region rule BEFORE the analyses so incidents are produced by the real job path.
            db.add(AlertRule(owner_id=owner.id, name="Demo: high-priority changes near the reserve", project_id=project.id,
                             region_id=reserve_row.id, region_relation="within_distance", distance_m=500.0,
                             min_severity="high", min_area_m2=10000.0, dedup_mode="spatial"))
            await db.commit()

            for (b, a, label) in (("t0", "t1", "Demo A: Jan - Jul 2024"), ("t1b", "t2", "Demo B: Jul 2024 - Jan 2025")):
                body = AnalysisCreate(project_id=project.id, name=label, before_asset_id=assets[b].id, after_asset_id=assets[a].id,
                                      config={"detection": {"method": "spectral_cva"}}, input_type="demo")
                await analysis_svc.create_analysis(db, owner, project, body, before=assets[b], after=assets[a], is_demo=True)
                await drain()
    print("demo workspace ready: open the map and pick 'Demo A' / 'Demo B'. All data is synthetic and labelled DEMO.")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--owner-email", required=True)
    p.add_argument("--reset", action="store_true")
    args = p.parse_args()
    asyncio.run(seed(args.owner_email, args.reset))


if __name__ == "__main__":
    main()
