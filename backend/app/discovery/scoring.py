"""
Deterministic, explainable scoring engine. No LLM call required to produce
a first score - every factor is computed independently and stored as its
own entry in score_breakdown, not just folded into a single number.
ai_reasoning (on Prospect) stays null until a future milestone's AI pass
reads this same breakdown and writes a narrative on top of it.
"""
from dataclasses import dataclass, field
from typing import Any

from app.models.icp_criteria import ICPCriteria
from app.models.product import Product
from app.models.prospect import Prospect

# Default weights, summing to 100. Not yet user-configurable - the first
# thing to revisit if these defaults don't hold up in practice.
WEIGHT_BUYER_TYPE = 25
WEIGHT_MARKET = 25
WEIGHT_COMPANY_SIZE = 20
WEIGHT_PRODUCT_RELEVANCE = 30

# A prospect in an explicitly excluded market is force-disqualified
# regardless of every other factor.
EXCLUDED_MARKET_SCORE = 0


@dataclass
class ScoringResult:
    total_score: float
    breakdown: list[dict[str, Any]]
    excluded: bool


def _country_matches(prospect_country: str | None, countries: list) -> bool:
    if not prospect_country:
        return False
    needle = prospect_country.strip().lower()
    return any(needle == c.name.strip().lower() or needle == c.code.strip().lower() for c in countries)


def _score_buyer_type(prospect: Prospect, icp: ICPCriteria) -> dict[str, Any]:
    target_ids = {bt.id for bt in icp.target_buyer_types}
    if not target_ids:
        return {
            "factor": "buyer_type_match", "weight": WEIGHT_BUYER_TYPE, "matched": None,
            "points": WEIGHT_BUYER_TYPE, "explanation": "ICP specifies no target buyer types - treated as no preference.",
        }
    matched = prospect.buyer_type_id is not None and prospect.buyer_type_id in target_ids
    return {
        "factor": "buyer_type_match", "weight": WEIGHT_BUYER_TYPE, "matched": matched,
        "points": WEIGHT_BUYER_TYPE if matched else 0,
        "explanation": "Prospect's buyer type is one of this ICP's target buyer types." if matched
        else "Prospect's buyer type is not in this ICP's target buyer types (or is unset).",
    }


def _score_market(prospect: Prospect, icp: ICPCriteria) -> tuple[dict[str, Any], bool]:
    if _country_matches(prospect.country, icp.excluded_countries):
        return {
            "factor": "market_match", "weight": WEIGHT_MARKET, "matched": False, "points": EXCLUDED_MARKET_SCORE,
            "explanation": f"'{prospect.country}' is explicitly excluded by this ICP - forces disqualification.",
        }, True

    if not icp.target_markets:
        return {
            "factor": "market_match", "weight": WEIGHT_MARKET, "matched": None, "points": WEIGHT_MARKET,
            "explanation": "ICP specifies no target markets - treated as no preference.",
        }, False

    matched = _country_matches(prospect.country, icp.target_markets)
    return {
        "factor": "market_match", "weight": WEIGHT_MARKET, "matched": matched,
        "points": WEIGHT_MARKET if matched else 0,
        "explanation": "Prospect's country is one of this ICP's target markets." if matched
        else f"'{prospect.country}' is not in this ICP's target markets.",
    }, False


def _score_company_size(prospect: Prospect, icp: ICPCriteria) -> dict[str, Any]:
    preferred = icp.preferred_company_size or []
    if not preferred:
        return {
            "factor": "company_size_match", "weight": WEIGHT_COMPANY_SIZE, "matched": None,
            "points": WEIGHT_COMPANY_SIZE, "explanation": "ICP specifies no preferred company size - treated as no preference.",
        }
    matched = bool(prospect.company_size_range) and prospect.company_size_range.strip().lower() in [
        p.strip().lower() for p in preferred
    ]
    return {
        "factor": "company_size_match", "weight": WEIGHT_COMPANY_SIZE, "matched": matched,
        "points": WEIGHT_COMPANY_SIZE if matched else 0,
        "explanation": "Prospect's company size is in this ICP's preferred range(s)." if matched
        else "Prospect's company size is outside this ICP's preferred range(s) (or unset).",
    }


def _score_product_relevance(prospect: Prospect, products: list[Product]) -> dict[str, Any]:
    keywords: set[str] = set()
    for product in products:
        keywords.update(k.strip().lower() for k in (product.keywords or []) if k and k.strip())
        keywords.update(a.strip().lower() for a in (product.applications or []) if a and a.strip())

    text = (prospect.description or "").lower()
    if not keywords or not text:
        return {
            "factor": "product_keyword_relevance", "weight": WEIGHT_PRODUCT_RELEVANCE, "matched": None,
            "points": 0, "explanation": "No product keywords/applications or no prospect description to compare against.",
        }

    matched_keywords = sorted(k for k in keywords if k in text)
    # 3+ distinct keyword hits earns full credit; fewer hits scale linearly.
    ratio = min(1.0, len(matched_keywords) / 3)
    points = round(WEIGHT_PRODUCT_RELEVANCE * ratio, 1)
    return {
        "factor": "product_keyword_relevance", "weight": WEIGHT_PRODUCT_RELEVANCE, "matched": bool(matched_keywords),
        "points": points,
        "explanation": (
            f"Matched keywords/applications: {', '.join(matched_keywords)}." if matched_keywords
            else "None of this business's product keywords/applications appear in the prospect's description."
        ),
    }


def score_prospect(prospect: Prospect, icp: ICPCriteria, products: list[Product]) -> ScoringResult:
    market_entry, excluded = _score_market(prospect, icp)

    if excluded:
        breakdown = [market_entry]
        return ScoringResult(total_score=0.0, breakdown=breakdown, excluded=True)

    breakdown = [
        _score_buyer_type(prospect, icp),
        market_entry,
        _score_company_size(prospect, icp),
        _score_product_relevance(prospect, products),
    ]
    total = round(sum(entry["points"] for entry in breakdown), 1)
    return ScoringResult(total_score=total, breakdown=breakdown, excluded=False)
