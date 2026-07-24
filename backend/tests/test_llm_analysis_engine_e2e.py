"""
Tests for LLMAnalysisEngine (app/research/analysis/llm_engine.py) -
M2 Phase 3. Disclosed as NOT executed in the authoring sandbox: this
module imports ResearchContext/RawDocument/Prospect/CompanyProfile/
Product (real SQLAlchemy ORM models) and, transitively via
app.ai_agents.runtime, app.core.config (pydantic_settings) - both
confirmed absent here, with no PyPI/network access to install them (same
standing sandbox disclosure as every DB-touching test in this project,
e.g. test_discovery_providers_route.py). py_compile-checked clean here;
run for real in Docker.

Uses unittest.mock to patch AgentRuntime.run_with_metadata rather than
exercising a real Gateway/provider call - this file's job is proving
LLMAnalysisEngine's own mapping/degradation logic (ORM -> primitives ->
AnalysisOutcome), not re-proving AgentRuntime itself (already covered by
test_research_analysis_agent_full_chain_e2e.py).

Imports app.db.base before any app.models.* import, same as every other
DB-backed test in this project (test_research_workflow_e2e.py,
test_discovery_search_service_e2e.py, ...): app.db.base is the one
module that imports every mapped model class, so every string-based
relationship target (e.g. CompanyProfile.industries -> "Industry") is
registered in SQLAlchemy's mapper registry BEFORE the first mapped class
is ever instantiated in this process. SQLAlchemy configures every
as-yet-unconfigured mapper the moment any one mapped class is first
used - skipping this import (as this file originally did) means
whichever model this file instantiates first becomes, by accident, the
trigger for a project-wide mapper configuration pass that only "sees"
the handful of model modules this file itself happened to import
directly (CompanyProfile/Product/Prospect/RawDocument), not the full
set - so a relationship target like "Industry" that no import in this
file ever touches directly fails to resolve. This is a test-file-only
fix (one import, correctly ordered) - no production code changes, no
weakened assertions, no bypassing of mapper configuration.

Run standalone (Docker/full environment only) with:
    python -m unittest tests.test_llm_analysis_engine_e2e
"""
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from app.db import base as _base  # noqa: F401  (registers every model - see module docstring)
from app.ai_agents.base import AgentExecutionResult, AgentOutcome, AgentOutput
from app.models.company_profile import CompanyProfile
from app.models.enums import AIAnalysisType
from app.models.product import Product
from app.models.prospect import Prospect
from app.models.raw_document import RawDocument
from app.research.analysis.llm_engine import LLMAnalysisEngine, _build_agent_context
from app.research.context import ResearchContext

VALID_RESPONSE = {
    "company_profile": {
        "structured_output": {
            "business_model": "manufacturer",
            "products_offered": ["yarn"],
            "markets_served": ["EU"],
            "certifications": [],
            "manufacturing_or_trading": "manufacturer",
            "sustainability_notes": None,
            "import_export_activity": [],
        },
        "confidence": 0.8,
        "reasoning": "Company page describes manufacturing.",
    },
    "buyer_profile": {
        "structured_output": {"buyer_notes": "Central buying office.", "procurement_structure": None, "purchasing_process": None},
        "confidence": 0.4,
        "reasoning": "Mentions a buying office.",
    },
    "business_signals": {
        "structured_output": {"signals": [], "signals_summary": "No signals detected."},
        "confidence": 0.0,
        "reasoning": "No signal keywords matched.",
    },
    "sales_intelligence": {
        "structured_output": {"recommendations": []},
        "confidence": 0.0,
        "reasoning": "No product overlap found.",
    },
}


def _make_context() -> tuple[ResearchContext, list[RawDocument]]:
    prospect = Prospect(
        id=uuid.uuid4(),
        company_profile_id=uuid.uuid4(),
        name="Acme Textiles",
        website="https://acme-textiles.example",
        country="Vietnam",
        industry_raw="Textiles",
        first_discovered_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
    )
    company_profile = CompanyProfile(
        id=uuid.uuid4(), owner_user_id=uuid.uuid4(), name="My Trading Co", about="We sell yarn."
    )
    product = Product(
        id=uuid.uuid4(), company_profile_id=company_profile.id, name="Organic Cotton Yarn",
        keywords=["organic cotton"], applications=["knitwear"],
    )
    raw_document = RawDocument(
        id=uuid.uuid4(), research_source_id=uuid.uuid4(), prospect_id=prospect.id,
        document_type="html_page", extracted_text="Acme Textiles is a manufacturer of organic cotton yarn.",
    )
    context = ResearchContext(prospect=prospect, company_profile=company_profile, products=[product])
    return context, [raw_document]


class TestBuildAgentContext(unittest.TestCase):
    def test_extracts_plain_primitives_from_orm_objects(self):
        context, raw_documents = _make_context()
        agent_context = _build_agent_context(context, raw_documents)

        self.assertEqual(agent_context["prospect"]["name"], "Acme Textiles")
        self.assertEqual(agent_context["prospect"]["country"], "Vietnam")
        self.assertEqual(agent_context["company_profile"]["name"], "My Trading Co")
        self.assertEqual(agent_context["products"][0]["name"], "Organic Cotton Yarn")
        self.assertEqual(agent_context["documents"][0]["index"], 0)
        self.assertIn("organic cotton yarn", agent_context["documents"][0]["extracted_text"])
        # every value must be a plain primitive - no ORM object leaks through
        self.assertIsInstance(agent_context["products"][0]["id"], str)


class TestLLMAnalysisEngineAnalyze(unittest.TestCase):
    def test_maps_successful_agent_output_into_four_analysis_outcomes(self):
        context, raw_documents = _make_context()
        engine = LLMAnalysisEngine()
        fake_result = AgentExecutionResult(
            output=AgentOutput(status=AgentOutcome.SUCCESS, result=VALID_RESPONSE),
            provider_key="claude",
            model="claude-real-model",
        )

        with patch("app.research.analysis.llm_engine.AgentRuntime.run_with_metadata", return_value=fake_result):
            outcomes = engine.analyze(context, raw_documents)

        self.assertEqual(len(outcomes), 4)
        by_type = {o.analysis_type: o for o in outcomes}
        self.assertIn(AIAnalysisType.COMPANY_PROFILE, by_type)
        self.assertEqual(by_type[AIAnalysisType.COMPANY_PROFILE].model_used, "claude-real-model")
        self.assertEqual(by_type[AIAnalysisType.COMPANY_PROFILE].confidence, 0.8)
        self.assertEqual(by_type[AIAnalysisType.COMPANY_PROFILE].structured_output["business_model"], "manufacturer")
        self.assertEqual(by_type[AIAnalysisType.BUYER_PROFILE].structured_output["buyer_notes"], "Central buying office.")

    def test_degrades_gracefully_never_raises_on_agent_failure(self):
        context, raw_documents = _make_context()
        engine = LLMAnalysisEngine()
        fake_result = AgentExecutionResult(
            output=AgentOutput(status=AgentOutcome.FAILURE, error="all providers exhausted"),
            provider_key=None,
            model=None,
        )

        with patch("app.research.analysis.llm_engine.AgentRuntime.run_with_metadata", return_value=fake_result):
            outcomes = engine.analyze(context, raw_documents)  # must not raise

        self.assertEqual(len(outcomes), 4)
        for outcome in outcomes:
            self.assertIsNone(outcome.confidence)
            self.assertIn("all providers exhausted", outcome.reasoning)
            self.assertEqual(outcome.source_document_indices, [])


if __name__ == "__main__":
    unittest.main()
