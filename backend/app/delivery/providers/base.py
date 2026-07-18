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


def provider_supports_capability(provider: EmailConnectionProvider, capability: type) -> bool:
    """isinstance check wrapped as a named function so call sites read as
    intent ("does this provider support X") rather than a bare isinstance
    scattered through calling code."""
    return isinstance(provider, capability)
