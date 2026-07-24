"""
Provider plugin contract. A new provider is a new class implementing
DiscoveryProvider + a registry entry (see registry.py) - never a schema
change and never a change to the pipeline that calls it.

M2 Phase 2 additions: `health()`/`capabilities()`/`provider_name()` are
new, deliberately NON-abstract methods with safe defaults - adding them
as required abstract methods would force every existing/future provider
(starting with ManualCSVProvider) to implement stubs it doesn't actually
need, for no real benefit. `health()` mirrors
app.ai_gateway.providers.base.ProviderClient.is_configured()'s own
precedent exactly: a cheap, no-network readiness check the Provider
Registry/Search Service call before ever attempting a real search - see
registry.py's `iter_enabled_providers()` and search_service.py's
`SearchService.discover()`. A retryable ProviderError hierarchy is also
added here, mirroring app.ai_gateway.errors.GatewayError's own
`retryable` flag convention (see that module's docstring for the full
reasoning) - applied one layer down, to a single provider's own internal
retry policy (see brave_search.py), not to Discovery's job-level
provider-to-provider fallback (which app.discovery.pipeline already
handles today, unchanged, by simply continuing to the next
provider_key on any ProviderError).

`from __future__ import annotations` + a TYPE_CHECKING-only
DiscoveryContext import (added this phase) - same discipline already
established by app/discovery/dedup.py and app/discovery/scoring.py (see
their own docstrings). DiscoveryContext's own module eagerly imports
real ORM model classes (CompanyProfile, ICPCriteria, Product,
KnowledgeBase), which pulls in sqlalchemy - importing it here at RUNTIME
would make this module (and therefore anything importing it, including
app.discovery.search_service) require a working sqlalchemy install just
to type-hint one method parameter. Guarding it behind TYPE_CHECKING
means this module - and everything that only needs DiscoveryProvider/
ProviderError/RawProviderResult/ProviderSearchOutcome from it - stays
importable with zero third-party dependencies, exactly like
ManualCSVProvider's actual runtime behavior never needed sqlalchemy
either.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from app.discovery.context import DiscoveryContext


class ProviderError(Exception):
    """Raised when a provider fails to complete a search. Caught by the
    pipeline, recorded on that provider's DiscoveryJobProviderRun, and does
    not stop other enabled providers in the same job from running.

    `retryable` - worth immediately retrying the SAME provider (bounded by
    that provider's own retry-count setting, e.g.
    settings.BRAVE_SEARCH_MAX_RETRIES)? True for transient/provider-side
    failures; False for anything that would fail identically on a retry
    (e.g. a bad API key). Read generically by a provider's own internal
    retry loop - never branched on by app.discovery.pipeline or
    app.discovery.search_service, which only ever care that SOME
    ProviderError was raised, exactly as before this phase."""

    retryable: bool = False


class ProviderTimeoutError(ProviderError):
    """The request exceeded the provider's own configured timeout, on
    every attempt its retry policy allowed."""

    retryable = True


class ProviderRateLimitError(ProviderError):
    """The provider's own rate limit was hit (HTTP 429 or equivalent) on
    every attempt its retry policy allowed."""

    retryable = True


class ProviderUnavailableError(ProviderError):
    """A transient provider-side failure (5xx, connection reset, etc.) on
    every attempt its retry policy allowed."""

    retryable = True


class ProviderAuthError(ProviderError):
    """Bad/missing API key or credential - never worth retrying (retrying
    with the same credentials cannot succeed). A well-behaved provider's
    own health() should catch a MISSING key before this is ever reached;
    this is for a key that is present but rejected by the provider
    itself."""

    retryable = False


@dataclass
class RawContactResult:
    """One person surfaced alongside a RawProviderResult."""
    name: str | None = None
    role: str | None = None
    department: str | None = None
    decision_maker_level: str | None = None  # matches DecisionMakerLevel values; "unknown" if not provided
    email: str | None = None
    phone: str | None = None
    confidence: float | None = None


@dataclass
class RawProviderResult:
    """One candidate company as returned by a provider, before dedup or
    scoring. raw_payload is preserved byte-for-byte (as a dict) regardless
    of what normalized fields below were extracted from it."""
    name: str
    raw_payload: dict[str, Any]
    website: str | None = None
    country: str | None = None
    industry_raw: str | None = None
    company_size_range: str | None = None
    description: str | None = None
    source_url: str | None = None
    # How much this one occurrence should be trusted (0-1). Distinct from
    # any per-provider default - a provider can vary this per result.
    provider_confidence: float | None = None
    contacts: list[RawContactResult] = field(default_factory=list)
    # M2 Phase 1b: government identifiers, fed through
    # app.discovery.normalization.normalize_candidate() and then tier 1
    # of dedup (app.discovery.identifier_lookup). All optional -
    # ManualCSVProvider is the only provider that populates them today;
    # a real search-derived provider (M2 Phase 2+) may rarely surface
    # either. email is a company-level contact email, not a dedup
    # signal (see Prospect.email's own docstring).
    vat_number: str | None = None
    registration_number: str | None = None
    email: str | None = None


@dataclass
class ProviderSearchOutcome:
    results: list[RawProviderResult]
    request_count: int = 0
    api_cost: float | None = None
    token_usage: int | None = None


class DiscoveryProvider(ABC):
    """Abstract base every concrete provider plugin implements."""

    key: ClassVar[str]

    @abstractmethod
    def search(self, query_spec: dict[str, Any], context: DiscoveryContext) -> ProviderSearchOutcome:
        """Run one search against this provider and return its raw results
        plus execution metrics. Must raise ProviderError (not a bare
        exception type the pipeline doesn't expect) on failure."""
        raise NotImplementedError

    def provider_name(self) -> str:
        """Human-readable name for logs/UI - defaults to `key`. Override
        only if a provider wants a friendlier display name than its
        registry key (e.g. "Brave Search" vs "brave_search")."""
        return self.key

    def health(self) -> bool:
        """Cheap, no-network readiness check - never makes a real call,
        mirrors app.ai_gateway.providers.base.ProviderClient.is_configured()
        exactly. Default True: most providers (ManualCSVProvider today)
        need no external configuration at all, so "ready" is the correct
        default rather than forcing every provider to override this just
        to return True. A provider that DOES need configuration (an API
        key, a feature flag) overrides this - see
        BraveSearchProvider.health() for the convention every future
        query-driven provider should follow. Checked by
        registry.iter_enabled_providers() and by
        SearchService.discover() before attempting a real search."""
        return True

    def capabilities(self) -> dict[str, Any]:
        """Static, non-network description of what this provider can do -
        e.g. which query_spec fields it actually uses, its rough rate
        limit, whether results include contacts. Default: empty dict
        (no claims made). Never raises, never makes a network call. Read
        by admin/diagnostic tooling only - app.discovery.pipeline and
        app.discovery.search_service never branch on its contents, so an
        empty dict is always a safe, non-breaking default."""
        return {}
