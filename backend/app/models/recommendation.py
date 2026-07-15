import uuid

from sqlalchemy import Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import RecommendationStatus, RecommendationType


class Recommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A prescriptive, actionable output - distinct from the descriptive
    facts on IntelligenceSnapshot. recommendation_type is a closed enum
    (the Research Engine's own fixed vocabulary), unlike Signal.signal_type
    which stays open for external/future categories.
    """

    __tablename__ = "recommendations"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    intelligence_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intelligence_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recommendation_type: Mapped[RecommendationType] = mapped_column(
        Enum(
            RecommendationType,
            name="recommendation_type",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RecommendationStatus] = mapped_column(
        Enum(
            RecommendationStatus,
            name="recommendation_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=RecommendationStatus.NEW,
        nullable=False,
        index=True,
    )

    prospect: Mapped["Prospect"] = relationship()
    intelligence_snapshot: Mapped["IntelligenceSnapshot | None"] = relationship(back_populates="recommendations")
    product: Mapped["Product | None"] = relationship()
    evidence: Mapped[list["RecommendationEvidence"]] = relationship(
        back_populates="recommendation", cascade="all, delete-orphan"
    )
