import uuid

from sqlalchemy import Enum, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PersonalizationStrategyRank


class PersonalizationStrategy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One ranked sales approach for a prospect - per the approved M3
    adjustment, a snapshot produces up to three of these (primary/
    secondary/fallback) rather than a single strategy field, since sales
    rarely has only one valid approach and future AI agents (M6/M7) need
    to be able to choose among them (e.g. "primary got no reply, try
    secondary in the follow-up"). Exactly one row per
    (personalization_snapshot_id, strategy_rank) - enforced by a unique
    constraint, not just application logic.
    """

    __tablename__ = "personalization_strategies"
    __table_args__ = (UniqueConstraint("personalization_snapshot_id", "strategy_rank", name="uq_personalization_strategy_rank"),)

    personalization_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("personalization_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy_rank: Mapped[PersonalizationStrategyRank] = mapped_column(
        Enum(
            PersonalizationStrategyRank,
            name="personalization_strategy_rank",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    personalization_snapshot: Mapped["PersonalizationSnapshot"] = relationship(back_populates="strategies")
    evidence: Mapped[list["PersonalizationEvidence"]] = relationship(
        back_populates="personalization_strategy", cascade="all, delete-orphan"
    )
