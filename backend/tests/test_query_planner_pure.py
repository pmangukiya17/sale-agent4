"""
tests.test_query_planner_pure - M2 Phase 2.

Genuinely executed in this sandbox: app.discovery.query_planner has zero
ORM/third-party dependency (see that module's own docstring), so unlike
most of this phase's other new code, these tests run for real here, not
just via py_compile.

Run standalone with:
    python -m unittest tests.test_query_planner_pure
"""
import unittest

from app.discovery.query_planner import (
    MAX_VARIATIONS_PER_PLAN,
    QueryPlanInput,
    build_query_plan,
)


class TestBuildQueryPlan(unittest.TestCase):
    def test_no_products_yields_empty_plan(self):
        plan = build_query_plan(QueryPlanInput(buyer_types=["Importer"], countries=["Germany"]))
        self.assertEqual(plan.variations, [])

    def test_single_product_no_other_dimensions(self):
        plan = build_query_plan(QueryPlanInput(product_names=["Cotton Yarn"]))
        self.assertEqual(len(plan.variations), 1)
        variation = plan.variations[0]
        self.assertEqual(variation.query, "Cotton Yarn")
        self.assertIsNone(variation.country)
        self.assertEqual(variation.product_name, "Cotton Yarn")

    def test_countries_produce_one_variation_each(self):
        plan = build_query_plan(QueryPlanInput(product_names=["Cotton Yarn"], countries=["Germany", "France"]))
        self.assertEqual(len(plan.variations), 2)
        countries_seen = {v.country for v in plan.variations}
        self.assertEqual(countries_seen, {"Germany", "France"})
        for v in plan.variations:
            self.assertIn("Cotton Yarn", v.query)
            self.assertIn(v.country, v.query)

    def test_buyer_type_and_industry_enrich_query_without_cross_multiplying(self):
        plan = build_query_plan(
            QueryPlanInput(
                product_names=["Cotton Yarn"],
                buyer_types=["Importer", "Distributor"],  # only the FIRST is used
                industries=["Textiles", "Apparel"],  # only the FIRST is used
                countries=["Germany"],
            )
        )
        # One product x one country = one variation, NOT product x buyer_type x industry x country.
        self.assertEqual(len(plan.variations), 1)
        variation = plan.variations[0]
        self.assertEqual(variation.buyer_type, "Importer")
        self.assertEqual(variation.industry_name, "Textiles")
        self.assertIn("Importer", variation.query)
        self.assertIn("Textiles", variation.query)

    def test_synonyms_add_extra_variations_for_the_same_product(self):
        plan = build_query_plan(
            QueryPlanInput(
                product_names=["Cotton Yarn"],
                synonyms={"Cotton Yarn": ["Cotton Thread", "Spun Cotton Yarn"]},
            )
        )
        self.assertEqual(len(plan.variations), 3)  # base + 2 synonyms
        queries = {v.query for v in plan.variations}
        self.assertIn("Cotton Yarn", queries)
        self.assertIn("Cotton Thread", queries)
        self.assertIn("Spun Cotton Yarn", queries)
        synonym_variations = [v for v in plan.variations if v.synonym is not None]
        self.assertEqual(len(synonym_variations), 2)

    def test_product_keywords_are_included_alongside_product_names(self):
        plan = build_query_plan(QueryPlanInput(product_names=["Cotton Yarn"], product_keywords=["GSM 200 fabric"]))
        queries = {v.query for v in plan.variations}
        self.assertIn("Cotton Yarn", queries)
        self.assertIn("GSM 200 fabric", queries)

    def test_duplicate_query_strings_are_deduplicated(self):
        plan = build_query_plan(QueryPlanInput(product_names=["Cotton Yarn", "Cotton Yarn"]))
        self.assertEqual(len(plan.variations), 1)

    def test_hard_ceiling_is_never_exceeded(self):
        many_products = [f"Product {i}" for i in range(20)]
        many_countries = [f"Country {i}" for i in range(20)]
        plan = build_query_plan(QueryPlanInput(product_names=many_products, countries=many_countries))
        self.assertLessEqual(len(plan.variations), MAX_VARIATIONS_PER_PLAN)
        self.assertEqual(len(plan.variations), MAX_VARIATIONS_PER_PLAN)  # 20*20=400 possible, capped

    def test_every_variation_produces_a_valid_query_spec(self):
        plan = build_query_plan(
            QueryPlanInput(product_names=["Cotton Yarn"], countries=["Germany"], languages=["de"])
        )
        spec = plan.variations[0].as_query_spec()
        self.assertEqual(spec["query"], "Cotton Yarn Germany")
        self.assertEqual(spec["country"], "Germany")
        self.assertEqual(spec["language"], "de")

    def test_whitespace_in_inputs_is_collapsed(self):
        plan = build_query_plan(QueryPlanInput(product_names=["  Cotton   Yarn  "]))
        self.assertEqual(plan.variations[0].query, "Cotton Yarn")

    def test_never_raises_on_empty_input(self):
        plan = build_query_plan(QueryPlanInput())
        self.assertEqual(plan.variations, [])


if __name__ == "__main__":
    unittest.main()
