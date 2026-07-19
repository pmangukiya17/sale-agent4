"""
End-to-end verification of M7.3's Supervisor / Orchestrator Layer -
mirrors tests/test_ai_execution_platform_e2e.py's own precedent exactly:
real execution of SupervisorRuntime against local test doubles (fake
Agents, a fake ProviderClient, and fake Supervisor implementations),
never a real database or a real AI provider. Runnable with plain
`python -m unittest` in any environment, sandbox included - see
app.ai_gateway.client's own docstring for why AIGateway's
provider_lookup injection makes this possible without the real provider
SDKs installed.

Covers: single-agent run-to-completion, parallel fan-out (both agents
recorded, explainable inputs_consumed), WAIT/resume across two separate
step()-driving calls (proving statelessness between calls, not a
continuous loop), plan validation rejecting an unknown agent_key and an
allowlist violation (fail-closed, agent never actually invoked),
max-execution-depth enforcement, agent-level RETRY being fully resolved
inside AgentRuntime (never visible to Supervisor), execution_id
consistency across a whole run plus its contextvar-based logging
correlation availability window, and SupervisionState's own
versioning/timestamp fields.

Run standalone with:
    python -m unittest tests.test_supervisor_e2e
"""
import unittest

from app.ai_agents.base import Agent, AgentInput, AgentOutcome, AgentOutput
from app.ai_agents.execution_policy import EXECUTION_POLICY_REGISTRY, register_execution_policy
from app.ai_agents.registry import AGENT_REGISTRY, register_agent
from app.ai_gateway.client import AIGateway
from app.ai_gateway.providers.base import ProviderClient
from app.ai_gateway.request import GatewayRequest, GatewayResponse, TokenUsage
from app.ai_gateway.router import ROUTING_POLICY, RoutingDecision
from app.core.config import settings
from app.prompt_builder.base import PromptContext
from app.prompt_builder.policy import ExecutionPolicy
from app.supervisor.base import (
    SUPERVISION_STATE_SCHEMA_VERSION,
    AgentInvocationRequest,
    DecisionKind,
    ResumeTrigger,
    ResumeTriggerType,
    Supervisor,
    SupervisorDecision,
    SupervisionState,
    SupervisionStep,
)
from app.supervisor.observability import current_execution_id
from app.supervisor.plan_validation import validate_decision
from app.supervisor.registry import DEFAULT_SUPERVISOR_VERSION, SUPERVISOR_REGISTRY, register_default_version, register_supervisor
from app.supervisor.runtime import SupervisorRuntime


def _response(content, *, provider_key: str) -> GatewayResponse:
    return GatewayResponse(
        content=content,
        tool_calls=None,
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2, cost_usd=None),
        provider_key=provider_key,
        model="fake-model-v1",
        finish_reason="stop",
    )


# --- local test doubles: providers -------------------------------------------


class _OkProviderClient(ProviderClient):
    key = "fake_ok"

    def is_configured(self) -> bool:
        return True

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        return _response("ok", provider_key=self.key)


def _make_gateway() -> AIGateway:
    provider = _OkProviderClient()

    def provider_lookup(provider_key: str) -> ProviderClient:
        if provider_key != provider.key:
            raise KeyError(provider_key)
        return provider

    return AIGateway(provider_lookup=provider_lookup)


# --- local test doubles: agents -----------------------------------------------


class _EchoAgent(Agent):
    key = "supervisor_test.echo_agent"

    def build_context(self, input_data: AgentInput) -> PromptContext:
        return PromptContext(user_instructions=input_data.context.get("question", ""))

    def interpret(self, response: GatewayResponse, input_data: AgentInput) -> AgentOutput:
        return AgentOutput(status=AgentOutcome.SUCCESS, result={"answer": response.content})


class _RetryOnceThenSucceedAgent(Agent):
    key = "supervisor_test.retry_once_agent"

    def __init__(self):
        self.calls = 0

    def build_context(self, input_data: AgentInput) -> PromptContext:
        return PromptContext(user_instructions="whatever")

    def interpret(self, response: GatewayResponse, input_data: AgentInput) -> AgentOutput:
        self.calls += 1
        if self.calls < 2:
            return AgentOutput(status=AgentOutcome.RETRY, error="not good enough yet")
        return AgentOutput(status=AgentOutcome.SUCCESS, result={"attempt": self.calls})


