import uuid
from datetime import datetime

from sqlalchemy import Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ProspectStatus, RelationshipStage


class Prospect(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A durable, deduplicated, scored candidate buyer for one CompanyProfile.
    This is Discovery's own entity - entirely separate from the CRM's
    Company - and stays that way until a future milestone's explicit,
    one-way import action creates a Company from an approved Prospect. M1
    does not implement that import; only Approve/Reject/Archive exist here.
    """

    __tablename__ = "prospects"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    discovery_search_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_searches.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("industries.id", ondelete="SET NULL"), nullable=True
    )
    # What the provider actually said, kept verbatim even when industry_id
    # is confidently resolved - automatic classification won't always map
    # cleanly onto the fixed Industry reference table.
    industry_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    buyer_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buyer_types.id", ondelete="SET NULL"), nullable=True
    )
    company_size_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Free-text description/summary (whatever a provider surfaced) - the
    # only thing the scoring engine's product-keyword-relevance factor has
    # to compare against. Not part of the originally approved field list;
    # added because the scoring engine has nothing to match keywords
    # against without it.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[ProspectStatus] = mapped_column(
        Enum(
            ProspectStatus,
            name="prospect_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ProspectStatus.NEW,
        nullable=False,
        index=True,
    )
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # List of {factor, weight, matched, points, explanation} - the whole
    # point of "explainable", not just a number.
    score_breakdown: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Narrative justification from a future AI scoring/reasoning pass.
    # Column exists from day one; stays null until that milestone exists.
    ai_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_discovered_at: Mapped[datetime] = mapped_column(nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(nullable=False)

    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    potential_duplicate_of_prospect_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="SET NULL"), nullable=True
    )
    duplicate_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Added in M3. Actual sales history with this buyer - live and mutable,
    # deliberately NOT versioned like PersonalizationSnapshot's
    # buyer_readiness (an AI prediction, recalculated every run). M3's
    # pipeline only ever READS this value (copying it into
    # PersonalizationSnapshot.relationship_stage_at_generation for
    # explainability); nothing in M3 writes it. Future milestones (M4-M7)
    # are what advance it as outreach actually happens.
    relationship_stage: Mapped[RelationshipStage] = mapped_column(
        Enum(
            RelationshipStage,
            name="relationship_stage",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=RelationshipStage.COLD,
        nullable=False,
        index=True,
    )

    # IANA format, validated the same way as CompanyProfile.timezone - so a
    # future scheduler can read this without any schema change.
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)

    company_profile: Mapped["CompanyProfile"] = relationship()
    discovery_search: Mapped["DiscoverySearch | None"] = relationship()
    industry: Mapped["Industry | None"] = relationship()
    buyer_type: Mapped["BuyerType | None"] = relationship()
    potential_duplicate_of: Mapped["Prospect | None"] = relationship(remote_side="Prospect.id")

    contacts: Mapped[list["ProspectContact"]] = relationship(back_populates="prospect", cascade="all, delete-orphan")
    sources: Mapped[list["ProspectSource"]] = relationship(back_populates="prospect", cascade="all, delete-orphan")
    timeline_events: Mapped[list["ProspectTimelineEvent"]] = relationship(
        back_populates="prospect", cascade="all, delete-orphan", order_by="ProspectTimelineEvent.created_at"
    )
