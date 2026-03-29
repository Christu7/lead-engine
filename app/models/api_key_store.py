"""ApiKeyStore model — stores encrypted third-party API credentials.

This is NOT the ApiKey model (which handles webhook authentication).
This stores credentials for external services: Anthropic, OpenAI, Apollo, etc.
There is no client_id — these are system-level configuration values.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ApiKeyStore(Base):
    __tablename__ = "api_key_store"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=uuid.uuid4,
    )
    key_name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_value: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("key_name", name="uq_api_key_store_key_name"),
        Index("ix_api_key_store_key_name", "key_name", unique=True),
    )