class _ExecutionIdCapturingAgent(Agent):
    key = "supervisor_test.exec_id_capture_agent"

    def __init__(self):
        self.captured_execution_id = None

    def build_context(self, input_data: AgentInput) -> PromptContext:
        self.captured_execution_id = current_execution_id()
        return PromptContext(user_instructions="x")

    def interpret(self, response: GatewayResponse, input_data: AgentInput) -> AgentOutput:
        return AgentOutput(status=AgentOutcome.SUCCESS, result={})


# --- local test doubles: supervisors ------------------------------------------


class _SingleAgentThenCompleteSupervisor(Supervisor):
    key = "supervisor_test.single_then_complete"
    allowed_agent_keys = frozenset({_EchoAgent.key})

    def decide_next(self, state: SupervisionState) -> SupervisorDecision:
        if len(state.history) == 0:
            return SupervisorDecision.run_agents(
                reason="need the echo agent's answer before anything else",
                invocations=(AgentInvocationRequest(agent_key=_EchoAgent.key, context={"question": "hi"}, inputs_consumed=()),),
            )
        return SupervisorDecision.complete(
            reason="echo agent answered, nothing more needed",
            result={"echo": state.history[0].agent_results[0].output.result},
        )


class _ParallelThenCompleteSupervisor(Supervisor):
    key = "supervisor_test.parallel_then_complete"
    allowed_agent_keys = frozenset({_EchoAgent.key})

    def decide_next(self, state: SupervisionState) -> SupervisorDecision:
        if len(state.history) == 0:
            return SupervisorDecision.run_agents(
                reason="these two have no dependency on each other, run them together",
                invocations=(
                    AgentInvocationRequest(agent_key=_EchoAgent.key, context={"question": "a"}),
                    AgentInvocationRequest(agent_key=_EchoAgent.key, context={"question": "b"}),
                ),
            )
        return SupervisorDecision.complete(
            reason="both parallel invocations resolved",
            result={"count": len(state.history[0].agent_results)},
            )


class _WaitThenResumeSupervisor(Supervisor):
    key = "supervisor_test.wait_then_resume"
    allowed_agent_keys = frozenset({_EchoAgent.key})

    def decide_next(self, state: SupervisionState) -> SupervisorDecision:
        already_waited = any(step.decision.kind == DecisionKind.WAIT for step in state.history)
        if not already_waited:
            return SupervisorDecision.wait(
                reason="need a human approval before continuing",
                resume_trigger=ResumeTrigger(type=ResumeTriggerType.HUMAN_APPROVAL, payload={"approval_subject": "test"}),
            )
        if len(state.history) == 1:
            return SupervisorDecision.run_agents(
                reason="approval granted, proceed",
                invocations=(AgentInvocationRequest(agent_key=_EchoAgent.key, context={"question": "post-approval"}, inputs_consumed=(0,)),),
            )
        return SupervisorDecision.complete(reason="finished after resuming from approval", result={})


class _UnknownAgentSupervisor(Supervisor):
    key = "supervisor_test.unknown_agent"
    allowed_agent_keys = frozenset({"does.not.exist"})

    def decide_next(self, state: SupervisionState) -> SupervisorDecision:
        return SupervisorDecision.run_agents(
            reason="try an unregistered agent",
            invocations=(AgentInvocationRequest(agent_key="does.not.exist", context={}),),
        )


class _AllowlistViolationSupervisor(Supervisor):
    key = "supervisor_test.allowlist_violation"
    allowed_agent_keys = frozenset()  # empty - even a real, registered agent is disallowed

    def decide_next(self, state: SupervisionState) -> SupervisorDecision:
        return SupervisorDecision.run_agents(
            reason="try echo agent despite an empty allowlist",
            invocations=(AgentInvocationRequest(agent_key=_EchoAgent.key, context={}),),
        )


