import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RawDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Permanent, never-discarded evidence. One row per fetch, even if
    content is byte-identical to a previous fetch (content_hash lets a
    consumer cheaply detect "nothing changed since last time" without
    forcing that decision at storage time - never discarding is the
    explicit requirement).

    Note: the attribute is named doc_metadata, not metadata - "metadata"
    is reserved by SQLAlchemy's declarative base for table metadata.
    """

    __tablename__ = "raw_documents"

    research_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Free string by design - "html_page"/"pdf"/"json_api_response"/
    # "image"/"text"/future types - a new document shape is a data change,
    # not a code deploy.
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    research_source: Mapped["ResearchSource"] = relationship(back_populates="raw_documents")
