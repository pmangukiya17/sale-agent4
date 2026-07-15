import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProspectTimelineEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Open-ended, append-only event log for one Prospect. event_type is a
    free string (not an enum) and payload is schema-less JSONB
    deliberately - so a future AI agent (or a future milestone) can append
    a brand new kind of event ("ai_research_completed", "email_drafted",
    anything not invented yet) without a migration. This is a dedicated
    table rather than a reuse of the existing generic AuditLog because
    AuditLog is a system-wide ops trail across every entity type, not
    shaped for "show this one prospect's full story" as a first-class
    product feature the review UI reads directly.
    """

    __tablename__ = "prospect_timeline_events"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # "system" / "user:<uuid>" / "ai_agent:<name>" - free text, not a FK,
    # since not every actor is a row in the users table.
    actor: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    prospect: Mapped["Prospect"] = relationship(back_populates="timeline_events")