class _InfiniteLoopSupervisor(Supervisor):
    key = "supervisor_test.infinite_loop"
    allowed_agent_keys = frozenset({_EchoAgent.key})

    def decide_next(self, state: SupervisionState) -> SupervisorDecision:
        return SupervisorDecision.run_agents(
            reason="keep going forever (deliberately, to exercise the max-depth guard)",
            invocations=(AgentInvocationRequest(agent_key=_EchoAgent.key, context={}),),
        )


class _RetryAgentSupervisor(Supervisor):
    key = "supervisor_test.retry_agent_plan"
    allowed_agent_keys = frozenset({_RetryOnceThenSucceedAgent.key})

    def decide_next(self, state: SupervisionState) -> SupervisorDecision:
        if len(state.history) == 0:
            return SupervisorDecision.run_agents(
                reason="invoke the retry agent", invocations=(AgentInvocationRequest(agent_key=_RetryOnceThenSucceedAgent.key, context={}),)
            )
        return SupervisorDecision.complete(reason="done", result={"output": state.history[0].agent_results[0].output.result})


class _ExecIdCaptureSupervisor(Supervisor):
    key = "supervisor_test.exec_id_capture_plan"
    allowed_agent_keys = frozenset({_ExecutionIdCapturingAgent.key})

    def decide_next(self, state: SupervisionState) -> SupervisorDecision:
        if len(state.history) == 0:
            return SupervisorDecision.run_agents(
                reason="capture the execution id mid-invocation",
                invocations=(AgentInvocationRequest(agent_key=_ExecutionIdCapturingAgent.key, context={}),),
            )
        return SupervisorDecision.complete(reason="done", result={})


# --- tests ---------------------------------------------------------------------


class SupervisorTestCase(unittest.TestCase):
    """Shared registry-cleanup plumbing - every test registers whatever
    agents/supervisors it needs and this always tears them down, mirroring
    tests/test_ai_execution_platform_e2e.py's own setUp/tearDown pattern."""

    def setUp(self):
        self._agent_keys: list[str] = []
        self._capability_keys: list[str] = []
        self._supervisor_keys: list[tuple[str, int]] = []
        self.gateway = _make_gateway()

    def tearDown(self):
        for key in self._agent_keys:
            AGENT_REGISTRY.pop(key, None)
            EXECUTION_POLICY_REGISTRY.pop(key, None)
        for key in self._capability_keys:
            ROUTING_POLICY.pop(key, None)
        for plan_key, version in self._supervisor_keys:
            SUPERVISOR_REGISTRY.pop((plan_key, version), None)
            DEFAULT_SUPERVISOR_VERSION.pop(plan_key, None)

    def register_agent(self, agent: Agent) -> None:
        register_agent(agent.key, agent)
        self._agent_keys.append(agent.key)
        capability = f"cap.{agent.key}"
        register_execution_policy(agent.key, ExecutionPolicy(provider_capability=capability))
        ROUTING_POLICY[capability] = RoutingDecision(primary="fake_ok")
        self._capability_keys.append(capability)

    def register_supervisor(self, supervisor: Supervisor, *, version: int = 1) -> None:
        """M7.4: SUPERVISOR_REGISTRY is now keyed by (plan_key, version) -
        see app.supervisor.registry's own docstring. Every test in this
        file registers at version=1 (the default), matching
        SupervisionState.start()'s own plan_version=1 default, so
        get_supervisor(state.plan_key, state.plan_version) inside
        SupervisorRuntime.step() resolves correctly without every test
        needing to know about versioning explicitly. Also registers this
        version as plan_key's default (register_default_version()),
        purely so any test that exercises SupervisorRuntime.start_plan()
        (the M7.4 convenience constructor) has a default to resolve -
        existing tests construct SupervisionState.start() directly and
        never need this, but registering it is harmless and keeps this
        helper usable for either path."""
        register_supervisor(supervisor.key, version, supervisor)
        register_default_version(supervisor.key, version)
        self._supervisor_keys.append((supervisor.key, version))


