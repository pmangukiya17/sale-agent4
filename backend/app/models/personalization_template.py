import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PersonalizationTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Reusable Personalization Request blueprint - exact mirror of
    ResearchTemplate/SearchTemplate, including the nullable
    company_profile_id for system-seeded starter templates. Every
    PersonalizationRequest must point at exactly one of these (see
    PersonalizationRequest.personalization_template_id, NOT NULL) - the
    same mandatory Template -> Request -> Job chain used for Discovery and
    Research.
    """

    __tablename__ = "personalization_templates"

    company_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Which focus areas to weight, whether to always produce a fallback
    # strategy, etc. - provider-agnostic, validated at the engine layer,
    # not the DB layer.
    personalization_spec: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_system_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    personalization_requests: Mapped[list["PersonalizationRequest"]] = relationship(
        back_populates="personalization_template"
    )
