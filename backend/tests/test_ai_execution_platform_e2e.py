"""
End-to-end verification of M7.2's AI Execution Platform - the reference
verification for the whole Agent Runtime -> Prompt Builder -> AI Gateway
-> Provider Router chain, exercised mechanically with local test doubles
rather than a real database or a real AI provider.

Deliberately does NOT import app.ai_gateway.providers.registry (or
anything that transitively does) - that module imports the three
concrete provider clients, which in turn `import anthropic`/
`import openai`/`from google import genai`. Those SDKs are not
installed in every environment this test may run in (confirmed absent in
the sandbox this milestone was built in). AIGateway's own
`provider_lookup` constructor injection (see app.ai_gateway.client's own
docstring) exists specifically so this test can exercise the REAL
retry/fallback/error-handling logic in client.py without ever needing
those packages - every FakeProviderClient below is a local test double,
following the same `_FakeAction`/`_ScriptedAction` precedent already
established in M7.1's own test suite.

No database is touched anywhere in this file - AgentRuntime, PromptBuilder,
and AIGateway are all pure in-process Python, so this file is runnable
with plain `python -m unittest` in any environment, sandbox included.

Run standalone with:
    python -m unittest tests.test_ai_execution_platform_e2e
"""
import unittest

from app.ai_agents.base import Agent, AgentInput, AgentOutcome, AgentOutput
from app.ai_agents.execution_policy import EXECUTION_POLICY_REGISTRY, register_execution_policy
from app.ai_agents.registry import AGENT_REGISTRY, register_agent
from app.ai_agents.runtime import AgentRuntime
from app.ai_gateway.client import AIGateway
from app.ai_gateway.errors import InvalidRequestError, ProviderAuthError, ProviderUnavailableError
from app.ai_gateway.providers.base import ProviderClient
from app.ai_gateway.request import GatewayRequest, GatewayResponse, TokenUsage
from app.ai_gateway.router import ROUTING_POLICY, RoutingDecision
from app.prompt_builder.base import PromptContext
from app.prompt_builder.builder import PromptBuilder
from app.prompt_builder.policy import ExecutionPolicy


def _response(content, *, provider_key: str, model: str = "fake-model-v1") -> GatewayResponse:
    return GatewayResponse(
        content=content,
        tool_calls=None,
        usage=TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10, cost_usd=None),
        provider_key=provider_key,
        model=model,
        finish_reason="stop",
    )


# --- local test doubles -----------------------------------------------------


class _OkProviderClient(ProviderClient):
    key = "fake_ok"

    def is_configured(self) -> bool:
        return True

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        return _response("expected answer", provider_key=self.key)


class _RetryThenSucceedProviderClient(ProviderClient):
    key = "fake_retry_then_succeed"

    def __init__(self):
        self.attempts = 0

    def is_configured(self) -> bool:
        return True

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        self.attempts += 1
        if self.attempts < 2:
            raise ProviderUnavailableError("transient failure", provider_key=self.key)
        return _response("ok after retry", provider_key=self.key)


class _AlwaysUnavailableProviderClient(ProviderClient):
    key = "fake_always_unavailable"

    def __init__(self):
        self.attempts = 0

    def is_configured(self) -> bool:
        return True

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        self.attempts += 1
        raise ProviderUnavailableError("still down", provider_key=self.key)


class _AuthFailProviderClient(ProviderClient):
    """retryable=False, fallback_eligible=True - should NOT be retried on
    itself, but SHOULD let the chain fall through to the next provider."""

    key = "fake_auth_fail"

    def __init__(self):
        self.attempts = 0

    def is_configured(self) -> bool:
        return True

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        self.attempts += 1
        raise ProviderAuthError("bad credentials", provider_key=self.key)


class _InvalidRequestProviderClient(ProviderClient):
    """retryable=False, fallback_eligible=False - the whole chain must
    stop here; nothing after this provider may ever be attempted."""

    key = "fake_invalid_request"

    def __init__(self):
        self.attempts = 0

    def is_configured(self) -> bool:
        return True

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        self.attempts += 1
        raise InvalidRequestError("malformed request", provider_key=self.key)


class _NeverCalledProviderClient(ProviderClient):
    key = "fake_never_called"

    def __init__(self):
        self.attempts = 0

    def is_configured(self) -> bool:
        return True

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        self.attempts += 1
        raise AssertionError("this provider must never be called")


class _EchoAgent(Agent):
    key = "test.echo_agent"

    def build_context(self, input_data: AgentInput) -> PromptContext:
        return PromptContext(
            system_instructions="You are a test agent.",
            user_instructions=input_data.context.get("question"),
            business_context={"note": "hello", "structured": {"a": 1, "b": [1, 2, 3]}},
        )

    def interpret(self, response: GatewayResponse, input_data: AgentInput) -> AgentOutput:
        if response.content == "expected answer":
            return AgentOutput(status=AgentOutcome.SUCCESS, result={"answer": response.content})
        return AgentOutput(status=AgentOutcome.FAILURE, error=f"unexpected content: {response.content!r}")


