from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProviderUsageLog(Base):
    """Tracks external provider API calls for credit and volume visibility.

    Apollo does not return credits_used in API responses; use credits_estimated
    (computed from operation type) instead. credits_used stays NULL for Apollo.
    """

    __tablename__ = "provider_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    # operation values: "lead_enrich", "company_enrich", "contact_pull"
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    # entity_id is a string so it can hold either an int lead_id or a UUID company_id
    entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Number of HTTP requests made (1 base + reveal attempts for contact_pull)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Records returned by the API (people found, org enriched, etc.)
    records_returned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Actual credits charged — NULL because Apollo does not expose this in responses
    credits_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Our estimate based on known Apollo pricing per operation type
    credits_estimated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Extra context: reveal_attempts, reveals_succeeded, total_found, etc.
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_provider_usage_logs_client_id", "client_id"),
        Index("ix_provider_usage_logs_provider", "provider"),
        Index("ix_provider_usage_logs_created_at", "created_at"),
        Index("ix_provider_usage_logs_client_provider", "client_id", "provider"),
    )
