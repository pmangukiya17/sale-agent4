"""
Two-tier duplicate detection, deliberately not fully automatic in the
ambiguous band. No new Postgres extension (e.g. pg_trgm) required -
comparisons run in Python against prospects already scoped to one
company_profile_id, which is a small enough set for this to be fine at
M1's scale.

M2 Phase 1a note: the Prospect import below was moved behind
`TYPE_CHECKING` (with `from __future__ import annotations` making every
annotation in this module a lazily-evaluated string) so this module has
zero runtime dependency on sqlalchemy. Prospect was only ever used here
as a type hint, never at runtime - dataclasses don't enforce field
types - so this is a behavior-neutral change. It's what lets
app/discovery/normalization.py reuse normalize_website()/
normalize_company_name() from here without dragging the ORM into a
module that's otherwise designed to be independently unit-testable
(same reasoning as app/delivery/scope_utils.py).

M2 Phase 1b note: dedup is now a THREE-tier system overall, but this
module still only ever implements tiers 2 and 3 - website/domain exact
match (tier 2, see find_duplicate() below) and fuzzy name+country
similarity (tier 3, the two thresholds below). Tier 1 - exact match on
VAT number or Registration Number, the strongest signal - lives in the
new app/discovery/identifier_lookup.py, deliberately NOT here: that
tier needs a real, indexed database query (find the one existing
Prospect row with this exact vat_number/registration_number across
potentially many thousands of prospects for a company_profile_id), and
folding that query into this module would drag a real sqlalchemy
Session/select import back into the top of this file - exactly what the
Phase 1a TYPE_CHECKING change above was done to avoid. pipeline.py calls
identifier_lookup.find_duplicate_by_identifier() FIRST and only falls
back to this module's find_duplicate() if that returns no match.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.prospect import Prospect

# Above this, treat as the same real-world company - update, don't insert.
DEFINITE_MATCH_THRESHOLD = 0.85
# Between this and DEFINITE_MATCH_THRESHOLD, flag for human review instead
# of silently merging or silently treating as distinct.
POTENTIAL_MATCH_THRESHOLD = 0.6

_LEGAL_SUFFIXES = re.compile(
    r"\b(ltd|inc|gmbh|pvt ltd|pvt\.? ltd\.?|llc|co|corp|corporation|limited|plc|srl|bv|sa|ag|s\.a\.|s\.r\.l\.)\b\.?",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_WHITESPACE = re.compile(r"\s+")


def normalize_website(url: str | None) -> str | None:
    if not url:
        return None
    value = url.strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^www\.", "", value)
    value = value.rstrip("/")
    return value or None


def normalize_company_name(name: str | None) -> str:
    if not name:
        return ""
    value = name.lower()
    value = _LEGAL_SUFFIXES.sub("", value)
    value = _NON_ALNUM.sub(" ", value)
    value = _WHITESPACE.sub(" ", value).strip()
    return value


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_company_name(a), normalize_company_name(b)).ratio()


@dataclass
class DuplicateMatch:
    prospect: Prospect
    confidence: float
    is_definite: bool


def find_duplicate(
    candidates: list[Prospect],
    *,
    name: str,
    website: str | None,
    country: str | None,
) -> DuplicateMatch | None:
    """
    candidates: existing prospects for the same company_profile_id (plus
    any created earlier in the same job), checked against one new result.
    Website match is checked first and short-circuits to a definite match;
    otherwise falls back to fuzzy name + country similarity.
    """
    normalized_new_website = normalize_website(website)
    if normalized_new_website:
        for candidate in candidates:
            if normalize_website(candidate.website) == normalized_new_website:
                return DuplicateMatch(prospect=candidate, confidence=1.0, is_definite=True)

    best: DuplicateMatch | None = None
    for candidate in candidates:
        if country and candidate.country and candidate.country.strip().lower() != country.strip().lower():
            continue
        score = name_similarity(name, candidate.name)
        if score < POTENTIAL_MATCH_THRESHOLD:
            continue
        if best is None or score > best.confidence:
            best = DuplicateMatch(prospect=candidate, confidence=score, is_definite=score >= DEFINITE_MATCH_THRESHOLD)

    return best
