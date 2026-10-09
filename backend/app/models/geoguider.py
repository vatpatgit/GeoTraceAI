"""GeoGuider conversations: message history plus the structured workflow state (never only inside an LLM prompt)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class GeoGuiderConversation(Base):
    __tablename__ = "geoguider_conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="New conversation")
    workflow: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class GeoGuiderMessage(Base):
    __tablename__ = "geoguider_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("geoguider_conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    blocks: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)  # structured cards
    actions: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)  # validated UI instructions
    tool_calls: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)  # audit trail (inputs summarised)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_geoguider_messages_conv_created", "conversation_id", "created_at"),)