class TestSupervisorRuntimeSingleAgent(SupervisorTestCase):
    def test_run_to_completion(self):
        self.register_agent(_EchoAgent())
        self.register_supervisor(_SingleAgentThenCompleteSupervisor())

        state = SupervisionState.start(plan_key=_SingleAgentThenCompleteSupervisor.key, initial_context={})
        final_state = SupervisorRuntime.run_to_suspension(state, gateway=self.gateway)

        self.assertEqual(len(final_state.history), 2)
        self.assertEqual(final_state.history[0].decision.kind, DecisionKind.RUN_AGENTS)
        self.assertEqual(final_state.history[0].agent_results[0].output.status, AgentOutcome.SUCCESS)
        self.assertEqual(final_state.history[0].agent_results[0].provider_key, "fake_ok")
        self.assertEqual(final_state.history[1].decision.kind, DecisionKind.COMPLETE)
        self.assertEqual(final_state.execution_id, state.execution_id, "execution_id must stay immutable across a run")
        for step in final_state.history:
            self.assertTrue(step.decision.reason, "every decision must carry a non-empty, explainable reason")


class TestSupervisorRuntimeParallel(SupervisorTestCase):
    def test_parallel_agents_both_recorded(self):
        self.register_agent(_EchoAgent())
        self.register_supervisor(_ParallelThenCompleteSupervisor())

        state = SupervisionState.start(plan_key=_ParallelThenCompleteSupervisor.key, initial_context={})
        final_state = SupervisorRuntime.run_to_suspension(state, gateway=self.gateway)

        self.assertEqual(len(final_state.history[0].agent_results), 2, "both parallel invocations must be recorded")
        self.assertEqual(final_state.history[1].decision.result, {"count": 2})


class TestSupervisorRuntimeWaitAndResume(SupervisorTestCase):
    def test_wait_suspends_and_can_be_resumed_by_a_separate_call(self):
        self.register_agent(_EchoAgent())
        self.register_supervisor(_WaitThenResumeSupervisor())

        state = SupervisionState.start(plan_key=_WaitThenResumeSupervisor.key, initial_context={})
        suspended = SupervisorRuntime.run_to_suspension(state, gateway=self.gateway)

        self.assertEqual(len(suspended.history), 1)
        self.assertEqual(suspended.history[0].decision.kind, DecisionKind.WAIT)
        self.assertEqual(suspended.history[0].decision.resume_trigger.type, ResumeTriggerType.HUMAN_APPROVAL)

        # Resuming is just calling run_to_suspension again with the SAME
        # state object a caller could have persisted and reloaded in
        # between - no loop was held open, no in-memory object survived
        # between these two calls beyond the plain data in `suspended`.
        resumed = SupervisorRuntime.run_to_suspension(suspended, gateway=self.gateway)
        self.assertEqual(resumed.history[-1].decision.kind, DecisionKind.COMPLETE)
        self.assertEqual(resumed.execution_id, state.execution_id)
        self.assertEqual(resumed.history[1].decision.agent_invocations[0].inputs_consumed, (0,))


