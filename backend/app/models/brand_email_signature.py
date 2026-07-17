import uuid

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BrandEmailSignature(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Business Branding's first module: the business's own rich-HTML email
    signature. Deliberately a mutable, 1:1 settings entity - NOT versioned
    like OutreachPlaybook/PromptVersion. A signature is business
    configuration (fix a typo, update a title), not an evolving strategy
    that benefits from a comparable version history. company_profile_id is
    UNIQUE for exactly this reason: at most one row per business, edited
    in place via PUT, the same discipline CompanyProfile and
    WorkspaceSettings already use.

    "Business Branding" itself is a UI/module concept, not a database
    entity - there is no business_brandings parent table. This table hangs
    directly off company_profile_id, same as Product/ICPCriteria/
    KnowledgeBase. Future branding modules (Identity, Visual, Social,
    Contact, Legal - see docs/architecture/future-milestones.md) would each
    be their own sibling table added the same way, not a child of this one.

    Explainability is preserved WITHOUT versioning this table: Outreach
    freezes the exact rendered signature_html into OutreachDraft.
    ai_generated_content.assembled at generation time (a new JSONB key, no
    schema change to OutreachDraft) - so every historical draft still
    proves exactly what was appended, even though this row itself may have
    since been edited. A plain FK from Outreach back to this row would NOT
    have preserved that, since this row is mutable-in-place.

    signature_plain_text is always server-derived from signature_html on
    save (app/branding/plain_text.py) - never accepted from the client -
    so it can never drift out of sync with the actual HTML.
    """

    __tablename__ = "brand_email_signatures"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    signature_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_plain_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    company_profile: Mapped["CompanyProfile"] = relationship(back_populates="brand_email_signature")
