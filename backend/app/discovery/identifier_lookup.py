"""
Tier 1 of M2 Phase 1b's three-tier dedup system: exact match on a
government identifier (VAT number or Registration Number) - the
strongest signal available, checked before website/domain (tier 2,
app.discovery.dedup.find_duplicate's website branch) and fuzzy
name+country similarity (tier 3, that same function's fallback).

Deliberately a SEPARATE module from app/discovery/dedup.py, not a new
function added to it - per the CEO's explicit direction ("Keep dedup.py
pure by introducing a separate indexed lookup function rather than
embedding database access inside the matching logic"). dedup.py's pure
functions (normalize_website, normalize_company_name, name_similarity)
have zero runtime sqlalchemy dependency specifically so they can be
unit-tested in a sandbox with no working sqlalchemy install (see
dedup.py's own docstring); this module needs a REAL Session/select
against the prospects table, so it imports sqlalchemy and Prospect for
real, at module level, and is therefore only exercisable against a real
database (covered by the DB-backed e2e suite, same as
find_duplicate()'s own DB-touching caller in pipeline.py - see
tests/test_discovery_dedup_pure.py's docstring for that same
distinction).

Extensibility: IDENTIFIER_FIELDS is the single place a future third/
fourth identifier type (Company Number, EIN, Business Registration ID,
...) gets added - add the column to Prospect, add its name here, done.
find_duplicate_by_identifier() never hard-codes "vat_number" or
"registration_number" anywhere in its query-building logic.
"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.prospect import Prospect

# Every Prospect column that counts as a government identifier for tier-1
# dedup purposes, in priority order (informational only - a match on
# either field is treated as equally definite, see find_duplicate_by_identifier's
# own docstring). Add a new column name here (and to the model/migration)
# to support a new identifier type without touching the lookup logic below.
IDENTIFIER_FIELDS: tuple[str, ...] = ("vat_number", "registration_number")


def find_duplicate_by_identifier(
    db: Session,
    company_profile_id,
    **identifiers: str | None,
) -> Prospect | None:
    """Looks for an existing Prospect, scoped to one company_profile_id,
    whose vat_number OR registration_number exactly equals one of the
    (already-normalized - see app.discovery.normalization.
    normalize_vat_number/normalize_registration_number) values passed in.
    A match on EITHER field is treated as a definite re-sighting of the
    same real company - this is intentionally more permissive than
    requiring both to agree, since a candidate may only ever have one of
    the two identifiers available.

    identifiers: keyword args named after IDENTIFIER_FIELDS - e.g.
    find_duplicate_by_identifier(db, profile_id, vat_number="DE123",
    registration_number="HRB456"). Unknown keys are ignored; None/empty
    values are skipped (never matched as a wildcard). Returns None
    (rather than raising) if no identifier value was actually provided,
    or if none matched - callers should always fall back to
    app.discovery.dedup.find_duplicate() in either case, exactly the way
    pipeline.py already does.
    """
    conditions = []
    for field_name in IDENTIFIER_FIELDS:
        value = identifiers.get(field_name)
        if value:
            conditions.append(getattr(Prospect, field_name) == value)

    if not conditions:
        return None

    stmt = select(Prospect).where(Prospect.company_profile_id == company_profile_id, or_(*conditions))
    return db.scalars(stmt).first()