def _make_gateway(provider_map: dict[str, ProviderClient]) -> AIGateway:
    def provider_lookup(provider_key: str) -> ProviderClient:
        provider = provider_map.get(provider_key)
        if provider is None:
            raise KeyError(provider_key)
        return provider

    return AIGateway(provider_lookup=provider_lookup)


# --- tests -------------------------------------------------------------------


class TestPromptBuilder(unittest.TestCase):
    def test_build_renders_system_and_user_messages(self):
        context = PromptContext(
            system_instructions="Be helpful.",
            user_instructions="What is 2+2?",
            business_context={"icp": {"industry": "textiles"}, "note": "plain string"},
        )
        policy = ExecutionPolicy(provider_capability="test", model="m1", temperature=0.2, max_tokens=100)

        request = PromptBuilder.build(context, policy)

        self.assertEqual(request.capability, "test")
        self.assertEqual(request.model, "m1")
        self.assertEqual(request.temperature, 0.2)
        self.assertEqual(request.max_tokens, 100)
        self.assertEqual(len(request.messages), 2)
        self.assertEqual(request.messages[0]["role"], "system")
        self.assertIn("Be helpful.", request.messages[0]["content"])
        self.assertIn("### icp", request.messages[0]["content"])
        self.assertIn("### note", request.messages[0]["content"])
        self.assertIn("plain string", request.messages[0]["content"])
        self.assertEqual(request.messages[1], {"role": "user", "content": "What is 2+2?"})

    def test_build_omits_empty_messages(self):
        context = PromptContext()
        policy = ExecutionPolicy(provider_capability="test")
        request = PromptBuilder.build(context, policy)
        self.assertEqual(request.messages, [])


class TestAIGatewayRetryAndFallback(unittest.TestCase):
    def test_complete_returns_immediately_on_success(self):
        provider = _OkProviderClient()
        gateway = _make_gateway({"fake_ok": provider})
        request = GatewayRequest(capability="x", messages=[{"role": "user", "content": "hi"}])

        with self._routed_to("fake_ok"):
            response = gateway.complete(request)

        self.assertEqual(response.content, "expected answer")
        self.assertEqual(response.provider_key, "fake_ok")

    def test_complete_retries_transient_error_within_max_attempts(self):
        provider = _RetryThenSucceedProviderClient()
        gateway = _make_gateway({"fake_retry_then_succeed": provider})
        request = GatewayRequest(capability="x")

        with self._routed_to("fake_retry_then_succeed"):
            response = gateway.complete(request)

        self.assertEqual(response.content, "ok after retry")
        self.assertEqual(provider.attempts, 2, "should retry exactly once before succeeding")

    def test_complete_exhausts_retries_then_raises(self):
        provider = _AlwaysUnavailableProviderClient()
        gateway = _make_gateway({"fake_always_unavailable": provider})
        request = GatewayRequest(capability="x")

        with self._routed_to("fake_always_unavailable"):
            with self.assertRaises(ProviderUnavailableError):
                gateway.complete(request)

        from app.core.config import settings

        self.assertEqual(provider.attempts, settings.AI_GATEWAY_MAX_ATTEMPTS_PER_PROVIDER)

    def test_complete_falls_back_to_next_provider_on_fallback_eligible_error(self):
        primary = _AuthFailProviderClient()
        fallback = _OkProviderClient()
        gateway = _make_gateway({"fake_auth_fail": primary, "fake_ok": fallback})
        request = GatewayRequest(capability="x")

        with self._routed_to("fake_auth_fail", fallbacks=["fake_ok"]):
            response = gateway.complete(request)

        self.assertEqual(response.provider_key, "fake_ok")
        self.assertEqual(primary.attempts, 1, "an auth error is not retryable - must not retry the same provider")

    def test_complete_does_not_fall_back_on_non_fallback_eligible_error(self):
        primary = _InvalidRequestProviderClient()
        never_called = _NeverCalledProviderClient()
        gateway = _make_gateway({"fake_invalid_request": primary, "fake_never_called": never_called})
        request = GatewayRequest(capability="x")

        with self._routed_to("fake_invalid_request", fallbacks=["fake_never_called"]):
            with self.assertRaises(InvalidRequestError):
                gateway.complete(request)

        self.assertEqual(never_called.attempts, 0, "a non-fallback-eligible error must stop the whole chain")

    def test_complete_raises_when_provider_not_in_lookup(self):
        gateway = _make_gateway({})
        request = GatewayRequest(capability="x")
        with self._routed_to("does_not_exist"):
            with self.assertRaises(Exception):
                gateway.complete(request)

    # --- helper: temporarily point ROUTING_POLICY["x"] at a specific chain ---
    class _routed_to:
        def __init__(self, primary: str, fallbacks: list[str] | None = None):
            self._primary = primary
            self._fallbacks = fallbacks or []
            self._had_prior = "x" in ROUTING_POLICY
            self._prior = ROUTING_POLICY.get("x")

        def __enter__(self):
            ROUTING_POLICY["x"] = RoutingDecision(primary=self._primary, fallbacks=self._fallbacks)

        def __exit__(self, *exc_info):
            if self._had_prior:
                ROUTING_POLICY["x"] = self._prior
            else:
                ROUTING_POLICY.pop("x", None)


