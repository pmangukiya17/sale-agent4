import uuid

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.associations import (
    icp_criteria_excluded_countries,
    icp_criteria_languages,
    icp_criteria_target_buyer_types,
    icp_criteria_target_markets,
)
from app.models.enums import SearchDepth, SearchFrequency


class ICPCriteria(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Versioned Ideal Customer Profile rubric for one CompanyProfile — "who
    we're looking for", as opposed to CompanyProfile's "who we are". The
    Discovery Engine (a later milestone) searches using both a company's
    Products and its active ICPCriteria. Multiple versions can exist per
    company; only one is expected to be `is_active` at a time.
    """

    __tablename__ = "icp_criteria"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    preferred_company_size: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    minimum_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    exclude_duplicate_companies: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    search_depth: Mapped[SearchDepth] = mapped_column(
        Enum(
            SearchDepth,
            name="search_depth",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SearchDepth.STANDARD,
        nullable=False,
    )
    # Stored now, not yet acted on - scheduling automation is a later milestone.
    search_frequency: Mapped[SearchFrequency] = mapped_column(
        Enum(
            SearchFrequency,
            name="search_frequency",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SearchFrequency.MANUAL,
        nullable=False,
    )

    # Escape hatch for free-form criteria that don't have a modeled column
    # yet. Everything with a known, fixed shape gets a real column/junction
    # instead of living here.
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    company_profile: Mapped["CompanyProfile"] = relationship(back_populates="icp_criteria")
    target_buyer_types: Mapped[list["BuyerType"]] = relationship(secondary=icp_criteria_target_buyer_types)
    # Two separate relationships to Country via two separate junction
    # tables (not the same table), so each is unambiguous on its own -
    # no explicit primaryjoin/foreign_keys needed.
    target_markets: Mapped[list["Country"]] = relationship(secondary=icp_criteria_target_markets)
    excluded_countries: Mapped[list["Country"]] = relationship(secondary=icp_criteria_excluded_countries)
    languages: Mapped[list["Language"]] = relationship(secondary=icp_criteria_languages)
