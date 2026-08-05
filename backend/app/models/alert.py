from datetime import datetime
import uuid
from sqlalchemy import String, DateTime, Float, Boolean, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import User
from app.models.region import Region
from app.models.change_event import ChangeEvent

class AlertConfig(Base):
    __tablename__ = "alert_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    region_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("regions.id", ondelete="CASCADE"), nullable=True)
    change_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    threshold: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now())

    user: Mapped["User"] = relationship()
    region: Mapped["Region"] = relationship()


class AlertHistory(Base):
    __tablename__ = "alert_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    alert_config_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alert_configs.id", ondelete="CASCADE"), nullable=False)
    change_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("change_events.id", ondelete="CASCADE"), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now())

    alert_config: Mapped["AlertConfig"] = relationship()
    change_event: Mapped["ChangeEvent"] = relationship()
