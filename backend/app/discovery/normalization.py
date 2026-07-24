"""
Normalization pipeline stage.

M2 Phase 1a. Runs on every RawProviderResult, from every provider
(today's ManualCSVProvider rows, and - once M2's approved provider
strategy lands in Phase 2 - real search-derived candidates from the
Search Service), before Validation and Deduplication. Produces one
canonical NormalizedCandidate shape regardless of which provider
produced the raw candidate.

That shape is what gets written into
DiscoveryProviderResult.normalized_payload - a column that already
existed in the schema (M1) but, before this module, was populated ad
hoc inline in pipeline.py with the raw fields copied straight through,
no real normalization applied. No schema change here - this module
gives that existing column a real, consistent producer for the first
time. See docs/architecture/m2-discovery-provider-strategy.md Section 4
for the full design rationale.

Deliberately zero-dependency at the top of this module (no sqlalchemy
anywhere in the import chain) - same reasoning as
app/delivery/scope_utils.py: this is what makes normalize_candidate()
itself genuinely unit-testable, including in sandboxes without a
working sqlalchemy install. Reuses dedup.py's existing
normalize_website()/normalize_company_name() rather than
re-implementing the same regex twice - the two modules describe two
different pipeline stages over the same underlying "clean this string
up" logic, not two competing implementations of it. (dedup.py's own
top-level import of the Prospect model was moved behind
`TYPE_CHECKING` as part of this same change specifically so that reuse
would not drag sqlalchemy into this module's import chain - see
dedup.py's own docstring/comment for that change.)

M2 Phase 1b: added normalize_vat_number()/normalize_registration_number()
and threaded vat_number/registration_number/email through
NormalizedCandidate and normalize_candidate(). These two identifiers
feed app.discovery.identifier_lookup.find_duplicate_by_identifier() (a
separate, DB-touching module - see that module's own docstring for why
it isn't here) as tier 1 of the now three-tier dedup system; this
module only ever cleans the string, it never queries anything.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.discovery.dedup import normalize_company_name, normalize_website

# A handful of aliases for country forms providers/humans actually type in
# practice - not a full ISO-3166 table (that table, and whether a country
# is a *valid, targetable* one at all, is a Validation-layer concern - see
# validation.py - not a Normalization one). Normalization only cleans
# formatting; it never rejects or validates anything.
_COUNTRY_ALIASES: dict[str, str] = {
    "usa": "United States",
    "u.s.a": "United States",
    "u.s.a.": "United States",
    "us": "United States",
    "uk": "United Kingdom",
    "u.k": "United Kingdom",
    "u.k.": "United Kingdom",
    "uae": "United Arab Emirates",
}


@dataclass(frozen=True)
class IndustryRef:
    """Plain (id, name) pair for one known Industry row. Deliberately not
    the real Industry ORM model - keeps this module free of any ORM/DB
    dependency. Pipeline code builds a list of these once per job from
    the real, active Industry rows and passes it in; normalize_candidate()
    never queries anything itself."""

    id: str
    name: str


@dataclass
class NormalizedCandidate:
    """The canonical, cleaned-up shape every RawProviderResult becomes,
    regardless of which provider produced it. Validation and
    Deduplication should read from this, not from the raw provider
    fields directly."""

    name: str
    website: str | None
    country: str | None
    industry_raw: str | None
    industry_id: str | None
    # "exact" | "keyword" | None - explainable, never a silent guess. See
    # resolve_industry()'s own docstring for what each value means.
    industry_match_method: str | None
    company_size_range: str | None
    description: str | None
    # M2 Phase 1b - see this module's own docstring.
    vat_number: str | None
    registration_number: str | None
    email: str | None

    def as_payload(self) -> dict:
        """The shape written to DiscoveryProviderResult.normalized_payload."""
        return {
            "name": self.name,
            "website": self.website,
            "country": self.country,
            "industry_raw": self.industry_raw,
            "industry_id": self.industry_id,
            "industry_match_method": self.industry_match_method,
            "company_size_range": self.company_size_range,
            "description": self.description,
            "vat_number": self.vat_number,
            "registration_number": self.registration_number,
            "email": self.email,
        }


def normalize_country(country: str | None) -> str | None:
    """Cleans whitespace and expands a small set of common aliases
    (USA/UK/UAE/...) to their full form. Never rejects a country string -
    an unrecognized value passes through unchanged (only whitespace-
    cleaned). Whether a country is valid/targetable is Validation's job."""
    if not country:
        return None
    cleaned = " ".join(country.strip().split())
    if not cleaned:
        return None
    alias = _COUNTRY_ALIASES.get(cleaned.lower())
    return alias or cleaned


