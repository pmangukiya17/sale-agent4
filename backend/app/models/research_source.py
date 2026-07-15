import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ResearchSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One attempted fetch from one research provider within one job (e.g.
    "checked the company website", "checked LinkedIn"). source_identifier
    is an opaque provider-specific address (a LinkedIn company id, a
    registry number, ...) kept as a plain string so no provider-specific
    concept leaks into the core schema. A single source can yield zero,
    one, or many RawDocuments (a website crawl yields several pages).
    """

    __tablename__ = "research_sources"

    research_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_identifier: Mapped[str | None] = mapped_column(String(500), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    research_job: Mapped["ResearchJob"] = relationship(back_populates="sources")
    raw_documents: Mapped[list["RawDocument"]] = relationship(back_populates="research_source", cascade="all, delete-orphan")
