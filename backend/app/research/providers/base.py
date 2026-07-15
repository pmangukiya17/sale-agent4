"""
Research provider plugin contract - exact mirror of DiscoveryProvider's
shape (M1). A new provider (Company Website, LinkedIn, Google, News,
Trade Fair sites, Government registries, Import/Export directories,
PDFs, Catalogs, future APIs, ...) is a new class implementing
ResearchProvider + a registry entry (see registry.py) - never a schema
change and never a change to the pipeline that calls it. No provider-
specific concept (a LinkedIn URN, a registry number, an HTML selector)
leaks past RawFetchResult.raw_payload / source_identifier.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.research.context import ResearchContext


class ProviderError(Exception):
    """Raised when a provider fails to complete a fetch. Caught by the
    pipeline, recorded on that provider's ResearchJobProviderRun, and does
    not stop other enabled providers in the same job from running."""


@dataclass
class RawFetchResult:
    """One fetched document as returned by a provider, before any AI
    analysis. Nothing here is ever discarded - raw_html/raw_json/
    extracted_text/doc_metadata are all preserved verbatim regardless of
    what a later analysis pass does with them."""
    document_type: str
    source_url: str | None = None
    source_identifier: str | None = None
    raw_html: str | None = None
    raw_json: dict[str, Any] | None = None
    extracted_text: str | None = None
    doc_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderFetchOutcome:
    documents: list[RawFetchResult]
    request_count: int = 0
    api_cost: float | None = None
    token_usage: int | None = None


class ResearchProvider(ABC):
    """Abstract base every concrete research provider plugin implements."""

    key: ClassVar[str]

    @abstractmethod
    def fetch(self, source_spec: dict[str, Any], context: ResearchContext) -> ProviderFetchOutcome:
        """Fetch whatever documents this provider can find for the
        prospect in context and return them plus execution metrics. Must
        raise ProviderError (not a bare exception type the pipeline
        doesn't expect) on failure."""
        raise NotImplementedError
