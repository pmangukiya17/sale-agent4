"""
End-to-end verification of M7.4's Workflow <-> Supervisor bridge -
mirrors tests/test_supervisor_e2e.py's own precedent exactly: real
execution against local test doubles (fake Agents, a fake
ProviderClient, fake Supervisor implementations), never a real database
or a real AI provider. Runnable with plain `python -m unittest` in any
environment, sandbox included.

Covers:
  - versioned SUPERVISOR_REGISTRY: two versions of the same plan_key
    resolve independently; register_default_version() validates the
    version exists first; resolve_default_version() raises when unset.
  - SupervisorRuntime.start_plan() resolves the registered default
    version onto a freshly-minted SupervisionState.
  - SupervisionState (de)serialization round-trips exactly through
    state_to_dict()/state_from_dict(), including a WAIT step's
    ResumeTrigger and a RUN_AGENTS step's AgentStepResult/TokenUsage;
    a schema_version mismatch on load raises.
  - SupervisorInvocationAction: fresh start with no agents (COMPLETE ->
    SUCCESS), fresh start invoking a real agent via an injected fake
    gateway (COMPLETE -> SUCCESS with a real AgentStepResult recorded),
    WAIT -> RETRY -> a SECOND, independent execute() call (simulating
    the Step Runner's own context merge-and-reinvoke between ticks)
    correctly resumes and reaches COMPLETE -> SUCCESS, FAIL -> FAILURE,
    and a missing plan_key in action_config -> FAILURE without ever
    starting a plan.

Run standalone with:
    python -m unittest tests.test_supervisor_invocation_action_e2e
"""
import unittest
import uuid

from app.ai_agents.base import Agent, AgentInput, AgentOutcome, AgentOutput
from app.ai_agents.execution_policy import EXECUTION_POLICY_REGISTRY, register_execution_policy
from app.ai_agents.registry import AGENT_REGISTRY, register_agent
from app.ai_gateway.client import AIGateway
from app.ai_gateway.providers.base import ProviderClient
from app.ai_gateway.request import GatewayRequest, GatewayResponse, TokenUsage
from app.ai_gateway.router import ROUTING_POLICY, RoutingDecision
from app.prompt_builder.base import PromptContext
from app.prompt_builder.policy import ExecutionPolicy
from app.supervisor.base import (
    SUPERVISION_STATE_SCHEMA_VERSION,
    AgentInvocationRequest,
    AgentStepResult,
    DecisionKind,
    ResumeTrigger,
    ResumeTriggerType,
    Supervisor,
    SupervisorDecision,
    SupervisionState,
    SupervisionStep,
)
from app.supervisor.registry import (
    DEFAULT_SUPERVISOR_VERSION,
    SUPERVISOR_REGISTRY,
    register_default_version,
    register_supervisor,
    resolve_default_version,
)
from app.supervisor.runtime import SupervisorRuntime
from app.supervisor.serialization import state_from_dict, state_to_dict
from app.workflow_actions.supervisor_invocation_action import SupervisorInvocationAction
from app.workflow_engine.actions.base import ActionInput, ActionOutcome

_STATE_KEY = "_supervision_state"  # must match SupervisorInvocationAction's own reserved key


def _response(content, *, provider_key: str) -> GatewayResponse:
    return GatewayResponse(
        content=content,
        tool_calls=None,
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2, cost_usd=0.001),
        provider_key=provider_key,
        model="fake-model-v1",
        finish_reason="stop",
    )


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


class _EchoAgent(Agent):
    key = "supervisor_invocation_test.echo_agent"

    def build_context(self, input_data: AgentInput) -> PromptContext:
        return PromptContext(user_instructions=input_data.context.get("question", ""))

    def interpret(self, response: GatewayResponse, input_data: AgentInput) -> AgentOutput:
        return AgentOutput(status=AgentOutcome.SUCCESS, result={"answer": response.content})


class _CompleteImmediatelySupervisor(Supervisor):
    key = "supervisor_invocation_test.complete_immediately"
    allowed_agent_keys = frozenset()

    def decide_next(self, state: SupervisionState) -> SupervisorDecision:
        return SupervisorDecision.complete(reason="nothing to do", result={"seen_initial_context": state.initial_context})


class _RunAgentThenCompleteSupervisor(Supervisor):
    key = "supervisor_invocation_test.run_agent_then_complete"
    allowed_agent_keys = frozenset({_EchoAgent.key})

    def decide_next(self, state: SupervisionState) -> SupervisorDecision:
        if len(state.history) == 0:
            return SupervisorDecision.run_agents(
                reason="need the echo agent's answer",
                invocations=(AgentInvocationRequest(agent_key=_EchoAgent.key, context={"question": "hi"}),),
            )
        return SupervisorDecision.complete(reason="done", result={"echo": state.history[0].agent_results[0].output.result})


