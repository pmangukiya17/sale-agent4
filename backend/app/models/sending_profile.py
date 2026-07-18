import uuid
from datetime import time

from sqlalchemy import Boolean, ForeignKey, Integer, String, Time
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SendingProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A named sending identity a business sends outreach through - "CEO",
    "Sales", "Marketing", "Support" in the M5 brief's own example.
    Deliberately mutable-in-place, not versioned (same governance as
    BrandEmailSignature/CompanyProfile/WorkspaceSettings): a sending
    profile is configuration, not an evolving strategy.

    provider_connection_id is nullable and independent of provider_key -
    a profile can exist in a "not yet connected" state (created, but no
    OAuth grant attached yet), and per the explicit decoupled-connection
    decision, one ProviderConnection (one real mailbox) can back several
    SendingProfiles (e.g. CEO@ and Sales@ both send through the same Gmail
    account's "Send As" aliases). CompanyProfile never owns a provider
    directly - it owns SendingProfiles, which reference a
    ProviderConnection - see ProviderConnection's docstring.

    daily_limit/hourly_limit/min_gap_seconds/max_gap_seconds/
    sending_window_*/sending_days are this profile's DEFAULTS; a
    DeliveryCampaign may override any of them (same "business-specific
    overrides a default" convention as PromptVersion).
    """

    __tablename__ = "sending_profiles"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_connections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    reply_to_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hourly_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_gap_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_gap_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # The BUSINESS's own sending window/timezone - e.g. "only send 08:00-
    # 18:00 Europe/Berlin" - distinct from the RECIPIENT-local business
    # hours the timezone resolver computes per queue item. Both are
    # considered; see DeliveryCampaign.respect_recipient_timezone.
    sending_window_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    sending_window_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    sending_timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # e.g. ["mon","tue","wed","thu","fri"] - mirrors Company.working_days.
    sending_days: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    company_profile: Mapped["CompanyProfile"] = relationship(back_populates="sending_profiles")
    provider_connection: Mapped["ProviderConnection | None"] = relationship(back_populates="sending_profiles")
