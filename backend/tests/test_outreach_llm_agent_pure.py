"""
Pure unit tests for OutreachEmailAgent's own build_context()/interpret()
(app/outreach/channels/llm_agent.py) - M-AIGW-5, the SECOND concrete
Agent this codebase has shipped (see
docs/architecture/provider-neutral-ai-gateway-plan.md Section 12).

Deliberately imports ONLY app.outreach.channels.llm_agent/llm_mapping and
app.ai_gateway.request's plain dataclasses - NOT app.ai_agents.runtime or
app.ai_gateway.client, both of which import app.core.config, which
requires pydantic_settings (confirmed NOT installed in this sandbox - see
this project's standing sandbox disclosure, and
tests/test_research_analysis_agent_pure.py's identical precedent).
OutreachEmailAgent itself has no such dependency (see llm_agent.py's own
docstring), so this file's own tests ARE genuinely executed here. A full
AgentRuntime -> PromptBuilder -> AIGateway chain test (proving this exact
registered Agent end-to-end with a fake ProviderClient), mirroring
tests/test_research_analysis_agent_full_chain_e2e.py, is Docker-only
work not attempted in this sandbox - same disclosed limitation as every
other e2e test in this project.

Run standalone with:
    python -m unittest tests.test_outreach_llm_agent_pure
"""
import json
import unittest

from app.ai_agents.base import AgentInput, AgentOutcome
from app.ai_gateway.request import GatewayResponse, ResponseFormatType, TokenUsage
from app.outreach.channels.llm_agent import RESPONSE_FORMAT, OutreachEmailAgent

VALID_RESPONSE = {
    "subject": "Sourcing partnership for Acme Textiles",
    "blocks": [
        {"block_key": "opening_paragraph", "content": "I noticed your recent expansion...", "reasoning": "Anchored to primary signal."},
        {"block_key": "cta", "content": "Would it make sense to connect this week?", "reasoning": "Used primary strategy's CTA slot."},
    ],
    "confidence": 0.7,
    "reasoning": "Generated from the primary personalization strategy.",
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


class TestOutreachEmailAgentBuildContext(unittest.TestCase):
    def test_build_context_carries_business_context_through_unread(self):
        agent = OutreachEmailAgent()
        business_context = {"variables": {"company": "Acme"}, "blocks_to_write": []}
        context = agent.build_context(AgentInput(context=business_context))

        self.assertEqual(context.business_context, business_context)
        self.assertIsNotNone(context.system_instructions)
        self.assertIsNotNone(context.user_instructions)

    def test_build_context_reads_registered_prompt_template(self):
        from app.ai_agents.prompts.registry import get_prompt_template
        from app.outreach.channels.llm_agent import OUTREACH_EMAIL_AGENT_KEY, PROMPT_VERSION

        template = get_prompt_template(OUTREACH_EMAIL_AGENT_KEY, PROMPT_VERSION)
        agent = OutreachEmailAgent()
        context = agent.build_context(AgentInput(context={}))
        self.assertEqual(context.system_instructions, template.system_instructions)


class TestOutreachEmailAgentInterpret(unittest.TestCase):
    def test_interpret_succeeds_on_valid_json_string_content(self):
        agent = OutreachEmailAgent()
        response = _response(json.dumps(VALID_RESPONSE))

        output = agent.interpret(response, AgentInput(context={}))

        self.assertEqual(output.status, AgentOutcome.SUCCESS)
        self.assertEqual(output.result, VALID_RESPONSE)

    def test_interpret_succeeds_on_dict_content(self):
        agent = OutreachEmailAgent()
        response = _response(VALID_RESPONSE)

        output = agent.interpret(response, AgentInput(context={}))

        self.assertEqual(output.status, AgentOutcome.SUCCESS)

    def test_interpret_retries_on_malformed_json(self):
        agent = OutreachEmailAgent()
        response = _response("this is not json")

        output = agent.interpret(response, AgentInput(context={}))

        self.assertEqual(output.status, AgentOutcome.RETRY)
        self.assertIsNotNone(output.error)

    def test_interpret_retries_on_missing_subject(self):
        agent = OutreachEmailAgent()
        incomplete = {k: v for k, v in VALID_RESPONSE.items() if k != "subject"}
        response = _response(incomplete)

        output = agent.interpret(response, AgentInput(context={}))

        self.assertEqual(output.status, AgentOutcome.RETRY)
        self.assertIn("subject", output.error)

    def test_interpret_retries_on_block_missing_content(self):
        agent = OutreachEmailAgent()
        bad = dict(VALID_RESPONSE)
        bad["blocks"] = [{"block_key": "opening_paragraph"}]
        response = _response(bad)

        output = agent.interpret(response, AgentInput(context={}))

        self.assertEqual(output.status, AgentOutcome.RETRY)
        self.assertIn("content", output.error)

    def test_interpret_retries_on_empty_subject(self):
        agent = OutreachEmailAgent()
        bad = dict(VALID_RESPONSE)
        bad["subject"] = "   "
        response = _response(bad)

        output = agent.interpret(response, AgentInput(context={}))

        self.assertEqual(output.status, AgentOutcome.RETRY)

    def test_response_format_requests_json(self):
        self.assertEqual(RESPONSE_FORMAT.type, ResponseFormatType.JSON)
        self.assertIsNotNone(RESPONSE_FORMAT.json_schema)


class TestOutreachLlmMapping(unittest.TestCase):
    def test_index_blocks_by_key(self):
        from app.outreach.channels.llm_mapping import index_blocks_by_key

        indexed = index_blocks_by_key(VALID_RESPONSE)
        self.assertEqual(set(indexed), {"opening_paragraph", "cta"})
        self.assertEqual(indexed["cta"]["content"], "Would it make sense to connect this week?")

    def test_index_blocks_by_key_on_empty_response(self):
        from app.outreach.channels.llm_mapping import index_blocks_by_key

        self.assertEqual(index_blocks_by_key({}), {})


if __name__ == "__main__":
    unittest.main()
