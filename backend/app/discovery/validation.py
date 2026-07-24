"""
Validation pipeline stage.

M2 Phase 1a. Runs on every NormalizedCandidate, between Normalization
and Deduplication (see normalization.py's own docstring for the full
stage ordering: Provider -> Raw Candidate -> Normalization ->
Validation -> Deduplication -> Research Queue).

Answers a different question than Deduplication: "is this a
well-formed, plausibly real candidate at all?" - not "have we seen this
company before?" Duplicate-confidence scoring stays exclusively in
app/discovery/dedup.py; conflating the two concerns is exactly what
this stage is designed to avoid. See
docs/architecture/m2-discovery-provider-strategy.md Section 5 for the
full design rationale, including the explicit correction that
duplicate-confidence does not belong in this module's check list even
though an earlier draft of the requirements suggested it might.

A failed check never silently discards a candidate - pipeline.py is
expected to still record the raw/normalized data (DiscoveryProviderResult
already exists for exactly this - append-only, one row per raw hit
regardless of outcome) and simply skip creating/updating a Prospect
from a candidate that fails validation, keeping the reasons for later
inspection rather than the candidate just quietly vanishing.

Zero-dependency by design - no sqlalchemy import anywhere in this
module - same reasoning as normalization.py and
app/delivery/scope_utils.py.

M2 Phase 1b: added check_identifier_format(), a deliberately shallow
structural sanity check on vat_number/registration_number - not a full
per-country regex validator (out of scope; every real VAT/registration
scheme has its own format). It exists only to keep an obviously-garbage
value (empty after stripping, or containing no alphanumeric characters
at all) from ever reaching tier 1 of dedup at confidence 1.0 - see
app/discovery/identifier_lookup.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

# A deliberately conservative domain-syntax check (RFC 1035-ish, not a
# full RFC parser) - good enough to catch "not a domain at all" without
# false-rejecting real edge-case domains this pipeline is unlikely to
# ever see in practice.
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)

# Names that are clearly search/directory boilerplate rather than a real
# company name - not exhaustive, just the obvious cases a snippet-derived
# candidate (M2 Phase 2's Brave-derived results, in particular - see the
# provider strategy doc's Section 2 "Candidate Extraction" note on why
# search-derived names are the weakest-quality names in the pipeline)
# can produce.
_BOILERPLATE_NAME_PATTERNS = (
    re.compile(r"^home\b", re.IGNORECASE),
    re.compile(r"^sitemap\b", re.IGNORECASE),
    re.compile(r"\blogin\b", re.IGNORECASE),
    re.compile(r"page not found", re.IGNORECASE),
    re.compile(r"^untitled", re.IGNORECASE),
)


@dataclass
class ValidationCheck:
    check: str
    passed: bool
    detail: str | None = None


@dataclass
class ValidationResult:
    """Explainable, like score_breakdown and DuplicateMatch elsewhere in
    this package - never a bare pass/fail with no reason attached."""

    passed: bool
    checks: list[ValidationCheck] = field(default_factory=list)

    def as_payload(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [
                {"check": c.check, "passed": c.passed, "detail": c.detail} for c in self.checks
            ],
        }


def check_required_fields(name: str | None, website: str | None, country: str | None) -> ValidationCheck:
    if name and name.strip() and (website or country):
        return ValidationCheck("required_fields", passed=True)
    return ValidationCheck(
        "required_fields",
        passed=False,
        detail="A candidate needs a name plus at least one of website/country to be usable.",
    )


def check_name_quality(name: str | None) -> ValidationCheck:
    if not name or not name.strip():
        return ValidationCheck("name_quality", passed=False, detail="Company name is empty.")
    for pattern in _BOILERPLATE_NAME_PATTERNS:
        if pattern.search(name):
            return ValidationCheck(
                "name_quality", passed=False,
                detail=f"'{name}' looks like search/page boilerplate, not a company name.",
            )
    if len(name.strip()) < 2:
        return ValidationCheck(
            "name_quality", passed=False, detail=f"'{name}' is too short to be a plausible company name."
        )
    return ValidationCheck("name_quality", passed=True)


def check_domain_syntax(website: str | None) -> ValidationCheck:
    if not website:
        return ValidationCheck(
            "domain_syntax", passed=True, detail="No website provided - not a failure, just nothing to check."
        )
    if _DOMAIN_RE.match(website):
        return ValidationCheck("domain_syntax", passed=True)
    return ValidationCheck("domain_syntax", passed=False, detail=f"'{website}' is not a syntactically valid domain.")


def check_country_known(country: str | None, known_countries: set[str] | None = None) -> ValidationCheck:
    if not country:
        return ValidationCheck(
            "country_known", passed=True, detail="No country provided - not a failure, just nothing to check."
        )
    if known_countries is None:
        return ValidationCheck(
            "country_known", passed=True, detail="No known-country list supplied - check skipped, not failed."
        )
    if country.strip().lower() in {c.strip().lower() for c in known_countries}:
        return ValidationCheck("country_known", passed=True)
    return ValidationCheck(
        "country_known", passed=False, detail=f"'{country}' is not in the configured list of known countries."
    )


def check_website_reachable(
    website: str | None, *, reachability_checker: Callable[[str], bool] | None = None
) -> ValidationCheck:
    """Deliberately not wired to a live HTTP call by default. Per
    docs/architecture/m2-discovery-provider-strategy.md Sections 5 and 9,
    a real per-candidate reachability check is a network call that needs
    its own rate-limit/async budget at real scale - infrastructure that
    doesn't exist yet with only ManualCSVProvider registered (Phase 1),
    and that this sub-phase deliberately does not build ahead of an
    actual network-calling provider needing it (Phase 2). Callers may
    inject a reachability_checker once that infrastructure exists; until
    then this check is always skipped (passed=True, explicitly marked as
    not attempted) rather than silently pretending to have checked
    something it didn't."""
    if not website:
        return ValidationCheck(
            "website_reachable", passed=True, detail="No website provided - not a failure, just nothing to check."
        )
    if reachability_checker is None:
        return ValidationCheck(
            "website_reachable", passed=True,
            detail="Reachability check not wired up yet (Phase 1) - skipped, not attempted.",
        )
    try:
        reachable = reachability_checker(website)
    except Exception as exc:  # a broken checker should never crash a discovery job
        return ValidationCheck(
            "website_reachable", passed=True,
            detail=f"Reachability check itself raised ({exc}) - treated as skipped, not as a validation failure.",
        )
    if reachable:
        return ValidationCheck("website_reachable", passed=True)
    return ValidationCheck("website_reachable", passed=False, detail=f"'{website}' did not respond to a reachability check.")


