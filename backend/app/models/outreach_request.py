import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.enums import OutreachJobStatus
from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OutreachRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    "Generate outreach for this specific stakeholder, on this channel,
    from this playbook" - mirrors PersonalizationRequest's per-prospect,
    not-a-reusable-config shape, but addressed to a ProspectContact, not
    just a Prospect. Per the approved account-based-selling refinement,
    outreach is scoped per named stakeholder (multiple contacts at one
    account each get independent draft lineages) rather than per account,
    even though the underlying PersonalizationSnapshot strategy read is
    still account-level (see PersonalizationSnapshot.scope's docstring).

    outreach_playbook_id is mandatory (RESTRICT on delete), same mandatory
    Template/Playbook -> Request -> Job chain used since M1.

    sequence_key/sequence_position are forward-looking, unused fields:
    cheap to add now so a future M7 (Follow-up Automation) can group
    multiple requests as "touch 1/2/3 of the same sequence for this
    contact" without a schema change - M4 itself does not build any
    sequencing engine.
    """

    __tablename__ = "outreach_requests"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # RESTRICT, not CASCADE: an OutreachRequest is real execution history -
    # see deferred-items-and-design-boundaries.md.
    prospect_contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospect_contacts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    outreach_playbook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach_playbooks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    sequence_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sequence_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[OutreachJobStatus] = mapped_column(
        Enum(
            OutreachJobStatus,
            name="outreach_job_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=OutreachJobStatus.PENDING,
        nullable=False,
        index=True,
    )

    prospect: Mapped["Prospect"] = relationship()
    prospect_contact: Mapped["ProspectContact"] = relationship()
    outreach_playbook: Mapped["OutreachPlaybook"] = relationship(back_populates="outreach_requests")
    jobs: Mapped[list["OutreachJob"]] = relationship(back_populates="outreach_request", cascade="all, delete-orphan")
    runs: Mapped[list["OutreachRun"]] = relationship(back_populates="outreach_request", cascade="all, delete-orphan")