class _WaitOnceThenCompleteSupervisor(Supervisor):
    key = "supervisor_invocation_test.wait_once_then_complete"
    allowed_agent_keys = frozenset()

    def decide_next(self, state: SupervisionState) -> SupervisorDecision:
        already_waited = any(step.decision.kind == DecisionKind.WAIT for step in state.history)
        if not already_waited:
            return SupervisorDecision.wait(
                reason="waiting for a deadline",
                resume_trigger=ResumeTrigger(type=ResumeTriggerType.TIME, payload={"resume_at": "2099-01-01T00:00:00+00:00"}),
            )
        return SupervisorDecision.complete(reason="deadline reached, proceeding", result={})


class _FailImmediatelySupervisor(Supervisor):
    key = "supervisor_invocation_test.fail_immediately"
    allowed_agent_keys = frozenset()

    def decide_next(self, state: SupervisionState) -> SupervisorDecision:
        return SupervisorDecision.fail(reason="nothing else to try", error="deliberate test failure")


class _SupervisorInvocationTestCase(unittest.TestCase):
    """Shared registry cleanup - mirrors test_supervisor_e2e.py's own
    SupervisorTestCase, extended with default-version bookkeeping since
    this file's tests exercise SupervisorRuntime.start_plan()."""

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

    def register_supervisor(self, supervisor: Supervisor, *, version: int = 1, set_default: bool = True) -> None:
        register_supervisor(supervisor.key, version, supervisor)
        self._supervisor_keys.append((supervisor.key, version))
        if set_default:
            register_default_version(supervisor.key, version)


class TestSupervisorRegistryVersioning(_SupervisorInvocationTestCase):
    def test_two_versions_of_the_same_plan_key_resolve_independently(self):
        v1 = _CompleteImmediatelySupervisor()
        v2 = _CompleteImmediatelySupervisor()
        register_supervisor(v1.key, 1, v1)
        self._supervisor_keys.append((v1.key, 1))
        register_supervisor(v1.key, 2, v2)
        self._supervisor_keys.append((v1.key, 2))

        from app.supervisor.registry import get_supervisor

        self.assertIs(get_supervisor(v1.key, 1), v1)
        self.assertIs(get_supervisor(v1.key, 2), v2)

    def test_register_default_version_rejects_an_unregistered_version(self):
        with self.assertRaises(KeyError):
            register_default_version("supervisor_invocation_test.never_registered", 1)

    def test_resolve_default_version_raises_when_unset(self):
        supervisor = _CompleteImmediatelySupervisor()
        register_supervisor(supervisor.key, 1, supervisor)
        self._supervisor_keys.append((supervisor.key, 1))
        # deliberately NOT calling register_default_version()
        with self.assertRaises(KeyError):
            resolve_default_version(supervisor.key)


class TestSupervisorRuntimeStartPlan(_SupervisorInvocationTestCase):
    def test_start_plan_resolves_the_registered_default_version(self):
        self.register_supervisor(_CompleteImmediatelySupervisor(), version=5)

        state = SupervisorRuntime.start_plan(_CompleteImmediatelySupervisor.key, initial_context={"x": 1})

        self.assertEqual(state.plan_version, 5)
        self.assertEqual(state.initial_context, {"x": 1})
        self.assertEqual(state.history, ())

        final_state = SupervisorRuntime.run_to_suspension(state, gateway=self.gateway)
        self.assertEqual(final_state.history[-1].decision.kind, DecisionKind.COMPLETE)


class TestSupervisionStateSerializationRoundTrip(unittest.TestCase):
    def test_round_trip_preserves_a_wait_step_and_a_run_agents_step(self):
        state = SupervisionState.start(plan_key="serialization_test.plan", initial_context={"a": 1}, plan_version=2)

        wait_step = SupervisionStep(
            step_index=0,
            decision=SupervisorDecision.wait(
                reason="waiting", resume_trigger=ResumeTrigger(type=ResumeTriggerType.EVENT, payload={"event_type": "x"})
            ),
        )
        state = state.with_step(wait_step)

        run_agents_step = SupervisionStep(
            step_index=1,
            decision=SupervisorDecision.run_agents(
                reason="go",
                invocations=(AgentInvocationRequest(agent_key="a.b", context={"q": "hi"}, inputs_consumed=(0,)),),
            ),
            agent_results=(
                AgentStepResult(
                    agent_key="a.b",
                    output=AgentOutput(status=AgentOutcome.SUCCESS, result={"answer": "hi"}),
                    provider_key="fake_ok",
                    model="fake-model-v1",
                    usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2, cost_usd=0.001),
                ),
            ),
        )
        state = state.with_step(run_agents_step)

        round_tripped = state_from_dict(state_to_dict(state))

        self.assertEqual(round_tripped, state)

    def test_schema_version_mismatch_raises(self):
        state = SupervisionState.start(plan_key="serialization_test.plan", initial_context={})
        data = state_to_dict(state)
        data["schema_version"] = SUPERVISION_STATE_SCHEMA_VERSION + 1

        with self.assertRaises(ValueError):
            state_from_dict(data)


