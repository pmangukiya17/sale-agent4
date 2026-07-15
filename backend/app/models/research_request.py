import uuid

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ResearchJobStatus


class ResearchRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    "Research this prospect" - per-prospect, not a reusable saved config
    like DiscoverySearch. Research is a deliberately independent domain:
    no FK back to any Discovery table (DiscoverySearch/DiscoveryJob/...)
    exists anywhere in this model or its children.
    """

    __tablename__ = "research_requests"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    research_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_templates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    requested_focus_areas: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ResearchJobStatus] = mapped_column(
        Enum(
            ResearchJobStatus,
            name="research_job_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ResearchJobStatus.PENDING,
        nullable=False,
        index=True,
    )

    prospect: Mapped["Prospect"] = relationship()
    research_template: Mapped["ResearchTemplate"] = relationship(back_populates="research_requests")
    jobs: Mapped[list["ResearchJob"]] = relationship(back_populates="research_request", cascade="all, delete-orphan")
    runs: Mapped[list["ResearchRun"]] = relationship(back_populates="research_request", cascade="all, delete-orphan")
