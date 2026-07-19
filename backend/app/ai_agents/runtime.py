"""
AgentRuntime - M7.2, extended M7.3. The orchestrator that ties the split
Agent contract (base.py) to Prompt Builder and the AI Gateway - the only
place in this codebase that calls both PromptBuilder.build() and
AIGateway.complete() for an Agent invocation. Stateless, staticmethod-only
class - same style as app.ai_gateway.router.ProviderRouter and
app.prompt_builder.builder.PromptBuilder.

Execution flow, exactly matching the approved (post-refinement)
architecture's layer diagram:

    1. get_agent(agent_key)                         - AGENT_REGISTRY lookup
    2. resolve_execution_policy(agent_key)           - never hardcoded by the Agent
    3. agent.build_context(input_data)               - business content only
    4. PromptBuilder.build(context, policy)          - context + policy -> GatewayRequest
    5. AIGateway().complete(request)                 - provider routing/retry/fallback
    6. agent.interpret(response, input_data)         - GatewayResponse -> AgentOutput

A GatewayError escaping step 5 (the whole routing chain exhausted, or a
non-fallback-eligible error) is caught here and turned into an
AgentOutput(status=FAILURE, error=str(exc)) - Agent.interpret() is never
called with anything but a genuine GatewayResponse, so no Agent
implementation needs its own provider-failure handling logic.

M7.3 additions, both backward-compatible with every M7.2 caller/test:

  - AgentOutcome.RETRY handling: if interpret() returns RETRY, steps
    1-6 above are repeated (context is rebuilt fresh each attempt - an
    Agent's build_context() is expected to be a pure translation of
    AgentInput, so recomputing it carries no hidden state across
    attempts) up to settings.AGENT_RUNTIME_MAX_ATTEMPTS times. If still
    RETRY after the last attempt, that's reported as FAILURE (a RETRY
    escaping this Runtime would be meaningless to any caller - the same
    "exhausted retries becomes a terminal outcome" precedent
    AIGateway.complete() already applies one layer down).
  - run_with_metadata(): returns an AgentExecutionResult (AgentOutput
    plus provider_key/model/usage) instead of a bare AgentOutput -
    added for app.supervisor's own explainability needs (see that
    package's own docstring). run() itself is UNCHANGED in signature
    and behavior for the non-RETRY case - it now delegates to the same
    internal helper run_with_metadata() uses, but still returns exactly
    an AgentOutput, so every M7.2 caller and test keeps working
    unmodified.
"""
from app.ai_agents.base import Agent, AgentExecutionResult, AgentInput, AgentOutcome, AgentOutput
from app.ai_agents.execution_policy import resolve_execution_policy
from app.ai_agents.registry import get_agent
from app.ai_gateway.client import AIGateway
from app.ai_gateway.errors import GatewayError
from app.core.config import settings
from app.prompt_builder.builder import PromptBuilder


class AgentRuntime:
    @staticmethod
    def run(agent_key: str, input_data: AgentInput, *, gateway: AIGateway | None = None) -> AgentOutput:
        """`gateway` is an optional injection point for tests only (see
        tests/test_ai_execution_platform_e2e.py's own FakeProviderClient-
        based tests) - every real caller should omit it and get a fresh
        AIGateway(), which is itself stateless. Unchanged public shape
        from M7.2 - always returns a bare AgentOutput."""
        return AgentRuntime.run_with_metadata(agent_key, input_data, gateway=gateway).output

    @staticmethod
    def run_with_metadata(agent_key: str, input_data: AgentInput, *, gateway: AIGateway | None = None) -> AgentExecutionResult:
        """M7.3 addition - see module docstring. The richer sibling of
        run(); both share this one implementation."""
        agent: Agent = get_agent(agent_key)
        policy = resolve_execution_policy(agent_key)
        gateway = gateway or AIGateway()

        attempt = 0
        while attempt < settings.AGENT_RUNTIME_MAX_ATTEMPTS:
            attempt += 1
            context = agent.build_context(input_data)
            request = PromptBuilder.build(context, policy)

            try:
                response = gateway.complete(request)
            except GatewayError as exc:
                return AgentExecutionResult(output=AgentOutput(status=AgentOutcome.FAILURE, error=str(exc)))

            output = agent.interpret(response, input_data)
            if output.status != AgentOutcome.RETRY:
                return AgentExecutionResult(
                    output=output, provider_key=response.provider_key, model=response.model, usage=response.usage
                )

        exhausted = AgentOutput(
            status=AgentOutcome.FAILURE,
            error=f"agent '{agent_key}' returned RETRY {attempt} time(s); exhausted AGENT_RUNTIME_MAX_ATTEMPTS",
        )
        return AgentExecutionResult(output=exhausted, provider_key=response.provider_key, model=response.model, usage=response.usage)
