"""
Pure unit tests for app/research/analysis/llm_mapping.py - M2 Phase 3.
Zero third-party dependencies (stdlib json only) - genuinely executable
with plain `python -m unittest` in any environment, sandbox included,
same disclosure convention as every other *_pure.py test in this project
(test_query_planner_pure.py, test_brave_search_mapping_pure.py, ...).

Run standalone with:
    python -m unittest tests.test_llm_mapping_pure
"""
import unittest

from app.research.analysis.llm_mapping import (
    REQUIRED_SECTIONS,
    degraded_structured_output,
    extract_section,
    parse_agent_response_content,
    validate_sections,
)


def _valid_response() -> dict:
    return {
        "company_profile": {
            "structured_output": {
                "business_model": "manufacturer",
                "products_offered": ["cotton yarn"],
                "markets_served": ["EU"],
                "certifications": ["ISO 9001"],
                "manufacturing_or_trading": "manufacturer",
                "sustainability_notes": None,
                "import_export_activity": ["exporter"],
            },
            "confidence": 0.8,
            "reasoning": "Company page mentions ISO 9001 and export activity.",
        },
        "buyer_profile": {
            "structured_output": {
                "buyer_notes": "Central buying office.",
                "procurement_structure": "central buying office",
                "purchasing_process": None,
            },
            "confidence": 0.5,
            "reasoning": "Mentions a central buying office.",
        },
        "business_signals": {
            "structured_output": {
                "signals": [
                    {
                        "signal_type": "expansion",
                        "title": "New facility",
                        "description": "Opening a new factory in Vietnam.",
                        "importance": "high",
                        "urgency": "medium",
                        "confidence": 0.7,
                        "reasoning": "Document explicitly states a new factory is opening.",
                        "evidence_document_indices": [0, 99],
                    }
                ],
                "signals_summary": "1 expansion signal detected.",
            },
            "confidence": 0.7,
            "reasoning": "One strong signal found.",
        },
        "sales_intelligence": {
            "structured_output": {
                "recommendations": [
                    {
                        "recommendation_type": "product_fit",
                        "title": "Pitch organic cotton yarn",
                        "rationale": "Prospect already sources organic cotton.",
                        "product_id": "abc-123",
                        "confidence": 0.6,
                        "reasoning": "Keyword overlap with product catalog.",
                        "evidence_document_indices": [1],
                    }
                ]
            },
            "confidence": 0.6,
            "reasoning": "One product-fit recommendation found.",
        },
    }


class TestParseAgentResponseContent(unittest.TestCase):
    def test_accepts_dict_directly(self):
        parsed = parse_agent_response_content({"a": 1})
        self.assertEqual(parsed, {"a": 1})

    def test_parses_valid_json_string(self):
        parsed = parse_agent_response_content('{"a": 1}')
        self.assertEqual(parsed, {"a": 1})

    def test_raises_valueerror_on_invalid_json(self):
        with self.assertRaises(ValueError):
            parse_agent_response_content("not json at all {")

    def test_raises_valueerror_on_json_array(self):
        with self.assertRaises(ValueError):
            parse_agent_response_content("[1, 2, 3]")

    def test_raises_valueerror_on_unexpected_type(self):
        with self.assertRaises(ValueError):
            parse_agent_response_content(12345)


class TestValidateSections(unittest.TestCase):
    def test_accepts_a_fully_valid_response(self):
        validate_sections(_valid_response())  # must not raise

    def test_rejects_missing_section(self):
        response = _valid_response()
        del response["sales_intelligence"]
        with self.assertRaises(ValueError) as ctx:
            validate_sections(response)
        self.assertIn("sales_intelligence", str(ctx.exception))

    def test_rejects_section_missing_structured_output(self):
        response = _valid_response()
        del response["business_signals"]["structured_output"]
        with self.assertRaises(ValueError):
            validate_sections(response)

    def test_rejects_non_dict_structured_output(self):
        response = _valid_response()
        response["buyer_profile"]["structured_output"] = "not a dict"
        with self.assertRaises(ValueError):
            validate_sections(response)

    def test_every_required_section_checked(self):
        # sanity: REQUIRED_SECTIONS itself matches what the test fixture covers
        self.assertEqual(set(REQUIRED_SECTIONS), set(_valid_response().keys()))


class TestExtractSection(unittest.TestCase):
    def test_extracts_structured_output_confidence_reasoning(self):
        response = _valid_response()
        structured_output, confidence, reasoning = extract_section(
            response, "buyer_profile", raw_document_count=5
        )
        self.assertEqual(structured_output["procurement_structure"], "central buying office")
        self.assertEqual(confidence, 0.5)
        self.assertIn("central buying office", reasoning)

    def test_bounds_evidence_document_indices_for_signals(self):
        response = _valid_response()
        structured_output, _, _ = extract_section(response, "business_signals", raw_document_count=3)
        # index 99 is out of range for a 3-document set and must be dropped;
        # index 0 is in range and must survive.
        self.assertEqual(structured_output["signals"][0]["evidence_document_indices"], [0])

    def test_bounds_evidence_document_indices_for_recommendations(self):
        response = _valid_response()
        structured_output, _, _ = extract_section(response, "sales_intelligence", raw_document_count=1)
        # index 1 is out of range for a 1-document set (valid indices: [0]).
        self.assertEqual(structured_output["recommendations"][0]["evidence_document_indices"], [])

    def test_missing_section_falls_back_to_empty_shape(self):
        structured_output, confidence, reasoning = extract_section({}, "company_profile", raw_document_count=0)
        self.assertEqual(structured_output, degraded_structured_output("company_profile"))
        self.assertIsNone(confidence)
        self.assertIsNone(reasoning)

    def test_non_int_or_negative_indices_are_dropped(self):
        response = _valid_response()
        response["business_signals"]["structured_output"]["signals"][0]["evidence_document_indices"] = [
            0, -1, "not an int", 2.5, None,
        ]
        structured_output, _, _ = extract_section(response, "business_signals", raw_document_count=5)
        self.assertEqual(structured_output["signals"][0]["evidence_document_indices"], [0])


class TestDegradedStructuredOutput(unittest.TestCase):
    def test_returns_contract_shaped_empty_dict_for_every_section(self):
        for section_key in REQUIRED_SECTIONS:
            shape = degraded_structured_output(section_key)
            self.assertIsInstance(shape, dict)

    def test_business_signals_degraded_shape_has_empty_signals_list(self):
        shape = degraded_structured_output("business_signals")
        self.assertEqual(shape["signals"], [])
        self.assertIsInstance(shape["signals_summary"], str)

    def test_returned_dict_is_a_copy_not_a_shared_reference(self):
        first = degraded_structured_output("sales_intelligence")
        first["recommendations"].append({"fake": True})
        second = degraded_structured_output("sales_intelligence")
        self.assertEqual(second["recommendations"], [])


if __name__ == "__main__":
    unittest.main()
