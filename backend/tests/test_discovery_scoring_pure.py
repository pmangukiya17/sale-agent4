"""
tests.test_discovery_scoring_pure - M2 Phase 1b.

Pure logic, zero fixtures, zero database. app/discovery/scoring.py's
ICPCriteria/Product/Prospect imports were moved behind `TYPE_CHECKING`
as part of Phase 1b (mirroring dedup.py's Phase 1a change - see that
module's own docstring and scoring.py's own "purity note"), specifically
so this suite can exercise resolve_weights()/_score_industry()/etc.
against lightweight stand-in objects, with no working sqlalchemy install
- the same "pure logic, actually executed in the authoring sandbox"
precedent tests/test_discovery_dedup_pure.py and
tests/test_discovery_normalization.py already set.

score_prospect() end-to-end against real ORM rows (real ICPCriteria with
real relationships, real Prospect) stays covered only by the existing
DB-backed e2e suite (tests/test_discovery_workflow_e2e.py) - this file
only covers the parts of scoring.py's logic that don't require a real
relationship collection to be meaningful, using simple stand-ins that
duck-type the handful of attributes each function actually reads.
"""
import unittest
from types import SimpleNamespace

from app.discovery.scoring import (
    DEFAULT_WEIGHTS,
    SCORING_FACTOR_NAMES,
    _score_industry,
    resolve_weights,
)


def _make_icp(**overrides):
    """A plain stand-in for ICPCriteria - only the attributes
    resolve_weights()/_score_industry() actually read via attribute
    access (never isinstance-checked, never instantiated as the real
    class - see scoring.py's own "purity note")."""
    defaults = {
        "rules": {},
        "target_industries": [],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_prospect(**overrides):
    defaults = {"industry_id": None}
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_industry(id_):
    return SimpleNamespace(id=id_)


class TestDefaultWeights(unittest.TestCase):
    def test_sums_to_100(self):
        self.assertEqual(sum(DEFAULT_WEIGHTS.values()), 100)

    def test_matches_ceo_approved_split(self):
        # CEO-directed exact defaults (Phase 1b architecture-review
        # approval message) - a regression guard against silent drift.
        self.assertEqual(DEFAULT_WEIGHTS["product_keyword_relevance"], 25)
        self.assertEqual(DEFAULT_WEIGHTS["buyer_type_match"], 20)
        self.assertEqual(DEFAULT_WEIGHTS["industry_match"], 20)
        self.assertEqual(DEFAULT_WEIGHTS["market_match"], 20)
        self.assertEqual(DEFAULT_WEIGHTS["company_size_match"], 15)

    def test_scoring_factor_names_matches_default_weights_keys(self):
        self.assertEqual(SCORING_FACTOR_NAMES, frozenset(DEFAULT_WEIGHTS))


class TestResolveWeights(unittest.TestCase):
    def test_no_override_returns_platform_defaults(self):
        icp = _make_icp(rules={})
        self.assertEqual(resolve_weights(icp), dict(DEFAULT_WEIGHTS))

    def test_none_rules_returns_platform_defaults(self):
        # rules is NOT NULL/default=dict on the real model, but
        # resolve_weights should never crash even if a row somehow has
        # rules=None.
        icp = _make_icp(rules=None)
        self.assertEqual(resolve_weights(icp), dict(DEFAULT_WEIGHTS))

    def test_partial_override_only_changes_named_factors(self):
        icp = _make_icp(rules={"scoring_weights": {"industry_match": 40}})
        result = resolve_weights(icp)
        self.assertEqual(result["industry_match"], 40)
        # every other factor keeps its platform default - never partial.
        for factor, default in DEFAULT_WEIGHTS.items():
            if factor != "industry_match":
                self.assertEqual(result[factor], default)
        self.assertEqual(set(result), set(DEFAULT_WEIGHTS))

    def test_full_custom_override(self):
        custom = {
            "buyer_type_match": 10, "market_match": 10, "company_size_match": 10,
            "product_keyword_relevance": 50, "industry_match": 20,
        }
        icp = _make_icp(rules={"scoring_weights": custom})
        self.assertEqual(resolve_weights(icp), custom)

    def test_malformed_override_falls_back_to_defaults(self):
        # scoring_weights present but not a dict - never crash, treat as
        # no override at all.
        icp = _make_icp(rules={"scoring_weights": "not-a-dict"})
        self.assertEqual(resolve_weights(icp), dict(DEFAULT_WEIGHTS))

    def test_never_mutates_icp_rules(self):
        original_rules = {"scoring_weights": {"industry_match": 40}}
        icp = _make_icp(rules=original_rules)
        resolve_weights(icp)
        self.assertEqual(icp.rules, original_rules)


class TestScoreIndustry(unittest.TestCase):
    def test_no_target_industries_is_no_preference(self):
        icp = _make_icp(target_industries=[])
        prospect = _make_prospect(industry_id="ind-1")
        entry = _score_industry(prospect, icp, weight=20)
        self.assertIsNone(entry["matched"])
        self.assertEqual(entry["points"], 20)

    def test_matching_industry_scores_full_weight(self):
        icp = _make_icp(target_industries=[_make_industry("ind-1"), _make_industry("ind-2")])
        prospect = _make_prospect(industry_id="ind-1")
        entry = _score_industry(prospect, icp, weight=20)
        self.assertTrue(entry["matched"])
        self.assertEqual(entry["points"], 20)

    def test_non_matching_industry_scores_zero(self):
        icp = _make_icp(target_industries=[_make_industry("ind-2")])
        prospect = _make_prospect(industry_id="ind-1")
        entry = _score_industry(prospect, icp, weight=20)
        self.assertFalse(entry["matched"])
        self.assertEqual(entry["points"], 0)

    def test_unresolved_prospect_industry_scores_zero_not_none(self):
        # A target list IS configured, so an unresolved (None)
        # prospect.industry_id is a genuine non-match, not "no preference".
        icp = _make_icp(target_industries=[_make_industry("ind-1")])
        prospect = _make_prospect(industry_id=None)
        entry = _score_industry(prospect, icp, weight=20)
        self.assertFalse(entry["matched"])
        self.assertEqual(entry["points"], 0)

    def test_factor_name_and_weight_recorded(self):
        icp = _make_icp(target_industries=[])
        prospect = _make_prospect()
        entry = _score_industry(prospect, icp, weight=20)
        self.assertEqual(entry["factor"], "industry_match")
        self.assertEqual(entry["weight"], 20)
        self.assertIsNotNone(entry["explanation"])


if __name__ == "__main__":
    unittest.main()
