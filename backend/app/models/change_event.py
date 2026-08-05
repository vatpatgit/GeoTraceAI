from datetime import datetime
import uuid
from typing import Any, Dict
from sqlalchemy import String, DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
from app.database import Base
from app.models.region import Region

class ChangeEvent(Base):
    __tablename__ = "change_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    region_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("regions.id", ondelete="CASCADE"), nullable=False)
    change_type: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    area_affected_km2: Mapped[float] = mapped_column(Float, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    geometry = mapped_column(Geometry("POLYGON", srid=4326), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="sentinel-2", nullable=False)
    ndvi_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now())

    region: Mapped["Region"] = relationship(backref="change_events")
