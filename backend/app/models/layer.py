from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import Boolean, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class LayerCatalog(Base):
    """Persisted metadata + last-known availability of each environmental / risk layer (see ``app.layers.registry``)."""

    __tablename__ = "layer_catalog"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    group: Mapped[str] = mapped_column(String(24), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    data_type: Mapped[str] = mapped_column(String(24), nullable=False)
    render_type: Mapped[str] = mapped_column(String(24), nullable=False)
    crs: Mapped[str] = mapped_column(String(20), nullable=False, default="EPSG:3857")
    config: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    legend: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    temporal: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    attribution: Mapped[str] = mapped_column(Text, nullable=False, default="")
    limitations: Mapped[List[str] | None] = mapped_column(JSONB, nullable=True)
    default_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_opacity: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    availability: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    availability_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
