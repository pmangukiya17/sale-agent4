"""
Provider plugin contract. A new provider is a new class implementing
DiscoveryProvider + a registry entry (see registry.py) - never a schema
change and never a change to the pipeline that calls it.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.discovery.context import DiscoveryContext


class ProviderError(Exception):
    """Raised when a provider fails to complete a search. Caught by the
    pipeline, recorded on that provider's DiscoveryJobProviderRun, and does
    not stop other enabled providers in the same job from running."""


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