class TestAgentRuntimeFullChain(unittest.TestCase):
    """Exercises the entire approved (post-refinement) layer diagram in one
    process, with a real Agent (build_context/interpret split), a real
    ExecutionPolicy resolution, a real PromptBuilder.build(), and a real
    AIGateway.complete() retry/fallback loop - only the ProviderClient at
    the very bottom is a test double."""

    AGENT_KEY = "test.echo_agent"
    CAPABILITY = "test_echo"

    def setUp(self):
        register_agent(self.AGENT_KEY, _EchoAgent())
        register_execution_policy(self.AGENT_KEY, ExecutionPolicy(provider_capability=self.CAPABILITY))

    def tearDown(self):
        AGENT_REGISTRY.pop(self.AGENT_KEY, None)
        EXECUTION_POLICY_REGISTRY.pop(self.AGENT_KEY, None)
        ROUTING_POLICY.pop(self.CAPABILITY, None)

    def test_agent_runtime_runs_full_chain_to_success(self):
        ROUTING_POLICY[self.CAPABILITY] = RoutingDecision(primary="fake_ok")
        gateway = _make_gateway({"fake_ok": _OkProviderClient()})

        output = AgentRuntime.run(self.AGENT_KEY, AgentInput(context={"question": "what is it?"}), gateway=gateway)

        self.assertEqual(output.status, AgentOutcome.SUCCESS)
        self.assertEqual(output.result, {"answer": "expected answer"})

    def test_agent_runtime_wraps_exhausted_gateway_chain_as_failure_output(self):
        ROUTING_POLICY[self.CAPABILITY] = RoutingDecision(primary="fake_always_unavailable")
        gateway = _make_gateway({"fake_always_unavailable": _AlwaysUnavailableProviderClient()})

        output = AgentRuntime.run(self.AGENT_KEY, AgentInput(context={"question": "what is it?"}), gateway=gateway)

        self.assertEqual(output.status, AgentOutcome.FAILURE)
        self.assertIsNotNone(output.error)

    def test_agent_runtime_lets_interpret_reject_an_unexpected_response(self):
        class _WrongAnswerProviderClient(ProviderClient):
            key = "fake_wrong_answer"

            def is_configured(self):
                return True

            def complete(self, request):
                return _response("something else entirely", provider_key=self.key)

        ROUTING_POLICY[self.CAPABILITY] = RoutingDecision(primary="fake_wrong_answer")
        gateway = _make_gateway({"fake_wrong_answer": _WrongAnswerProviderClient()})

        output = AgentRuntime.run(self.AGENT_KEY, AgentInput(context={"question": "what is it?"}), gateway=gateway)

        self.assertEqual(output.status, AgentOutcome.FAILURE)
        self.assertIn("unexpected content", output.error)

    def test_agent_runtime_uses_default_policy_when_none_registered(self):
        # A second agent with no registered ExecutionPolicy must still run,
        # routed through ROUTING_POLICY["default"] via DEFAULT_EXECUTION_POLICY.
        register_agent("test.no_policy_agent", _EchoAgent())
        self.addCleanup(lambda: AGENT_REGISTRY.pop("test.no_policy_agent", None))

        # M11 (AI Provider Hierarchy): ROUTING_POLICY is now an empty-by-
        # default TEST-ONLY override seam (see router.py's own docstring) -
        # `original_default` is expected to be None here, not a pre-M11
        # pre-populated "default" entry. Cleanup restores that exact prior
        # state (pop if there wasn't one, not a conditional no-op) so this
        # test never leaks a "default" override into whichever test runs
        # next in the same process.
        original_default = ROUTING_POLICY.get("default")
        ROUTING_POLICY["default"] = RoutingDecision(primary="fake_ok")

        def _restore_default():
            if original_default is not None:
                ROUTING_POLICY["default"] = original_default
            else:
                ROUTING_POLICY.pop("default", None)

        self.addCleanup(_restore_default)

        gateway = _make_gateway({"fake_ok": _OkProviderClient()})
        output = AgentRuntime.run("test.no_policy_agent", AgentInput(context={"question": "x"}), gateway=gateway)

        self.assertEqual(output.status, AgentOutcome.SUCCESS)


if __name__ == "__main__":
    unittest.main()
