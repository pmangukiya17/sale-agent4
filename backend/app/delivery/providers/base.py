"""
Provider plugin contract - capability-based, per the explicit M5
refinement: a provider does not inherit a capability it doesn't
implement. `EmailConnectionProvider` (the OAuth lifecycle: authorize,
exchange, refresh, verify) is the one contract every provider implements,
since even a future read-only or send-only provider needs *some* way to
authenticate. `EmailSendCapable` and `MailboxReadCapable` are separate,
independently-inheritable interfaces on top of that:

    class GmailProvider(EmailConnectionProvider, EmailSendCapable): ...       # M5
    class GmailProvider(EmailConnectionProvider, EmailSendCapable,
                         MailboxReadCapable): ...                             # M6, additive
    class SMTPProvider(EmailConnectionProvider, EmailSendCapable): ...        # future, send-only

Code that needs to know whether a given provider can do something checks
`isinstance(provider, MailboxReadCapable)` rather than assuming every
registered provider supports every capability - see
provider_supports_capability() below.

MailboxReadCapable is declared now, implemented by nothing in M5 - see
docs/architecture/future-milestones.md note #9 (AI Mailbox Brief). Its
presence here costs nothing until M6 actually adds a class that inherits
it.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar


@dataclass
class OAuthTokenPayload:
    """What a successful authorize/exchange/refresh produces. This is the
    dict shape CredentialStore.save()/load() persist - provider code and
    credential-storage code agree on this shape without either importing
    the other's concrete classes."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scopes: list[str] = field(default_factory=list)
    external_account_email: str | None = None


@dataclass
class ConnectionVerificationResult:
    success: bool
    external_account_email: str | None = None
    detail: str | None = None


@dataclass
class DeliverySendOutcome:
    provider_message_id: str | None
    detail: dict[str, Any] | None = None
    # M6.3 additions - both optional/additive, default None so this
    # dataclass's existing shape (and every M5 caller/test built against
    # it) is unchanged for a provider that doesn't populate them.
    #
    # internet_message_id: the RFC 5322 Message-ID that ended up on the
    # actually-sent email - what a reply's In-Reply-To will reference.
    # GmailProvider mints and sets this itself (it authors the raw MIME
    # directly, so it can guarantee the value). OutlookProvider cannot
    # safely assume Graph will honor a client-supplied Message-ID header,
    # so it reads back whatever Graph generated via the create-draft step
    # of its now-draft-then-send send() implementation - see that
    # module's docstring. dispatch_service stores this directly onto the
    # outbound EmailMessage row it creates; Thread Builder's In-Reply-To/
    # References matching depends on it being accurate, not guessed.
    #
    # provider_thread_id: populated only when the provider's send call
    # itself reveals its native thread id "for free" (Outlook's
    # draft-then-send response includes conversationId before the
    # message is even sent). Purely an optimization for Thread Builder's
    # step-1 fast path - matching still works via internet_message_id
    # alone if this is None.
    internet_message_id: str | None = None
    provider_thread_id: str | None = None


class ProviderAuthError(Exception):
    """Raised when a provider call fails specifically because the
    credential is invalid/expired/revoked - distinct from a generic
    ProviderSendError, so dispatch_service can flip ProviderConnection.status
    to expired/revoked rather than just retrying the send."""


