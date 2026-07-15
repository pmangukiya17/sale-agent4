"""
Manual document provider - the first concrete ResearchProvider, exact
counterpart to ManualCSVProvider (M1). Needs no external API key or
network call: a business pastes/uploads documents it already has (a
saved copy of the buyer's website text, a PDF extract, a news clipping)
and Research can run today. New providers (real website crawler,
LinkedIn, Google, News, ...) are added the same way: a class + a
PROVIDER_REGISTRY entry, nothing else changes.
"""
from typing import Any

from app.research.context import ResearchContext
from app.research.providers.base import (
    ProviderError,
    ProviderFetchOutcome,
    RawFetchResult,
    ResearchProvider,
)


class ManualDocumentProvider(ResearchProvider):
    key = "manual_document"

    def fetch(self, source_spec: dict[str, Any], context: ResearchContext) -> ProviderFetchOutcome:
        documents = source_spec.get("documents")
        if not isinstance(documents, list):
            raise ProviderError(
                "manual_document provider expects source_spec['documents'] to be a list of document objects"
            )

        results: list[RawFetchResult] = []
        for doc in documents:
            if not isinstance(doc, dict) or not doc.get("document_type"):
                raise ProviderError("each manual_document entry must be an object with at least a 'document_type' field")

            results.append(
                RawFetchResult(
                    document_type=doc["document_type"],
                    source_url=doc.get("source_url"),
                    source_identifier=doc.get("source_identifier"),
                    raw_html=doc.get("raw_html"),
                    raw_json=doc.get("raw_json"),
                    extracted_text=doc.get("extracted_text"),
                    doc_metadata=doc.get("doc_metadata") or {},
                )
            )

        return ProviderFetchOutcome(
            documents=results,
            request_count=len(results),
            api_cost=0,
            token_usage=None,
        )