class TestSupervisorRuntimeValidation(SupervisorTestCase):
    def test_unknown_agent_is_rejected_and_never_invoked(self):
        self.register_supervisor(_UnknownAgentSupervisor())
        state = SupervisionState.start(plan_key=_UnknownAgentSupervisor.key, initial_context={})

        new_state, decision = SupervisorRuntime.step(state, gateway=self.gateway)

        self.assertEqual(decision.kind, DecisionKind.ABORT)
        self.assertIn("unknown agent_key", decision.error)
        self.assertEqual(new_state.history[0].agent_results, (), "a rejected decision must never actually invoke anything")

    def test_allowlist_violation_is_rejected_even_for_a_real_registered_agent(self):
        self.register_agent(_EchoAgent())
        self.register_supervisor(_AllowlistViolationSupervisor())
        state = SupervisionState.start(plan_key=_AllowlistViolationSupervisor.key, initial_context={})

        new_state, decision = SupervisorRuntime.step(state, gateway=self.gateway)

        self.assertEqual(decision.kind, DecisionKind.ABORT)
        self.assertIn("not in the allowlist", decision.error)
        self.assertEqual(new_state.history[0].agent_results, ())

    def test_max_execution_depth_forces_abort(self):
        self.register_agent(_EchoAgent())
        self.register_supervisor(_InfiniteLoopSupervisor())

        original_depth = settings.SUPERVISOR_MAX_EXECUTION_DEPTH
        settings.SUPERVISOR_MAX_EXECUTION_DEPTH = 3
        try:
            state = SupervisionState.start(plan_key=_InfiniteLoopSupervisor.key, initial_context={})
            final_state = SupervisorRuntime.run_to_suspension(state, gateway=self.gateway, max_iterations=20)
        finally:
            settings.SUPERVISOR_MAX_EXECUTION_DEPTH = original_depth

        self.assertEqual(final_state.history[-1].decision.kind, DecisionKind.ABORT)
        self.assertLessEqual(len(final_state.history), 4, "must stop at (or just past) the configured depth ceiling")

    def test_validate_decision_rejects_malformed_decisions_directly(self):
        supervisor = _SingleAgentThenCompleteSupervisor()
        state = SupervisionState.start(plan_key="x", initial_context={})

        complete_without_result = SupervisorDecision(kind=DecisionKind.COMPLETE, reason="oops", result=None)
        self.assertFalse(validate_decision(complete_without_result, state, supervisor).is_valid)

        fail_without_error = SupervisorDecision(kind=DecisionKind.FAIL, reason="oops", error=None)
        self.assertFalse(validate_decision(fail_without_error, state, supervisor).is_valid)

        wait_without_trigger = SupervisorDecision(kind=DecisionKind.WAIT, reason="oops", resume_trigger=None)
        self.assertFalse(validate_decision(wait_without_trigger, state, supervisor).is_valid)


class TestSupervisorRuntimeAgentRetry(SupervisorTestCase):
    def test_agent_level_retry_resolved_inside_agent_runtime_never_visible_to_supervisor(self):
        self.register_agent(_RetryOnceThenSucceedAgent())
        self.register_supervisor(_RetryAgentSupervisor())

        state = SupervisionState.start(plan_key=_RetryAgentSupervisor.key, initial_context={})
        final_state = SupervisorRuntime.run_to_suspension(state, gateway=self.gateway)

        agent_result = final_state.history[0].agent_results[0]
        self.assertEqual(agent_result.output.status, AgentOutcome.SUCCESS, "RETRY must never escape AgentRuntime as a final status")
        self.assertEqual(agent_result.output.result, {"attempt": 2})


class TestSupervisorExecutionIdCorrelation(SupervisorTestCase):
    def test_execution_id_available_only_during_agent_invocation(self):
        agent = _ExecutionIdCapturingAgent()
        self.register_agent(agent)
        self.register_supervisor(_ExecIdCaptureSupervisor())

        self.assertIsNone(current_execution_id(), "nothing in progress before the run starts")
        state = SupervisionState.start(plan_key=_ExecIdCaptureSupervisor.key, initial_context={})
        SupervisorRuntime.run_to_suspension(state, gateway=self.gateway)

        self.assertEqual(agent.captured_execution_id, str(state.execution_id))
        self.assertIsNone(current_execution_id(), "must be cleared again once the invocation finishes")


class TestSupervisionStateShape(unittest.TestCase):
    def test_versioning_and_timestamps(self):
        state = SupervisionState.start(plan_key="whatever", initial_context={"x": 1}, plan_version=3)

        self.assertEqual(state.schema_version, SUPERVISION_STATE_SCHEMA_VERSION)
        self.assertEqual(state.plan_version, 3)
        self.assertEqual(state.created_at, state.updated_at)
        self.assertEqual(state.history, ())

        step = SupervisionStep(step_index=0, decision=SupervisorDecision.complete(reason="x", result={}))
        next_state = state.with_step(step)

        self.assertEqual(len(next_state.history), 1)
        self.assertEqual(next_state.created_at, state.created_at, "created_at must never change")
        self.assertGreaterEqual(next_state.updated_at, state.updated_at)
        self.assertEqual(next_state.execution_id, state.execution_id, "with_step must never mint a new execution_id")


if __name__ == "__main__":
    unittest.main()
