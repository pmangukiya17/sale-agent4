import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SearchTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Reusable Discovery Search blueprint. company_profile_id is nullable
    specifically so a small set of system-seeded starter templates
    (is_system_default=True) can exist without belonging to any one
    business — a business clones one into its own row when it customizes
    it, the same "seed, then clone/override" pattern already used for
    reference data. Every DiscoverySearch must point at exactly one of
    these (see DiscoverySearch.search_template_id, NOT NULL).
    """

    __tablename__ = "search_templates"

    company_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provider-agnostic search parameters (keywords, regions, buyer-type
    # hints, ...). Deliberately schema-less - shape varies per provider and
    # is validated at the provider layer, not the DB layer.
    query_spec: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_system_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    discovery_searches: Mapped[list["DiscoverySearch"]] = relationship(back_populates="search_template")
