"""
Manual/CSV import provider - the first concrete DiscoveryProvider. Needs no
external API key or network call, so it's fully testable and gives a
business a working way to bootstrap Discovery (paste or upload a list of
candidate buyers) before any real scraping/search-API provider is wired
up. New providers are added the same way: a class + a PROVIDER_REGISTRY
entry, nothing else changes.
"""
from typing import Any

from app.discovery.context import DiscoveryContext
from app.discovery.providers.base import (
    DiscoveryProvider,
    ProviderError,
    ProviderSearchOutcome,
    RawContactResult,
    RawProviderResult,
)


class ManualCSVProvider(DiscoveryProvider):
    key = "manual_csv"

    def search(self, query_spec: dict[str, Any], context: DiscoveryContext) -> ProviderSearchOutcome:
        rows = query_spec.get("rows")
        if not isinstance(rows, list):
            raise ProviderError("manual_csv provider expects query_spec['rows'] to be a list of row objects")

        results: list[RawProviderResult] = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("name"):
                raise ProviderError("each manual_csv row must be an object with at least a 'name' field")

            contacts = [
                RawContactResult(
                    name=c.get("name"),
                    role=c.get("role"),
                    department=c.get("department"),
                    decision_maker_level=c.get("decision_maker_level"),
                    email=c.get("email"),
                    phone=c.get("phone"),
                    confidence=c.get("confidence"),
                )
                for c in row.get("contacts", [])
                if isinstance(c, dict)
            ]

            results.append(
                RawProviderResult(
                    name=row["name"],
                    website=row.get("website"),
                    country=row.get("country"),
                    industry_raw=row.get("industry"),
                    company_size_range=row.get("company_size_range"),
                    description=row.get("description"),
                    source_url=row.get("source_url"),
                    # User-supplied rows are the most directly trustworthy
                    # source available - a human typed this in deliberately.
                    provider_confidence=1.0,
                    contacts=contacts,
                    raw_payload=row,
                    # M2 Phase 1b - see RawProviderResult's own docstring.
                    vat_number=row.get("vat_number"),
                    registration_number=row.get("registration_number"),
                    email=row.get("email"),
                )
            )

        return ProviderSearchOutcome(
            results=results,
            request_count=len(results),
            api_cost=0,
            token_usage=None,
        )