def check_identifier_format(vat_number: str | None, registration_number: str | None) -> ValidationCheck:
    """See this module's own docstring - shallow sanity check only.
    Values are expected to already be normalize_vat_number()/
    normalize_registration_number()-cleaned (uppercased, separators
    stripped) by the time they reach here; this only rejects a value
    with literally no alphanumeric content."""
    for label, value in (("vat_number", vat_number), ("registration_number", registration_number)):
        if value is None:
            continue
        if not any(ch.isalnum() for ch in value):
            return ValidationCheck(
                "identifier_format", passed=False,
                detail=f"{label} '{value}' contains no alphanumeric characters - not a plausible identifier.",
            )
    return ValidationCheck("identifier_format", passed=True)


def validate_candidate(
    *,
    name: str | None,
    website: str | None,
    country: str | None,
    known_countries: set[str] | None = None,
    reachability_checker: Callable[[str], bool] | None = None,
    vat_number: str | None = None,
    registration_number: str | None = None,
) -> ValidationResult:
    """The single entry point every NormalizedCandidate passes through
    before Deduplication. Duplicate-confidence is deliberately absent
    from this check list - that is app.discovery.dedup's job, not this
    module's (see this module's own docstring).

    vat_number/registration_number are optional (default None) so every
    existing caller keeps working unchanged - only pipeline.py's M2
    Phase 1b wiring passes them (already-normalized values)."""
    checks = [
        check_required_fields(name, website, country),
        check_name_quality(name),
        check_domain_syntax(website),
        check_country_known(country, known_countries),
        check_website_reachable(website, reachability_checker=reachability_checker),
        check_identifier_format(vat_number, registration_number),
    ]
    return ValidationResult(passed=all(c.passed for c in checks), checks=checks)
