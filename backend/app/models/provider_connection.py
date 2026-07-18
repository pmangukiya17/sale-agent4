import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ProviderConnectionStatus


class ProviderConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One OAuth grant to one real mailbox (a Gmail or Microsoft 365 account),
    owned by the business - "business should not directly own providers"
    per the M5 brief is honored literally: CompanyProfile never gets a
    token column, it owns SendingProfiles, and a SendingProfile references
    this row by FK. Decoupled from SendingProfile on purpose (not a 1:1
    embed): one connection (one real mailbox) can back several sending
    identities/aliases, e.g. CEO@ and Sales@ both sending through the same
    Gmail account's "Send As" aliases.

    Deliberately holds NO credential material itself - see
    ProviderCredential's docstring for why that's split into its own
    table/abstraction. This row is the OAuth-flow-level record: which
    mailbox, what scopes, is it currently usable, when was it last
    verified. It is never hard-deleted by Disconnect (see status/
    disconnected_at) so connection history survives independently of
    whether the underlying credential is still present.

    last_verification_at updates on every Verify Connection attempt,
    success or failure. last_verified_at only updates on a SUCCESSFUL
    verification (a fresh OAuth code exchange counts as one). Kept as two
    separate columns deliberately, not one - "last checked 2 minutes ago"
    and "last actually confirmed working 3 days ago" are different, both
    operationally useful facts for a connection-health UI.
    """

    __tablename__ = "provider_connections"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    external_account_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scopes_granted: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[ProviderConnectionStatus] = mapped_column(
        Enum(
            ProviderConnectionStatus,
            name="provider_connection_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ProviderConnectionStatus.CONNECTED,
        nullable=False,
        index=True,
    )
    connected_at: Mapped[datetime | None] = mapped_column(nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_verification_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_verification_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    company_profile: Mapped["CompanyProfile"] = relationship(back_populates="provider_connections")
    credential: Mapped["ProviderCredential | None"] = relationship(
        back_populates="provider_connection", cascade="all, delete-orphan", uselist=False
    )
    # "Which sending identities use this mailbox" - operationally needed by
    # the Disconnect flow (warn/block if actively in use), same "used-by"
    # back-reference precedent as OutreachPlaybook.outreach_requests.
    sending_profiles: Mapped[list["SendingProfile"]] = relationship(back_populates="provider_connection")