def _normalize_identifier(value: str | None) -> str | None:
    """Shared cleanup for both government identifier types: uppercase,
    strip surrounding whitespace, and drop internal spaces/dashes/dots -
    the punctuation providers/humans use as visual separators
    ("DE 123 456 789", "DE-123-456-789") but that isn't part of the
    identifier's actual value. This maximizes recall for the exact-match
    lookup in app.discovery.identifier_lookup, at the cost of being
    unable to distinguish two identifiers that differ ONLY in separator
    placement - an acceptable trade-off since no real identifier scheme
    assigns different meaning to two values that differ only that way."""
    if not value or not value.strip():
        return None
    cleaned = re.sub(r"[\s\-.]+", "", value.strip().upper())
    return cleaned or None


def normalize_vat_number(value: str | None) -> str | None:
    """Kept as its own named function (rather than callers using
    _normalize_identifier directly) so VAT-specific formatting rules can
    be added later - e.g. per-country VAT prefix validation - without
    touching registration_number's normalization. See this module's own
    docstring / the architecture doc's "government identifiers" section
    for why the two are modeled as separate identifier types."""
    return _normalize_identifier(value)


def normalize_registration_number(value: str | None) -> str | None:
    """See normalize_vat_number()'s docstring - identical logic today,
    kept as a separate function for the same future-extensibility
    reason."""
    return _normalize_identifier(value)


def resolve_industry(
    industry_raw: str | None, known_industries: list[IndustryRef]
) -> tuple[str | None, str | None]:
    """Attempts to resolve a provider's free-text industry onto the
    platform's Industry reference table, deterministically and
    explainably - never an AI call, never a silent best-guess. This is
    the fix for a real, previously-confirmed gap: Prospect.industry_id
    existed in the schema since M1 but nothing ever set it - every
    Prospect had industry_raw populated and industry_id left null
    forever. This function (and pipeline.py wiring it in) is what
    starts populating it, with zero schema change.

    Returns (industry_id, match_method):
      - (id, "exact")   - normalized industry_raw exactly equals a known
                          industry's normalized name.
      - (id, "keyword") - industry_raw contains a known industry's full
                          name as a substring, or vice versa (handles a
                          provider saying "Textiles & Apparel" resolving
                          to a known industry named "Textiles").
      - (None, None)    - no confident match. industry_raw is kept
                          verbatim on the candidate regardless - it is
                          never discarded just because it didn't resolve.
    """
    if not industry_raw or not known_industries:
        return None, None

    # normalize_company_name's suffix/punctuation-stripping logic is named
    # for company names but is exactly the "lowercase, strip punctuation,
    # collapse whitespace" behavior industry-name matching needs too -
    # reused rather than re-implemented.
    normalized_raw = normalize_company_name(industry_raw)
    if not normalized_raw:
        return None, None

    for industry in known_industries:
        if normalize_company_name(industry.name) == normalized_raw:
            return industry.id, "exact"

    for industry in known_industries:
        normalized_name = normalize_company_name(industry.name)
        if not normalized_name:
            continue
        if normalized_name in normalized_raw or normalized_raw in normalized_name:
            return industry.id, "keyword"

    return None, None


def normalize_candidate(
    *,
    name: str,
    website: str | None,
    country: str | None,
    industry_raw: str | None,
    company_size_range: str | None,
    description: str | None,
    known_industries: list[IndustryRef] | None = None,
    vat_number: str | None = None,
    registration_number: str | None = None,
    email: str | None = None,
) -> NormalizedCandidate:
    """The single entry point every provider's raw result passes through
    before Validation/Deduplication. Takes discrete fields (matching this
    package's existing convention in dedup.find_duplicate) rather than a
    RawProviderResult object, so this module never needs to import
    app.discovery.providers.base and stays independent of the provider
    layer entirely.

    vat_number/registration_number/email are optional (default None) so
    every existing caller keeps working unchanged - only
    app/discovery/pipeline.py's M2 Phase 1b wiring passes them."""
    industry_id, match_method = resolve_industry(industry_raw, known_industries or [])
    return NormalizedCandidate(
        name=" ".join(name.strip().split()) if name else name,
        website=normalize_website(website),
        country=normalize_country(country),
        industry_raw=industry_raw,
        industry_id=industry_id,
        industry_match_method=match_method,
        company_size_range=company_size_range.strip() if company_size_range else company_size_range,
        description=description,
        vat_number=normalize_vat_number(vat_number),
        registration_number=normalize_registration_number(registration_number),
        email=email.strip() if email else None,
    )
