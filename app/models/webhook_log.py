from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WebhookLog(Base):
    __tablename__ = "webhook_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="received")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_webhook_logs_client_id", "client_id"),
        Index("ix_webhook_logs_source", "source"),
        Index("ix_webhook_logs_status", "status"),
    )