class ProviderSendError(Exception):
    """Raised for a genuine send failure that is NOT an auth problem
    (rate-limited, invalid recipient, transient network error, ...).
    dispatch_service classifies these into RETRY vs FAILED - see its
    docstring."""

    def __init__(self, message: str, *, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


class ProviderSyncError(Exception):
    """M6.2: raised for a genuine incremental-sync failure that is NOT an
    auth problem (rate-limited, malformed delta response, transient
    network error, ...) - the sync-worker's own equivalent of
    ProviderSendError. Auth problems still raise ProviderAuthError (reused
    as-is from the send path - an expired/revoked credential means the
    same thing to sync as it does to send: the connection needs
    reconnecting), so the sync worker only needs to distinguish these two
    exception types, exactly like dispatch_service does today."""


class EmailConnectionProvider(ABC):
    """The OAuth connection lifecycle - shared by every provider
    regardless of which capabilities it implements below."""

    key: ClassVar[str]
    #  The scopes THIS provider requests for send-only M5 use. A future
    #  M6 read capability will need its own, separate scope list - see
    #  MailboxReadCapable's docstring - requested only when a user
    #  actually enables Mailbox Brief, via Reconnect, never upfront here.
    send_scopes: ClassVar[list[str]]

    def is_configured(self) -> bool:
        """Whether this provider's OAuth client id/secret are actually
        set (see .env.example) - added so the route layer (Layer 5) can
        filter an unconfigured provider out of the "connectable
        providers" list rather than offering a Connect button that would
        fail immediately on code exchange. Default True (no prerequisite)
        so a future provider with no such requirement doesn't need to
        override this; Gmail/Outlook override it to check their own
        settings. Deliberately a plain method, not a registry-level
        check, so each provider owns knowledge of its own required
        settings - the registry/route layer never needs to know Gmail's
        settings are named GMAIL_OAUTH_CLIENT_ID/SECRET specifically."""
        return True

    @abstractmethod
    def get_authorize_url(self, state: str, scopes: list[str]) -> str:
        raise NotImplementedError

    @abstractmethod
    def exchange_code(self, code: str) -> OAuthTokenPayload:
        raise NotImplementedError

    @abstractmethod
    def refresh_access_token(self, refresh_token: str) -> OAuthTokenPayload:
        raise NotImplementedError

    @abstractmethod
    def verify(self, credential_payload: dict) -> ConnectionVerificationResult:
        """A cheap, read-only call proving the credential still works
        (e.g. Gmail users.getProfile, Graph GET /me). Must not raise for
        an expired/invalid credential - return success=False with a
        human-readable detail instead; only raise for a genuine
        transport-level failure the caller couldn't have anticipated."""
        raise NotImplementedError


class EmailSendCapable(ABC):
    @abstractmethod
    def send(self, context: "DeliveryContext") -> DeliverySendOutcome:  # noqa: F821 - avoid circular import
        """Sends one already-frozen queue item's content. Must raise
        ProviderAuthError for credential problems and ProviderSendError
        (with permanent=True/False) for everything else - never a bare
        exception type dispatch_service doesn't expect."""
        raise NotImplementedError


class MailboxReadCapable(ABC):
    """M6 extension point. Not implemented by any provider in M5 - see
    this module's docstring. Declared now purely so a future provider
    class adding this is additive, never a redesign of
    EmailConnectionProvider or EmailSendCapable."""

    @abstractmethod
    def fetch_recent_messages(
        self, context: "DeliveryContext", since: datetime, max_results: int  # noqa: F821
    ) -> list[dict[str, Any]]:
        raise NotImplementedError


@dataclass
class RawRecipient:
    """One To/Cc recipient as observed by a provider - the sync-side
    counterpart to DeliverySendOutcome's outbound recipient capture (see
    dispatch_service.py). Kept minimal - email is the only field Thread
    Builder's identity resolution actually needs; name is carried through
    for display purposes only."""

    email: str | None
    name: str | None = None


@dataclass
class RawAttachment:
    """One attachment's metadata as observed by a provider during
    incremental sync - never the file bytes (see Attachment model's
    docstring for why). filename/content_type/size_bytes are best-effort;
    a provider may not always populate all three."""

    provider_attachment_id: str | None
    filename: str | None
    content_type: str | None
    size_bytes: int | None


@dataclass
class RawEmailMessage:
    """One inbound email as normalized by a provider's
    fetch_messages_incremental() - the provider-neutral shape the sync
    worker persists as an EmailMessage row (conversation_id always NULL at
    this point - see email_message.py's docstring for the full lifecycle).
    Every field here maps 1:1 onto an EmailMessage column of the same
    name; this dataclass exists so provider code never constructs an
    EmailMessage ORM object directly (same boundary DeliverySendOutcome
    already draws on the send side - provider code speaks a plain,
    provider-neutral shape, never the ORM).

    direction is deliberately NOT a field here - M6.2 is inbound-only sync
    (see IncrementalSyncCapable's docstring), so every RawEmailMessage this
    milestone ever produces is inbound by construction; the sync worker
    sets EmailMessage.direction itself rather than trusting a
    provider-supplied value that would always be the same thing anyway."""

    provider_message_id: str | None
    provider_thread_id: str | None
    internet_message_id: str | None
    in_reply_to: str | None
    references: str | None
    from_email: str | None
    from_name: str | None
    subject: str | None
    body_text: str | None
    body_html: str | None
    sent_at: datetime | None
    received_at: datetime | None
    has_attachments: bool = False
    attachments: list[RawAttachment] = field(default_factory=list)
    # M6.3 addition - see RawRecipient's own docstring and
    # email_message.py's to_recipients/cc_recipients column note for why
    # this wasn't part of M6.2's original field list.
    to_recipients: list[RawRecipient] = field(default_factory=list)
    cc_recipients: list[RawRecipient] = field(default_factory=list)


@dataclass
class IncrementalSyncResult:
    """What one fetch_messages_incremental() call returns: a page (or the
    full remaining backlog, provider-dependent) of new/changed messages
    plus the opaque cursor to persist for next time. `next_cursor` is
    ALWAYS what the sync worker should save, even when `messages` is empty
    - a quiet inbox still advances the provider's own delta position, and
    saving the old cursor would make the next tick re-request work the
    provider already told us is caught up.

    has_more signals that this single call did not reach the provider's
    caught-up position (e.g. Outlook Graph's @odata.nextLink instead of
    @odata.deltaLink) - the sync worker's own docstring covers how a
    single tick handles this."""

    messages: list[RawEmailMessage]
    next_cursor: str | None
    has_more: bool = False


class IncrementalSyncCapable(ABC):
    """M6.2 extension point - a provider-agnostic, cursor-based interface
    for continuous inbox synchronization, kept deliberately separate from
    MailboxReadCapable (a still-unimplemented, time-windowed one-shot read
    declared in M5 - see that class's own docstring) rather than replacing
    it: the two solve different problems (one-shot bounded read vs.
    ongoing incremental sync) and a provider could plausibly implement
    only one of them.

    Inbound-only for M6.2, by explicit scope: fetch_messages_incremental()
    only ever returns messages the mailbox RECEIVED, never ones it sent.
    Outbound-message correlation (matching a provider's sent-item id back
    to the DeliveryQueueItem that sent it) is a distinct problem reassigned
    to M6.3, not solved by this interface - see OutlookProvider.send()'s
    own docstring for the specific known gap (provider_message_id is
    always None for Outlook sends today) that makes outbound correlation
    non-trivial there.

    read_scopes is this capability's own scope list, deliberately separate
    from EmailConnectionProvider.send_scopes (send-only, requested at
    Connect time) - Mail.Read-class scopes are read/sync-specific and, per
    M5's own established Reconnect-for-more-scopes precedent (see
    connection_service.build_reconnect_authorize_url's docstring), are
    only ever requested when a user actually enables mailbox sync, not
    upfront at every Connect. NOTE: M6.2's scope, as explicitly given by
    product direction, does NOT include building that Reconnect-with-
    expanded-scopes UI/route - see sync_worker.py's module docstring for
    what this means for real end-to-end testing against a live mailbox
    today.
    """

    read_scopes: ClassVar[list[str]]

    @abstractmethod
    def fetch_messages_incremental(
        self, credential_payload: dict, cursor: str | None, max_results: int
    ) -> IncrementalSyncResult:
        """cursor is None on the very first call for a connection (no
        MailboxSyncState.cursor yet) - implementations must treat that as
        "establish a new sync scope", never as "fetch everything since the
        beginning of the mailbox" (see OutlookProvider's implementation
        for how Outlook bounds this). Must raise ProviderAuthError for
        credential problems and ProviderSyncError for everything else -
        same two-exception-type discipline EmailSendCapable.send()
        already establishes for the send path."""
        raise NotImplementedError


def provider_supports_capability(provider: EmailConnectionProvider, capability: type) -> bool:
    """isinstance check wrapped as a named function so call sites read as
    intent ("does this provider support X") rather than a bare isinstance
    scattered through calling code."""
    return isinstance(provider, capability)
