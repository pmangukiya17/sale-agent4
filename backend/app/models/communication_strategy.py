import uuid

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CommunicationFormality, CommunicationIntensityLevel, CommunicationLength


class CommunicationStrategy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    The communication blueprint for M4 - larger than a single "tone",
    per the approved M3 adjustment. One row per PersonalizationSnapshot
    (1:1, unique FK) since exactly one communication posture applies to a
    given version of the strategy. Each axis is a closed enum (the engine's
    own fixed vocabulary) rather than free text, matching this codebase's
    established "fixed/enumerable domain vocabulary -> real Postgres enum"
    convention - a rep or future agent can filter/query on these directly.
    """

    __tablename__ = "communication_strategies"

    personalization_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("personalization_snapshots.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    formality: Mapped[CommunicationFormality] = mapped_column(
        Enum(
            CommunicationFormality,
            name="communication_formality",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    directness: Mapped[CommunicationIntensityLevel] = mapped_column(
        Enum(
            CommunicationIntensityLevel,
            name="communication_intensity_level",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    warmth: Mapped[CommunicationIntensityLevel] = mapped_column(
        Enum(CommunicationIntensityLevel, name="communication_intensity_level", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=False,
    )
    technical_depth: Mapped[CommunicationIntensityLevel] = mapped_column(
        Enum(CommunicationIntensityLevel, name="communication_intensity_level", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=False,
    )
    authority: Mapped[CommunicationIntensityLevel] = mapped_column(
        Enum(CommunicationIntensityLevel, name="communication_intensity_level", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=False,
    )
    consultative_level: Mapped[CommunicationIntensityLevel] = mapped_column(
        Enum(CommunicationIntensityLevel, name="communication_intensity_level", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=False,
    )
    urgency: Mapped[CommunicationIntensityLevel] = mapped_column(
        Enum(CommunicationIntensityLevel, name="communication_intensity_level", values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=False,
    )
    message_length: Mapped[CommunicationLength] = mapped_column(
        Enum(
            CommunicationLength,
            name="communication_length",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    personalization_snapshot: Mapped["PersonalizationSnapshot"] = relationship(
        back_populates="communication_strategy"
    )
