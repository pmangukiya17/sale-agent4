import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import FollowUpStatus


class FollowUp(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    SUPERSEDED - do not use. Same M0-era, never-wired situation as
    Thread/Message/WebsiteFinding - no route/service/frontend page
    references it. Real cadence/follow-up scheduling now lives in
    OutreachRequest.sequence_key/sequence_position (see that model's
    docstring) once a future milestone builds the sequencing engine. See
    deferred-items-and-design-boundaries.md's legacy CRM entry.
    """

    __tablename__ = "followups"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("threads.id", ondelete="SET NULL"), nullable=True
    )
    cadence_step: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(nullable=False)
    status: Mapped[FollowUpStatus] = mapped_column(
        Enum(
            FollowUpStatus,
            name="followup_status",
            # Same fix as User.role: bind the enum's lowercase VALUE, not
            # its uppercase NAME, to match the Postgres type from migration 0001.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=FollowUpStatus.SCHEDULED,
        nullable=False,
    )
    stop_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    company: Mapped["Company"] = relationship(back_populates="followups")
