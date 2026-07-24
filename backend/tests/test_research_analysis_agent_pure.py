"""
Pure unit tests for ResearchAnalysisAgent's own build_context()/
interpret() (app/research/analysis/llm_agent.py) - M2 Phase 3, the first
concrete Agent this codebase has shipped.

Deliberately imports ONLY app.research.analysis.llm_agent and
app.ai_gateway.request's plain dataclasses - NOT app.ai_agents.runtime or
app.ai_gateway.client, both of which import app.core.config, which
requires pydantic_settings (confirmed NOT installed in this sandbox, and
no PyPI access to install it - see this project's standing sandbox
disclosure). ResearchAnalysisAgent itself has no such dependency (see
llm_agent.py's own docstring: "fully sqlalchemy-free... only
app.ai_agents.base/app.ai_gateway.request/app.prompt_builder.base/
app.prompt_builder.policy/app.research.analysis.llm_mapping"), so this
file's own tests ARE genuinely executed here. The full AgentRuntime ->
PromptBuilder -> AIGateway chain test (proving this exact registered
Agent end-to-end with a fake ProviderClient) lives in
tests/test_research_analysis_agent_full_chain_e2e.py instead, disclosed
there as requiring a real Python environment with pydantic_settings
installed (Docker), since AgentRuntime/AIGateway.client both need it.

Run standalone with:
    python -m unittest tests.test_research_analysis_agent_pure
"""
import json
import unittest

from app.ai_agents.base import AgentInput, AgentOutcome
from app.ai_gateway.request import GatewayResponse, ResponseFormatType, TokenUsage
from app.research.analysis.llm_agent import RESPONSE_FORMAT, ResearchAnalysisAgent

VALID_RESPONSE = {
    "company_profile": {
        "structured_output": {
            "business_model": "manufacturer",
            "products_offered": [],
            "markets_served": [],
            "certifications": [],
            "manufacturing_or_trading": "manufacturer",
            "sustainability_notes": None,
            "import_export_activity": [],
        },
        "confidence": 0.6,
        "reasoning": "Company page describes a manufacturing operation.",
    },
    "buyer_profile": {
        "structured_output": {"buyer_notes": None, "procurement_structure": None, "purchasing_process": None},
        "confidence": 0.0,
        "reasoning": "No procurement information found.",
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


def _response(content, *, provider_key: str = "fake_llm", model: str = "fake-model-v1") -> GatewayResponse:
    return GatewayResponse(
        content=content,
        tool_calls=None,
        usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20, cost_usd=0.001),
        provider_key=provider_key,
        model=model,
        finish_reason="stop",
    )


class TestResearchAnalysisAgentBuildContext(unittest.TestCase):
    def test_build_context_carries_business_context_through_unread(self):
        agent = ResearchAnalysisAgent()
        business_context = {"prospect": {"name": "Acme Textiles"}, "documents": []}
        context = agent.build_context(AgentInput(context=business_context))

        self.assertEqual(context.business_context, business_context)
        self.assertIsNotNone(context.system_instructions)
        self.assertIsNotNone(context.user_instructions)

    def test_build_context_reads_registered_prompt_template(self):
        # The system instructions come from app.ai_agents.prompts.registry,
        # not a hardcoded literal inside build_context() itself - confirm
        # the registered template is actually what's returned.
        from app.ai_agents.prompts.registry import get_prompt_template
        from app.research.analysis.llm_agent import PROMPT_VERSION, RESEARCH_ANALYSIS_AGENT_KEY

        template = get_prompt_template(RESEARCH_ANALYSIS_AGENT_KEY, PROMPT_VERSION)
        agent = ResearchAnalysisAgent()
        context = agent.build_context(AgentInput(context={}))
        self.assertEqual(context.system_instructions, template.system_instructions)


class TestResearchAnalysisAgentInterpret(unittest.TestCase):
    def test_interpret_succeeds_on_valid_json_string_content(self):
        agent = ResearchAnalysisAgent()
        response = _response(json.dumps(VALID_RESPONSE))

        output = agent.interpret(response, AgentInput(context={}))

        self.assertEqual(output.status, AgentOutcome.SUCCESS)
        self.assertEqual(output.result, VALID_RESPONSE)

    def test_interpret_succeeds_on_dict_content(self):
        agent = ResearchAnalysisAgent()
        response = _response(VALID_RESPONSE)

        output = agent.interpret(response, AgentInput(context={}))

        self.assertEqual(output.status, AgentOutcome.SUCCESS)

    def test_interpret_retries_on_malformed_json(self):
        agent = ResearchAnalysisAgent()
        response = _response("this is not json")

        output = agent.interpret(response, AgentInput(context={}))

        self.assertEqual(output.status, AgentOutcome.RETRY)
        self.assertIsNotNone(output.error)

    def test_interpret_retries_on_missing_required_section(self):
        agent = ResearchAnalysisAgent()
        incomplete = {k: v for k, v in VALID_RESPONSE.items() if k != "sales_intelligence"}
        response = _response(incomplete)

        output = agent.interpret(response, AgentInput(context={}))

        self.assertEqual(output.status, AgentOutcome.RETRY)
        self.assertIn("sales_intelligence", output.error)

    def test_response_format_requests_json(self):
        self.assertEqual(RESPONSE_FORMAT.type, ResponseFormatType.JSON)
        self.assertIsNotNone(RESPONSE_FORMAT.json_schema)


if __name__ == "__main__":
    unittest.main()
