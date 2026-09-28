"""Script to seed monitoring data, change events, and alert history."""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.database import async_session_maker
from app.models import AlertConfig, AlertHistory, ChangeEvent, Region, User


def build_model(model_cls, **kwargs):
    """Filter kwargs to match actual model columns."""
    valid_cols = {c.name for c in model_cls.__table__.columns}
    return model_cls(**{k: v for k, v in kwargs.items() if k in valid_cols})


async def main() -> None:
    now = datetime.now(timezone.utc)
    change_event_id = uuid4()
    alert_config_id = uuid4()

    region_wkt = "SRID=4326;POLYGON((-65.0 -3.0, -60.0 -3.0, -60.0 -8.0, -65.0 -8.0, -65.0 -3.0))"
    event_wkt = "SRID=4326;POLYGON((-62.5 -4.5, -62.3 -4.5, -62.3 -4.7, -62.5 -4.7, -62.5 -4.5))"

    async with async_session_maker() as db:
        # 1. Fetch existing User
        user_res = await db.execute(select(User).limit(1))
        user = user_res.scalars().first()
        if not user:
            print("Error: No user found. Run reset_admin_password first.")
            return

        # 2. Fetch or create Region
        reg_res = await db.execute(select(Region).limit(1))
        region = reg_res.scalars().first()
        if not region:
            region = build_model(
                Region,
                id=uuid4(),
                name="Amazon Basin",
                description="Primary rainforest monitoring zone",
                area_km2=1250000.0,
                geometry=region_wkt,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            db.add(region)
            await db.flush()

        # 3. Create Change Event
        change_event = build_model(
            ChangeEvent,
            id=change_event_id,
            region_id=region.id,
            change_type="deforestation",
            confidence=0.92,
            area_affected_km2=14.5,
            source="sentinel-2",
            ndvi_before=0.82,
            ndvi_after=0.41,
            geometry=event_wkt,
            detected_at=now,
            created_at=now,
        )
        db.add(change_event)
        await db.flush()

        # 4. Create Alert Config linked to User and Region
        alert_cfg = build_model(
            AlertConfig,
            id=alert_config_id,
            user_id=user.id,
            region_id=region.id,
            change_type="deforestation",
            threshold=0.70,
            channel="email",
            recipient=user.email,
            is_active=True,
            created_at=now,
        )
        db.add(alert_cfg)
        await db.flush()

        # 5. Seed Alert History Entries
        alert_histories = [
            build_model(
                AlertHistory,
                id=uuid4(),
                user_id=user.id,
                region_id=region.id,
                change_event_id=change_event_id,
                alert_config_id=alert_config_id,
                title="Deforestation Anomaly Detected",
                message="High vegetation loss detected in Amazon Basin Sector 4B (14.5 km²).",
                severity="critical",
                status="sent",
                triggered_at=now,
                created_at=now,
            ),
            build_model(
                AlertHistory,
                id=uuid4(),
                user_id=user.id,
                region_id=region.id,
                change_event_id=change_event_id,
                alert_config_id=alert_config_id,
                title="Canopy Disturbance Warning",
                message="Unusual canopy thinning observed near sector 2A.",
                severity="warning",
                status="sent",
                triggered_at=now,
                created_at=now,
            ),
        ]

        db.add_all(alert_histories)
        await db.commit()
        print(f"Successfully seeded demo alert data for user '{user.email}' in '{region.name}'.")


if __name__ == "__main__":
    asyncio.run(main())