class TestSupervisorInvocationActionFreshStart(_SupervisorInvocationTestCase):
    def test_complete_with_no_agents_returns_success(self):
        self.register_supervisor(_CompleteImmediatelySupervisor())
        action = SupervisorInvocationAction()

        action_input = ActionInput(
            workflow_instance_id=uuid.uuid4(),
            step_id="step-1",
            context={"foo": "bar"},
            idempotency_key="k1",
            action_config={"plan_key": _CompleteImmediatelySupervisor.key},
        )
        output = action.execute(action_input)

        self.assertEqual(output.status, ActionOutcome.SUCCESS)
        self.assertIn(_STATE_KEY, output.result)
        self.assertEqual(output.result["supervisor_result"], {"seen_initial_context": {"foo": "bar"}})

    def test_complete_after_running_a_real_agent_returns_success(self):
        self.register_agent(_EchoAgent())
        self.register_supervisor(_RunAgentThenCompleteSupervisor())
        action = SupervisorInvocationAction(gateway=self.gateway)

        action_input = ActionInput(
            workflow_instance_id=uuid.uuid4(),
            step_id="step-1",
            context={},
            idempotency_key="k1",
            action_config={"plan_key": _RunAgentThenCompleteSupervisor.key},
        )
        output = action.execute(action_input)

        self.assertEqual(output.status, ActionOutcome.SUCCESS)
        self.assertEqual(output.result["supervisor_result"], {"echo": {"answer": "ok"}})

    def test_fail_decision_returns_failure_with_error(self):
        self.register_supervisor(_FailImmediatelySupervisor())
        action = SupervisorInvocationAction()

        action_input = ActionInput(
            workflow_instance_id=uuid.uuid4(),
            step_id="step-1",
            context={},
            idempotency_key="k1",
            action_config={"plan_key": _FailImmediatelySupervisor.key},
        )
        output = action.execute(action_input)

        self.assertEqual(output.status, ActionOutcome.FAILURE)
        self.assertEqual(output.error, "deliberate test failure")

    def test_missing_plan_key_returns_failure_without_starting_a_plan(self):
        action = SupervisorInvocationAction()

        action_input = ActionInput(
            workflow_instance_id=uuid.uuid4(),
            step_id="step-1",
            context={},
            idempotency_key="k1",
            action_config={},
        )
        output = action.execute(action_input)

        self.assertEqual(output.status, ActionOutcome.FAILURE)
        self.assertIn("plan_key", output.error)


class TestSupervisorInvocationActionWaitAndResume(_SupervisorInvocationTestCase):
    def test_wait_returns_pending_and_a_second_call_resumes_to_completion(self):
        """Post-architecture-review correction: WAIT must be a genuine
        suspension (ActionOutcome.PENDING - the same contract
        WaitForEventAction already uses), never ActionOutcome.RETRY. This
        test proves two things: (1) the first call suspends correctly -
        PENDING, no `error` set (matching WaitForEventAction's own PENDING
        precedent), the suspended plan's reason preserved losslessly in
        `result["wait_reason"]` and inside the serialized SupervisionState
        itself; (2) resumption remains possible once something DOES decide
        to re-invoke this Action with the persisted state (there is no
        automated waker yet - see this module's own docstring - so this
        simulates a future resumer the same way the ORIGINAL version of
        this test simulated the Step Runner's own re-tick). Statelessness
        between calls mirrors tests/test_supervisor_e2e.py's own WAIT test
        one layer down for SupervisorRuntime itself."""
        self.register_supervisor(_WaitOnceThenCompleteSupervisor())
        action = SupervisorInvocationAction()
        instance_id = uuid.uuid4()

        first_input = ActionInput(
            workflow_instance_id=instance_id,
            step_id="step-1",
            context={},
            idempotency_key="k1",
            action_config={"plan_key": _WaitOnceThenCompleteSupervisor.key},
        )
        first_output = action.execute(first_input)

        self.assertEqual(first_output.status, ActionOutcome.PENDING, "WAIT must suspend, never retry")
        self.assertIn(_STATE_KEY, first_output.result)
        self.assertIsNone(first_output.error, "PENDING must carry no error, matching WaitForEventAction's own precedent")
        self.assertIn("waiting", first_output.result["wait_reason"])
        first_state = state_from_dict(first_output.result[_STATE_KEY])
        self.assertEqual(first_state.history[-1].decision.kind, DecisionKind.WAIT, "the suspended state must record the WAIT decision")

        merged_context = {**first_input.context, **first_output.result}

        second_input = ActionInput(
            workflow_instance_id=instance_id,
            step_id="step-1",
            context=merged_context,
            idempotency_key="k1",
            action_config={"plan_key": _WaitOnceThenCompleteSupervisor.key},
        )
        second_output = action.execute(second_input)

        self.assertEqual(second_output.status, ActionOutcome.SUCCESS)
        final_state = state_from_dict(second_output.result[_STATE_KEY])
        self.assertEqual(len(final_state.history), 2)
        self.assertEqual(final_state.history[0].decision.kind, DecisionKind.WAIT)
        self.assertEqual(final_state.history[1].decision.kind, DecisionKind.COMPLETE)

        self.assertEqual(
            final_state.execution_id, first_state.execution_id, "resuming must never mint a new execution_id"
        )


if __name__ == "__main__":
    unittest.main()
