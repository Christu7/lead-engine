import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    apollo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    funding_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    annual_revenue_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tech_stack: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    keywords: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    founded_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enrichment_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    enrichment_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )
    enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    abm_status: Mapped[str] = mapped_column(String(50), nullable=False, default="target")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("apollo_id", "client_id", name="uq_companies_apollo_id_client"),
        UniqueConstraint("domain", "client_id", name="uq_companies_domain_client"),
        Index("ix_companies_client_id", "client_id"),
        Index("ix_companies_domain", "domain"),
        Index("ix_companies_apollo_id", "apollo_id"),
        Index("ix_companies_enrichment_status", "enrichment_status"),
        Index("ix_companies_abm_status", "abm_status"),
    )
