import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ResearchTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Reusable Research Request blueprint - mirrors SearchTemplate (M1)
    exactly, including the nullable company_profile_id for system-seeded
    starter templates. Every ResearchRequest must point at exactly one of
    these (see ResearchRequest.research_template_id, NOT NULL), the same
    mandatory Template -> Request -> Job chain used for Discovery.
    """

    __tablename__ = "research_templates"

    company_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Which source types to check, depth, focus areas - provider-agnostic,
    # validated at the provider layer, not the DB layer.
    research_spec: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_system_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    research_requests: Mapped[list["ResearchRequest"]] = relationship(back_populates="research_template")
