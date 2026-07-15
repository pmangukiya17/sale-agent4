import uuid
from datetime import datetime

from sqlalchemy import Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SignalImportance, SignalStatus, SignalUrgency


class Signal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    An atomic, evidenced business signal (hiring, expansion, new facility,
    trade show, news, investment, ...). signal_type stays a free string -
    an open, growing vocabulary - while importance/urgency are closed
    enums, since those are fixed business-judgment categories a rep sorts
    and filters by, distinct from confidence (how sure the AI is).
    """

    __tablename__ = "signals"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    intelligence_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intelligence_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    signal_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    importance: Mapped[SignalImportance] = mapped_column(
        Enum(
            SignalImportance,
            name="signal_importance",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SignalImportance.MEDIUM,
        nullable=False,
        index=True,
    )
    urgency: Mapped[SignalUrgency] = mapped_column(
        Enum(
            SignalUrgency,
            name="signal_urgency",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SignalUrgency.MEDIUM,
        nullable=False,
        index=True,
    )
    status: Mapped[SignalStatus] = mapped_column(
        Enum(
            SignalStatus,
            name="signal_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SignalStatus.NEW,
        nullable=False,
        index=True,
    )

    prospect: Mapped["Prospect"] = relationship()
    intelligence_snapshot: Mapped["IntelligenceSnapshot | None"] = relationship(back_populates="signals")
    evidence: Mapped[list["SignalEvidence"]] = relationship(back_populates="signal", cascade="all, delete-orphan")
