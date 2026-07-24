"""
Deterministic, explainable scoring engine. No LLM call required to produce
a first score - every factor is computed independently and stored as its
own entry in score_breakdown, not just folded into a single number.
ai_reasoning (on Prospect) stays null until a future milestone's AI pass
reads this same breakdown and writes a narrative on top of it.

M2 Phase 1b: added a fifth factor (industry_match, using
ICPCriteria.target_industries + Prospect.industry_id - both new/newly-
populated as of Phase 1b/1a) and made every factor's weight configurable
per ICP, stored in ICPCriteria.rules["scoring_weights"] (the existing
JSONB escape hatch - no new column, per the CEO's explicit direction).

Approved default weights (CEO-directed, see docs/architecture/
m2-phase1b-dedup-scoring-architecture.md and the CEO's Phase 1b
architecture-review approval message): Product Relevance 25 / Buyer Type
20 / Industry 20 / Market 20 / Company Size 15 - still summing to 100.
The backend supports fully custom per-ICP weights immediately
(resolve_weights() below); nothing beyond the default preset is exposed
in the UI yet, per the CEO's explicit "refinement 1".

Per the CEO's explicit "refinement 3" (historical scoring), existing
Prospect scores are NEVER automatically recalculated when an ICP's
weights change - score_prospect() is only ever called from
pipeline.py's per-run scoring pass (_score_and_apply(), itself only
called for prospects touched by that specific run), never triggered by
an ICPCriteria update. If a future milestone needs to re-score existing
prospects against new weights, that must be a separate, explicit,
administrative action - not a side effect of anything in this module.

M2 Phase 1b purity note: ICPCriteria/Product/Prospect were moved behind
`TYPE_CHECKING` (mirroring dedup.py's Phase 1a change - see that
module's own docstring for the identical reasoning). Every function in
this module only ever does attribute access on these objects (icp.rules,
prospect.buyer_type_id, ...) - Python doesn't enforce dataclass/type
hints at runtime, so nothing here actually needs the real ORM classes
imported. This is what makes resolve_weights()/_score_industry()/etc.
genuinely unit-testable against lightweight stand-ins, in a sandbox with
no working sqlalchemy install, the same "pure logic, actually executed
in the authoring sandbox" precedent tests/test_discovery_dedup_pure.py
already set.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.icp_criteria import ICPCriteria
    from app.models.product import Product
    from app.models.prospect import Prospect

# Platform default weights - used whenever an ICP has no
# rules["scoring_weights"] override for a given factor (or no override
# at all). Approved 5-factor split (CEO-directed); sums to 100.
WEIGHT_BUYER_TYPE = 20
WEIGHT_MARKET = 20
WEIGHT_COMPANY_SIZE = 15
WEIGHT_PRODUCT_RELEVANCE = 25
WEIGHT_INDUSTRY = 20

DEFAULT_WEIGHTS: dict[str, float] = {
    "buyer_type_match": WEIGHT_BUYER_TYPE,
    "market_match": WEIGHT_MARKET,
    "company_size_match": WEIGHT_COMPANY_SIZE,
    "product_keyword_relevance": WEIGHT_PRODUCT_RELEVANCE,
    "industry_match": WEIGHT_INDUSTRY,
}

# The only valid keys for ICPCriteria.rules["scoring_weights"] / the
# API's scoring_weights convenience field - single source of truth,
# imported by app.schemas.icp_criteria for request validation so the two
# never drift apart.
SCORING_FACTOR_NAMES: frozenset[str] = frozenset(DEFAULT_WEIGHTS)

# A prospect in an explicitly excluded market is force-disqualified
# regardless of every other factor.
EXCLUDED_MARKET_SCORE = 0


@dataclass
class ScoringResult:
    total_score: float
    breakdown: list[dict[str, Any]]
    excluded: bool


def resolve_weights(icp: ICPCriteria) -> dict[str, float]:
    """Merges an ICP's custom per-factor weights (if any, stored in
    rules['scoring_weights']) over the platform defaults - every factor
    key is always present in the result, even if the ICP only overrides
    one. Never mutates icp.rules itself. Tolerant of a malformed/missing
    override (anything that isn't a dict is treated the same as "no
    override at all") - a scoring pass should never crash a discovery
    job over a bad rules blob."""
    custom = (icp.rules or {}).get("scoring_weights")
    if not isinstance(custom, dict):
        return dict(DEFAULT_WEIGHTS)
    return {factor: custom.get(factor, default) for factor, default in DEFAULT_WEIGHTS.items()}


def _country_matches(prospect_country: str | None, countries: list) -> bool:
    if not prospect_country:
        return False
    needle = prospect_country.strip().lower()
    return any(needle == c.name.strip().lower() or needle == c.code.strip().lower() for c in countries)


def _score_buyer_type(prospect: Prospect, icp: ICPCriteria, weight: float) -> dict[str, Any]:
    target_ids = {bt.id for bt in icp.target_buyer_types}
    if not target_ids:
        return {
            "factor": "buyer_type_match", "weight": weight, "matched": None,
            "points": weight, "explanation": "ICP specifies no target buyer types - treated as no preference.",
        }
    matched = prospect.buyer_type_id is not None and prospect.buyer_type_id in target_ids
    return {
        "factor": "buyer_type_match", "weight": weight, "matched": matched,
        "points": weight if matched else 0,
        "explanation": "Prospect's buyer type is one of this ICP's target buyer types." if matched
        else "Prospect's buyer type is not in this ICP's target buyer types (or is unset).",
    }


def _score_market(prospect: Prospect, icp: ICPCriteria, weight: float) -> tuple[dict[str, Any], bool]:
    if _country_matches(prospect.country, icp.excluded_countries):
        return {
            "factor": "market_match", "weight": weight, "matched": False, "points": EXCLUDED_MARKET_SCORE,
            "explanation": f"'{prospect.country}' is explicitly excluded by this ICP - forces disqualification.",
        }, True

    if not icp.target_markets:
        return {
            "factor": "market_match", "weight": weight, "matched": None, "points": weight,
            "explanation": "ICP specifies no target markets - treated as no preference.",
        }, False

    matched = _country_matches(prospect.country, icp.target_markets)
    return {
        "factor": "market_match", "weight": weight, "matched": matched,
        "points": weight if matched else 0,
        "explanation": "Prospect's country is one of this ICP's target markets." if matched
        else f"'{prospect.country}' is not in this ICP's target markets.",
    }, False


def _score_company_size(prospect: Prospect, icp: ICPCriteria, weight: float) -> dict[str, Any]:
    preferred = icp.preferred_company_size or []
    if not preferred:
        return {
            "factor": "company_size_match", "weight": weight, "matched": None,
            "points": weight, "explanation": "ICP specifies no preferred company size - treated as no preference.",
        }
    matched = bool(prospect.company_size_range) and prospect.company_size_range.strip().lower() in [
        p.strip().lower() for p in preferred
    ]
    return {
        "factor": "company_size_match", "weight": weight, "matched": matched,
        "points": weight if matched else 0,
        "explanation": "Prospect's company size is in this ICP's preferred range(s)." if matched
        else "Prospect's company size is outside this ICP's preferred range(s) (or unset).",
    }


def _score_product_relevance(prospect: Prospect, products: list[Product], weight: float) -> dict[str, Any]:
    keywords: set[str] = set()
    for product in products:
        keywords.update(k.strip().lower() for k in (product.keywords or []) if k and k.strip())
        keywords.update(a.strip().lower() for a in (product.applications or []) if a and a.strip())

    text = (prospect.description or "").lower()
    if not keywords or not text:
        return {
            "factor": "product_keyword_relevance", "weight": weight, "matched": None,
            "points": 0, "explanation": "No product keywords/applications or no prospect description to compare against.",
        }

    matched_keywords = sorted(k for k in keywords if k in text)
    # 3+ distinct keyword hits earns full credit; fewer hits scale linearly.
    ratio = min(1.0, len(matched_keywords) / 3)
    points = round(weight * ratio, 1)
    return {
        "factor": "product_keyword_relevance", "weight": weight, "matched": bool(matched_keywords),
        "points": points,
        "explanation": (
            f"Matched keywords/applications: {', '.join(matched_keywords)}." if matched_keywords
            else "None of this business's product keywords/applications appear in the prospect's description."
        ),
    }


def _score_industry(prospect: Prospect, icp: ICPCriteria, weight: float) -> dict[str, Any]:
    """M2 Phase 1b's new fifth factor - mirrors _score_buyer_type's exact
    shape/logic. Relies on Prospect.industry_id, populated by
    app.discovery.normalization's deterministic keyword-match resolver
    (Phase 1a) - a Prospect whose industry never resolved to a known
    Industry row is treated the same as one with no target set: not
    penalized, matched=None."""
    target_ids = {ind.id for ind in icp.target_industries}
    if not target_ids:
        return {
            "factor": "industry_match", "weight": weight, "matched": None,
            "points": weight, "explanation": "ICP specifies no target industries - treated as no preference.",
        }
    matched = prospect.industry_id is not None and prospect.industry_id in target_ids
    return {
        "factor": "industry_match", "weight": weight, "matched": matched,
        "points": weight if matched else 0,
        "explanation": "Prospect's resolved industry is one of this ICP's target industries." if matched
        else "Prospect's resolved industry is not in this ICP's target industries (or never resolved).",
    }


def score_prospect(prospect: Prospect, icp: ICPCriteria, products: list[Product]) -> ScoringResult:
    weights = resolve_weights(icp)
    market_entry, excluded = _score_market(prospect, icp, weights["market_match"])

    if excluded:
        breakdown = [market_entry]
        return ScoringResult(total_score=0.0, breakdown=breakdown, excluded=True)

    breakdown = [
        _score_buyer_type(prospect, icp, weights["buyer_type_match"]),
        market_entry,
        _score_company_size(prospect, icp, weights["company_size_match"]),
        _score_product_relevance(prospect, products, weights["product_keyword_relevance"]),
        _score_industry(prospect, icp, weights["industry_match"]),
    ]
    total = round(sum(entry["points"] for entry in breakdown), 1)
    return ScoringResult(total_score=total, breakdown=breakdown, excluded=False)
