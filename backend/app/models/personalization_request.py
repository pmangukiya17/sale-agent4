import uuid

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PersonalizationJobStatus


class PersonalizationRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    "Work out a sales strategy for this prospect" - per-prospect, not a
    reusable saved config. Personalization is a pure consumer of Research
    (M2): it reads IntelligenceSnapshot/Signal/Recommendation and never
    re-derives facts, so there is no FK from this model or its children
    back to any Discovery table, and no provider/raw-document concept at
    all - Personalization discovers nothing new.
    """

    __tablename__ = "personalization_requests"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    personalization_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("personalization_templates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    requested_focus_areas: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[PersonalizationJobStatus] = mapped_column(
        Enum(
            PersonalizationJobStatus,
            name="personalization_job_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=PersonalizationJobStatus.PENDING,
        nullable=False,
        index=True,
    )

    prospect: Mapped["Prospect"] = relationship()
    personalization_template: Mapped["PersonalizationTemplate"] = relationship(
        back_populates="personalization_requests"
    )
    jobs: Mapped[list["PersonalizationJob"]] = relationship(
        back_populates="personalization_request", cascade="all, delete-orphan"
    )
    runs: Mapped[list["PersonalizationRun"]] = relationship(
        back_populates="personalization_request", cascade="all, delete-orphan"
    )
