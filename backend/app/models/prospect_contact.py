import uuid
from datetime import datetime

from sqlalchemy import Enum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DecisionMakerLevel


class ProspectContact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A person found at a Prospect. Field set deliberately mirrors the CRM's
    Contact model closely (name/role/email/phone/source/confidence/
    timezone/working_hours/preferred_contact_time) so a future CRM-import
    routine can map each one onto a real Contact with no translation
    logic, plus discovery-specific fields (department, decision_maker_level)
    that Contact doesn't need.
    """

    __tablename__ = "prospect_contacts"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_maker_level: Mapped[DecisionMakerLevel] = mapped_column(
        Enum(
            DecisionMakerLevel,
            name="decision_maker_level",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=DecisionMakerLevel.UNKNOWN,
        nullable=False,
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    working_hours: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    preferred_contact_time: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # CRM Automation milestone - same fields, same discipline as
    # Prospect.last_contacted_at/last_replied_at (contact-level rather
    # than account-level; written by the same app.crm_automation.service
    # call sites, when a specific ProspectContact is known).
    last_contacted_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    last_replied_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)

    prospect: Mapped["Prospect"] = relationship(back_populates="contacts")
