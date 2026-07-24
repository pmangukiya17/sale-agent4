"""
Query Planner - M2 Phase 2: External Research Provider Framework.

Per docs/architecture/m2-discovery-provider-strategy.md Section 11.2
(CEO-approved): rather than the Discovery Engine (or a single "Query-Spec
Builder") constructing one search query, this module generates an
explicit, explainable list of query VARIATIONS from a business's
Products, ICP Buyer Types, Industries, target Countries, Languages, and
optional Synonyms. app.discovery.search_service.SearchService executes
the resulting QueryPlan against one query-driven ("search-type")
provider and merges the results before anything reaches
app.discovery.normalization - see that module's own docstring for what
happens next.

Kept a pure, zero-ORM-dependency module - the SAME discipline already
established by app/discovery/dedup.py and app/discovery/scoring.py
(TYPE_CHECKING-only ORM imports, `from __future__ import annotations`),
specifically so this logic is genuinely unit-testable in a sandbox with
no working sqlalchemy install. Every input here is a plain string/list,
never an ORM row - see app/discovery/pipeline.py's own
`_build_query_plan_input()` for where a real ICPCriteria/Product's
relationships get read and flattened into a QueryPlanInput before this
module ever sees them (the exact same split that function's neighbor,
`_load_known_industries()`, already established for
app.discovery.normalization.resolve_industry()).

Deliberately NOT a full cross-product of every dimension (products x
buyer_types x industries x countries x languages x synonyms) - that
combinatorial explosion is explicitly named as a Phase 4 "scale
hardening" concern in the architecture doc's Section 9, not something to
half-build speculatively now. Phase 2's own strategy: iterate products
(and their keywords) as the primary relevance signal, cross only with
countries (the dimension a query-driven web search API can most usefully
filter/localize by), and layer buyer_type/industry/language/synonym in
as query-string enrichment and explainability metadata on each
variation rather than as additional cartesian dimensions. A hard
MAX_VARIATIONS_PER_PLAN ceiling still applies regardless, as a safety net
- see its own comment below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# A hard ceiling on how many query variations one plan may ever contain -
# the practical, always-on guard against runaway fan-out for a business
# with many products/countries, mirroring the same "a simple ceiling now,
# not true combinatorial optimization" pragmatism already applied by
# app.supervisor.plan_validation's SUPERVISOR_MAX_EXECUTION_DEPTH. Real
# fan-out tuning at production volume is Phase 4's explicit scope (see
# this module's own docstring), not something to guess at here.
MAX_VARIATIONS_PER_PLAN = 50


@dataclass(frozen=True)
class QueryPlanInput:
    """Plain-primitive inputs this module needs - assembled by a caller
    that has ORM access (see app.discovery.pipeline._build_query_plan_input),
    never constructed from ORM rows directly here."""

    product_names: list[str] = field(default_factory=list)
    product_keywords: list[str] = field(default_factory=list)
    buyer_types: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    # product_name -> extra synonym terms to also search for, e.g.
    # {"Cotton Yarn": ["Cotton Thread", "Spun Cotton Yarn"]}. Optional -
    # most businesses have none configured yet.
    synonyms: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class QueryVariation:
    """One concrete query to run against a query-driven provider, plus
    enough metadata to explain WHY this variation exists - the
    "explicit, explainable" requirement from the architecture doc's
    Section 11.2. Never mutated after construction (frozen), same
    discipline as app.discovery.scoring.ScoringResult."""

    query: str
    country: str | None = None
    language: str | None = None
    product_name: str | None = None
    buyer_type: str | None = None
    industry_name: str | None = None
    synonym: str | None = None

    def as_query_spec(self) -> dict[str, Any]:
        """The shape app.discovery.providers.base.DiscoveryProvider.search()
        already expects as its first positional argument - a plain dict,
        so a query-driven provider (BraveSearchProvider) needs no new
        method signature beyond the one every provider already
        implements. Deliberately includes every explainability field,
        not just `query` - a provider MAY ignore fields it doesn't use
        (e.g. a future provider with no country-filter capability), but
        never has less information than this module actually derived."""
        return {
            "query": self.query,
            "country": self.country,
            "language": self.language,
            "product_name": self.product_name,
            "buyer_type": self.buyer_type,
            "industry_name": self.industry_name,
            "synonym": self.synonym,
        }


@dataclass(frozen=True)
class QueryPlan:
    variations: list[QueryVariation] = field(default_factory=list)


def build_query_plan(plan_input: QueryPlanInput) -> QueryPlan:
    """Pure function: primitives in, an explicit QueryPlan out. Never
    raises - a business with zero active products/zero configured ICP
    dimensions simply yields QueryPlan(variations=[]), which
    SearchService.discover() already treats as "nothing to search for
    this provider this run" rather than an error (see that module's own
    docstring) - the same "absence is a valid, non-error state" pattern
    ICPCriteria.minimum_confidence_score=None already establishes
    elsewhere in Discovery."""
    product_terms = [t for t in (plan_input.product_names + plan_input.product_keywords) if t]
    if not product_terms:
        return QueryPlan(variations=[])

    countries: list[str | None] = list(plan_input.countries) if plan_input.countries else [None]
    # Single representative value for the "enrichment" dimensions - see
    # this module's own docstring for why these aren't cross-multiplied.
    # First configured value only (deliberately not "all of them
    # combined into one long query string", which would produce
    # unnatural, low-recall queries a search engine handles poorly).
    buyer_type = plan_input.buyer_types[0] if plan_input.buyer_types else None
    industry = plan_input.industries[0] if plan_input.industries else None
    language = plan_input.languages[0] if plan_input.languages else None

    variations: list[QueryVariation] = []
    seen_queries: set[str] = set()

    def _add(query: str, *, country: str | None, product_name: str, synonym: str | None) -> bool:
        """Returns False once the plan is full - caller stops iterating."""
        normalized_query = " ".join(query.split())  # collapse incidental whitespace
        if not normalized_query or normalized_query in seen_queries:
            return len(variations) < MAX_VARIATIONS_PER_PLAN
        seen_queries.add(normalized_query)
        variations.append(
            QueryVariation(
                query=normalized_query,
                country=country,
                language=language,
                product_name=product_name,
                buyer_type=buyer_type,
                industry_name=industry,
                synonym=synonym,
            )
        )
        return len(variations) < MAX_VARIATIONS_PER_PLAN

    for product_term in product_terms:
        for country in countries:
            base_parts = [product_term]
            if buyer_type:
                base_parts.append(buyer_type)
            if industry:
                base_parts.append(industry)
            if country:
                base_parts.append(country)

            if not _add(" ".join(base_parts), country=country, product_name=product_term, synonym=None):
                return QueryPlan(variations=variations)

            for synonym in plan_input.synonyms.get(product_term, []):
                if not synonym:
                    continue
                synonym_parts = [synonym, *base_parts[1:]]
                if not _add(" ".join(synonym_parts), country=country, product_name=product_term, synonym=synonym):
                    return QueryPlan(variations=variations)

    return QueryPlan(variations=variations)
