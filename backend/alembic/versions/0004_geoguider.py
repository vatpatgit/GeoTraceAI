"""GeoGuider: conversations and messages.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-10
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB
TS = sa.DateTime(timezone=True)
NOW = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "geoguider_conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(120), nullable=False, server_default="New conversation"),
        sa.Column("workflow", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
    )
    op.create_index("ix_geoguider_conversations_user_id", "geoguider_conversations", ["user_id"])
    op.create_table(
        "geoguider_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("geoguider_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("blocks", JSONB(), nullable=False, server_default="[]"),
        sa.Column("actions", JSONB(), nullable=False, server_default="[]"),
        sa.Column("tool_calls", JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.CheckConstraint("role in ('user','assistant')", name="ck_geoguider_messages_role"),
    )
    op.create_index("ix_geoguider_messages_conv_created", "geoguider_messages", ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_table("geoguider_messages")
    op.drop_table("geoguider_conversations")
