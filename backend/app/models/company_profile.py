import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.associations import company_profile_industries


class CompanyProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A business the current user owns/operates. Deliberately NOT a singleton
    — a user can own multiple businesses and switch between them in the UI.
    Holds only static facts about the business itself ("who we are"); who
    the business is trying to sell to lives on ICPCriteria instead.
    """

    __tablename__ = "company_profiles"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # e.g. ["manufacturer", "exporter"] - a business can be more than one
    business_type: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    production_capacity: Mapped[str | None] = mapped_column(String(500), nullable=True)
    factory_location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    shipping_ports: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    export_certifications: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    minimum_order_quantity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_incoterms: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    preferred_payment_terms: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # IANA format, e.g. "Europe/Berlin" - validated at the API layer against
    # zoneinfo.available_timezones(), not enforced by the DB.
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Permanent instructions every AI agent reads before doing anything on
    # this business's behalf (tone, red lines, things to always mention,
    # etc.). Free text by design - this is a prompt fragment, not structured
    # data.
    ai_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    industries: Mapped[list["Industry"]] = relationship(
        secondary=company_profile_industries, backref="company_profiles"
    )
    products: Mapped[list["Product"]] = relationship(back_populates="company_profile", cascade="all, delete-orphan")
    icp_criteria: Mapped[list["ICPCriteria"]] = relationship(back_populates="company_profile", cascade="all, delete-orphan")
    knowledge_base_entries: Mapped[list["KnowledgeBase"]] = relationship(back_populates="company_profile", cascade="all, delete-orphan")
    # Business Branding: a UI/module concept, not a database entity - each
    # branding module (today: just the email signature) hangs directly off
    # company_profile_id, the same way Products/ICPCriteria/KnowledgeBase
    # do, rather than through an intermediate "Branding" aggregate row.
    brand_email_signature: Mapped["BrandEmailSignature | None"] = relationship(
        back_populates="company_profile", cascade="all, delete-orphan", uselist=False
    )
