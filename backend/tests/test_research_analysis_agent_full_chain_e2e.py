"""
Full-chain test for ResearchAnalysisAgent - M2 Phase 3. Runs the REAL
registered agent through the REAL AgentRuntime -> PromptBuilder ->
AIGateway chain, with only the bottom-most ProviderClient faked (mirrors
test_ai_execution_platform_e2e.py's own TestAgentRuntimeFullChain
pattern exactly) - proving the first concrete Agent this codebase ships
actually works end-to-end, without a database or a real model API key.

Disclosed as NOT executed in the authoring sandbox: app.ai_agents.runtime
imports app.ai_gateway.client, which imports app.core.config, which
requires pydantic_settings - confirmed absent here, with no PyPI access
to install it (`pip install pydantic-settings` fails: no route to
pypi.org in this sandbox). This is a genuine environment gap, not a
design flaw - test_ai_execution_platform_e2e.py's own reference suite
has always required the same dependency and has never been run in this
sandbox either. py_compile-checked clean here; run for real in Docker
alongside every other environment-gated test in this project.

Run standalone (Docker/full environment only) with:
    python -m unittest tests.test_research_analysis_agent_full_chain_e2e
"""
import json
import unittest

from app.ai_agents.base import AgentInput, AgentOutcome
from app.ai_agents.runtime import AgentRuntime
from app.ai_gateway.client import AIGateway
from app.ai_gateway.providers.base import ProviderClient
from app.ai_gateway.request import GatewayRequest, GatewayResponse, ResponseFormatType, TokenUsage
from app.ai_gateway.router import ROUTING_POLICY, RoutingDecision
from app.research.analysis.llm_agent import RESEARCH_ANALYSIS_AGENT_KEY

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


class _JsonProviderClient(ProviderClient):
    key = "fake_llm"

    def __init__(self, content, model: str = "fake-model-v1"):
        self._content = content
        self._model = model
        self.requests_seen: list[GatewayRequest] = []

    def is_configured(self) -> bool:
        return True

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        self.requests_seen.append(request)
        return _response(self._content, model=self._model)


def _make_gateway(provider: ProviderClient) -> AIGateway:
    def provider_lookup(key: str) -> ProviderClient:
        if key != provider.key:
            raise KeyError(key)
        return provider

    return AIGateway(provider_lookup=provider_lookup)


class TestResearchAnalysisAgentFullChain(unittest.TestCase):
    def setUp(self):
        self._original_routing = ROUTING_POLICY.get(RESEARCH_ANALYSIS_AGENT_KEY)
        ROUTING_POLICY[RESEARCH_ANALYSIS_AGENT_KEY] = RoutingDecision(primary="fake_llm")

    def tearDown(self):
        if self._original_routing is not None:
            ROUTING_POLICY[RESEARCH_ANALYSIS_AGENT_KEY] = self._original_routing
        else:
            ROUTING_POLICY.pop(RESEARCH_ANALYSIS_AGENT_KEY, None)

    def test_full_chain_success(self):
        provider = _JsonProviderClient(json.dumps(VALID_RESPONSE))
        gateway = _make_gateway(provider)

        result = AgentRuntime.run_with_metadata(
            RESEARCH_ANALYSIS_AGENT_KEY,
            AgentInput(context={"prospect": {"name": "Acme Textiles"}, "documents": []}),
            gateway=gateway,
        )

        self.assertEqual(result.output.status, AgentOutcome.SUCCESS)
        self.assertEqual(result.output.result, VALID_RESPONSE)
        self.assertEqual(result.provider_key, "fake_llm")
        self.assertEqual(result.model, "fake-model-v1")
        sent_request = provider.requests_seen[0]
        self.assertTrue(any("Acme Textiles" in m["content"] for m in sent_request.messages))
        self.assertEqual(sent_request.response_format.type, ResponseFormatType.JSON)

    def test_full_chain_retries_then_succeeds_after_malformed_first_response(self):
        class _FlakyProviderClient(ProviderClient):
            key = "fake_llm"

            def __init__(self):
                self.attempts = 0

            def is_configured(self):
                return True

            def complete(self, request):
                self.attempts += 1
                if self.attempts == 1:
                    return _response("not valid json")
                return _response(json.dumps(VALID_RESPONSE))

        provider = _FlakyProviderClient()
        gateway = _make_gateway(provider)

        output = AgentRuntime.run(RESEARCH_ANALYSIS_AGENT_KEY, AgentInput(context={}), gateway=gateway)

        self.assertEqual(output.status, AgentOutcome.SUCCESS)
        self.assertEqual(provider.attempts, 2)

    def test_full_chain_reports_failure_when_every_attempt_is_malformed(self):
        provider = _JsonProviderClient("still not json")
        gateway = _make_gateway(provider)

        output = AgentRuntime.run(RESEARCH_ANALYSIS_AGENT_KEY, AgentInput(context={}), gateway=gateway)

        self.assertEqual(output.status, AgentOutcome.FAILURE)
        self.assertIsNotNone(output.error)


if __name__ == "__main__":
    unittest.main()
