"""
Real, DB-backed tests of app/workflow_engine/step_runner_worker.py -
M7.1 Part 1, Phase 5. Covers: the success path (with and without a next
step), a definitive FAILURE following transitions.failure regardless of
remaining attempts, RETRY-then-succeed (attempt_number increments,
instance stays on the same step in between), retry exhaustion following
transitions.failure, PENDING -> WAITING (the built-in wait-for-event
pseudo-action's own round trip through both workers), and claim/
stale-claim reclaim behavior.

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_step_runner_worker
"""
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.models.company_profile import CompanyProfile
from app.models.enums import UserRole, WorkflowInstanceStatus, WorkflowStepInvocationStatus
from app.models.event_consumption import EventConsumption
from app.models.user import User
from app.models.workflow_event import Event
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step_invocation import WorkflowStepInvocation
from app.supervisor.base import ResumeTrigger, ResumeTriggerType, Supervisor, SupervisorDecision
from app.supervisor.registry import DEFAULT_SUPERVISOR_VERSION, SUPERVISOR_REGISTRY, register_default_version, register_supervisor
from app.workflow_actions.supervisor_invocation_action import SUPERVISOR_INVOCATION_ACTION_KEY, SupervisorInvocationAction
from app.workflow_engine import event_dispatcher_worker, step_runner_worker
from app.workflow_engine.actions.base import WAIT_FOR_EVENT_ACTION_KEY, Action, ActionInput, ActionOutcome, ActionOutput
from app.workflow_engine.actions.registry import ACTION_REGISTRY, register_action
from app.workflow_engine.definitions import activate_definition, create_draft_definition
from app.workflow_engine.events import publish_event
from tests.event_backbone_cleanup import delete_events_and_dependents


def _now():
    return datetime.now(timezone.utc)


class _ScriptedAction(Action):
    """Returns one ActionOutput per call, in order, from a fixed script -
    lets a test dictate the exact outcome sequence a real Action would
    only produce nondeterministically (a live provider, an LLM, etc)."""

    def __init__(self, outputs: list[ActionOutput]):
        self._outputs = list(outputs)
        self.calls: list[ActionInput] = []

    def execute(self, input_data: ActionInput) -> ActionOutput:
        self.calls.append(input_data)
        return self._outputs[len(self.calls) - 1]


class _RaisingAction(Action):
    def execute(self, input_data: ActionInput) -> ActionOutput:
        raise RuntimeError("boom")


class _WaitImmediatelySupervisor(Supervisor):
    """M7.4 (post-review) regression fixture: a Supervisor plan whose
    very first decide_next() call suspends via WAIT, used to prove
    SupervisorInvocationAction's WAIT -> ActionOutcome.PENDING correction
    holds all the way through a REAL step_runner_worker.process_instance()
    call against a real WorkflowInstance/WorkflowStepInvocation - not just
    against the local test doubles tests/test_supervisor_invocation_action_e2e.py
    already covers. `key` is set per-instance (not a ClassVar literal)
    since this file gives every test its own randomized
    self._test_key_prefix and a Supervisor plan_key needs the same
    per-test uniqueness discipline the WorkflowDefinition keys already
    have."""

    allowed_agent_keys = frozenset()

    def __init__(self, key: str):
        self.key = key

    def decide_next(self, state):
        return SupervisorDecision.wait(
            reason="waiting on a condition this regression test never resolves, by design",
            resume_trigger=ResumeTrigger(type=ResumeTriggerType.TIME, payload={"resume_at": "2099-01-01T00:00:00+00:00"}),
        )


def _graph(
    *,
    action_key: str,
    max_attempts: int = 1,
    on_success: str | None = None,
    on_failure: str | None = None,
    extra_steps: dict | None = None,
    action_config: dict | None = None,
) -> dict:
    step_1: dict = {
        "action_key": action_key,
        "transitions": {"success": on_success, "failure": on_failure},
        "max_attempts": max_attempts,
    }
    if action_config is not None:
        step_1["action_config"] = action_config
    steps = {"step_1": step_1}
    if extra_steps:
        steps.update(extra_steps)
    return {"start_step_id": "step_1", "steps": steps}


class TestStepRunnerWorker(unittest.TestCase):
    def setUp(self):
        self._saved_registry = dict(ACTION_REGISTRY)
        ACTION_REGISTRY.clear()
        # Deliberately NOT re-registering the built-in wait-for-event action
        # here - is_action_registered()/get_action() (actions/registry.py)
        # now guarantee its presence themselves via
        # ensure_builtin_actions_registered(), regardless of ACTION_REGISTRY
        # having just been cleared above. Leaving this test to rely on that
        # real mechanism, rather than re-registering it manually here too, is
        # what actually exercises the fix.

        self.db = SessionLocal()

        self.user = User(email=f"m7.1-step-runner-test-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M7.1 Step Runner Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.commit()

        self._test_key_prefix = f"test-step-runner-{uuid.uuid4()}"

    def tearDown(self):
        self.db.rollback()
        ACTION_REGISTRY.clear()
        ACTION_REGISTRY.update(self._saved_registry)

        # EventConsumption rows must be deleted BEFORE Event/WorkflowInstance
        # - event_consumptions.event_id is ondelete="RESTRICT" (deliberately).
        # Only one test in this class publishes an Event
        # (test_full_wait_for_event_round_trip_across_both_workers, via the
        # Event Dispatcher's own run_one_tick), producing a RESUMED_INSTANCE
        # row - but deleting it explicitly here, by both event_id and
        # workflow_instance_id membership, keeps this teardown correct
        # regardless of which outcome a future test in this class produces,
        # matching test_event_dispatcher_worker.py's own teardown exactly.
        event_ids = select(Event.id).where(Event.company_profile_id == self.company_profile.id)
        instance_ids = select(WorkflowInstance.id).where(WorkflowInstance.company_profile_id == self.company_profile.id)
        self.db.query(EventConsumption).filter(
            or_(EventConsumption.event_id.in_(event_ids), EventConsumption.workflow_instance_id.in_(instance_ids))
        ).delete(synchronize_session=False)
        self.db.commit()

        self.db.query(WorkflowStepInvocation).filter(
            WorkflowStepInvocation.workflow_instance_id.in_(instance_ids)
        ).delete(synchronize_session=False)
        self.db.commit()
        self.db.query(WorkflowInstance).filter(WorkflowInstance.company_profile_id == self.company_profile.id).delete(
            synchronize_session=False
        )
        self.db.commit()

        # Generalized fix (CEO review, 2026-07-28 - see
        # test_research_workflow_e2e.py's own tearDown for the full
        # writeup): NotificationDispatch/Notification are intentionally
        # independent, RESTRICT-FK'd consumers of Event, and this
        # project's real, always-on notification worker can insert one
        # referencing this test's own Events at any time - delete the
        # complete dependent set before the Event delete itself.
        delete_events_and_dependents(self.db, company_profile_id=self.company_profile.id)

        from app.models.workflow_definition import WorkflowDefinition

        self.db.query(WorkflowDefinition).filter(WorkflowDefinition.key.like(f"{self._test_key_prefix}%")).delete(
            synchronize_session=False
        )
        self.db.commit()
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    def _activated_definition(self, key_suffix: str, *, step_graph: dict):
        draft = create_draft_definition(
            self.db, key=f"{self._test_key_prefix}-{key_suffix}", trigger_event_type=f"test.trigger.{key_suffix}", step_graph=step_graph
        )
        return activate_definition(self.db, draft)

    def _instance(self, definition, *, status=WorkflowInstanceStatus.RUNNING, current_step_id="step_1", context=None) -> WorkflowInstance:
        instance = WorkflowInstance(
            workflow_definition_id=definition.id,
            version=definition.version,
            company_profile_id=self.company_profile.id,
            status=status,
            current_step_id=current_step_id,
            context=context or {},
        )
        self.db.add(instance)
        self.db.commit()
        return instance

    # --- success path ------------------------------------------------------
    def test_success_with_no_next_step_completes_instance(self):
        register_action("test.success_terminal", _ScriptedAction([ActionOutput(status=ActionOutcome.SUCCESS, result={"done": True})]))
        definition = self._activated_definition("success-terminal", step_graph=_graph(action_key="test.success_terminal"))
        instance = self._instance(definition)

        step_runner_worker.process_instance(self.db, instance)

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.COMPLETED)
        self.assertIsNotNone(instance.completed_at)
        self.assertTrue(instance.context.get("done"))
        self.assertIsNone(instance.claimed_by)

        invocation = self.db.query(WorkflowStepInvocation).filter(WorkflowStepInvocation.workflow_instance_id == instance.id).one()
        self.assertEqual(invocation.status, WorkflowStepInvocationStatus.SUCCEEDED)
        self.assertEqual(invocation.attempt_number, 1)

    def test_success_with_next_step_advances_and_stays_running(self):
        register_action("test.success_advance", _ScriptedAction([ActionOutput(status=ActionOutcome.SUCCESS)]))
        register_action("test.step_two_noop", _ScriptedAction([ActionOutput(status=ActionOutcome.SUCCESS)]))
        definition = self._activated_definition(
            "success-advance",
            step_graph=_graph(
                action_key="test.success_advance",
                on_success="step_2",
                extra_steps={"step_2": {"action_key": "test.step_two_noop", "transitions": {"success": None, "failure": None}, "max_attempts": 1}},
            ),
        )
        instance = self._instance(definition)

        step_runner_worker.process_instance(self.db, instance)

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.RUNNING)
        self.assertEqual(instance.current_step_id, "step_2")
        self.assertIsNone(instance.completed_at)

    # --- definitive failure --------------------------------------------------
    def test_failure_follows_failure_transition_regardless_of_attempts_remaining(self):
        register_action("test.always_fails", _ScriptedAction([ActionOutput(status=ActionOutcome.FAILURE, error="nope")]))
        definition = self._activated_definition(
            "failure-immediate", step_graph=_graph(action_key="test.always_fails", max_attempts=5, on_failure=None)
        )
        instance = self._instance(definition)

        step_runner_worker.process_instance(self.db, instance)

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.FAILED, "FAILURE must go straight to the failure transition, ignoring max_attempts")
        invocation = self.db.query(WorkflowStepInvocation).filter(WorkflowStepInvocation.workflow_instance_id == instance.id).one()
        self.assertEqual(invocation.status, WorkflowStepInvocationStatus.FAILED)
        self.assertEqual(invocation.error, "nope")

    def test_raising_action_is_treated_as_failure(self):
        register_action("test.raises", _RaisingAction())
        definition = self._activated_definition("raises", step_graph=_graph(action_key="test.raises", on_failure=None))
        instance = self._instance(definition)

        step_runner_worker.process_instance(self.db, instance)

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.FAILED)
        invocation = self.db.query(WorkflowStepInvocation).filter(WorkflowStepInvocation.workflow_instance_id == instance.id).one()
        self.assertEqual(invocation.status, WorkflowStepInvocationStatus.FAILED)
        self.assertIn("boom", invocation.error)

    # --- retry ---------------------------------------------------------------
    def test_retry_then_succeed_increments_attempt_number_and_stays_on_same_step(self):
        action = _ScriptedAction(
            [ActionOutput(status=ActionOutcome.RETRY, error="try again"), ActionOutput(status=ActionOutcome.SUCCESS, result={"ok": True})]
        )
        register_action("test.retry_then_succeed", action)
        definition = self._activated_definition("retry-then-succeed", step_graph=_graph(action_key="test.retry_then_succeed", max_attempts=3))
        instance = self._instance(definition)

        step_runner_worker.process_instance(self.db, instance)
        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.RUNNING)
        self.assertEqual(instance.current_step_id, "step_1", "a RETRY within max_attempts must stay on the same step")

        step_runner_worker.process_instance(self.db, instance)
        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.COMPLETED)

        invocations = (
            self.db.query(WorkflowStepInvocation)
            .filter(WorkflowStepInvocation.workflow_instance_id == instance.id)
            .order_by(WorkflowStepInvocation.attempt_number.asc())
            .all()
        )
        self.assertEqual([i.attempt_number for i in invocations], [1, 2])
        self.assertEqual(invocations[0].status, WorkflowStepInvocationStatus.FAILED)
        self.assertEqual(invocations[1].status, WorkflowStepInvocationStatus.SUCCEEDED)

    def test_retry_exhaustion_follows_failure_transition(self):
        action = _ScriptedAction([ActionOutput(status=ActionOutcome.RETRY, error="try again")] * 2)
        register_action("test.retry_exhausted", action)
        definition = self._activated_definition("retry-exhausted", step_graph=_graph(action_key="test.retry_exhausted", max_attempts=2, on_failure=None))
        instance = self._instance(definition)

        step_runner_worker.process_instance(self.db, instance)
        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.RUNNING, "attempt 1 of 2 must still retry")

        step_runner_worker.process_instance(self.db, instance)
        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.FAILED, "attempt 2 of 2 exhausts retries and must follow the failure transition")

    # --- PENDING -> WAITING, and the full wait-for-event round trip ----------
    def test_pending_outcome_transitions_instance_to_waiting(self):
        definition = self._activated_definition(
            "wait-basic",
            step_graph=_graph(action_key=WAIT_FOR_EVENT_ACTION_KEY, on_success=None, action_config={"event_type": "test.resume.basic"}),
        )

        instance = self._instance(definition)
        step_runner_worker.process_instance(self.db, instance)

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.WAITING)
        self.assertEqual(instance.current_step_id, "step_1")

        invocation = self.db.query(WorkflowStepInvocation).filter(WorkflowStepInvocation.workflow_instance_id == instance.id).one()
        self.assertEqual(invocation.status, WorkflowStepInvocationStatus.PENDING)

    def test_full_wait_for_event_round_trip_across_both_workers(self):
        """The built-in wait-for-event pseudo-action's whole lifecycle:
        Step Runner sees PENDING -> WAITING; Event Dispatcher resumes it
        on a matching event -> RUNNING with the _woken_by_event marker;
        Step Runner's next pass consumes the marker -> SUCCESS -> next
        step. Exercises both Phase 4 and Phase 5 together end to end."""
        definition = self._activated_definition(
            "wait-round-trip",
            step_graph=_graph(
                action_key=WAIT_FOR_EVENT_ACTION_KEY, on_success=None, action_config={"event_type": "test.resume.round_trip"}
            ),
        )

        instance = self._instance(definition)

        # 1. Step Runner: no marker yet -> WAITING.
        step_runner_worker.process_instance(self.db, instance)
        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.WAITING)

        # 2. Event Dispatcher: a matching event resumes it -> RUNNING + marker.
        publish_event(
            self.db, event_type="test.resume.round_trip", company_profile_id=self.company_profile.id, source="tests", payload={"x": 1}
        )
        self.db.commit()
        event_dispatcher_worker.run_one_tick()

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.RUNNING)
        self.assertIn("_woken_by_event", instance.context)

        # 3. Step Runner: marker present -> SUCCESS, terminal (on_success=None).
        step_runner_worker.process_instance(self.db, instance)
        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.COMPLETED)
        self.assertIsNone(instance.context.get("_woken_by_event"), "the marker must be consumed/cleared, not left set")

    # --- M7.4 (post-review): Supervisor WAIT must suspend like PENDING, --
    # --- never retry -----------------------------------------------------
    def test_supervisor_wait_suspends_without_incrementing_attempts(self):
        """Regression for the WAIT-semantics correction: a Supervisor
        plan's WAIT decision must produce EXACTLY the same real-database
        shape as the engine's own built-in wait-for-event PENDING outcome
        (see test_pending_outcome_transitions_instance_to_waiting above) -
        WorkflowInstanceStatus.WAITING, current_step_id unchanged, and
        - the specific regression this test locks in - exactly ONE
        WorkflowStepInvocation row (attempt_number == 1, status PENDING),
        never a second attempt, because SupervisorInvocationAction now
        returns ActionOutcome.PENDING for WAIT, not ActionOutcome.RETRY.
        Also confirms the serialized SupervisionState survives the round
        trip through the real context JSONB column, and that a WAITING
        instance is excluded from the Step Runner's own claim query - i.e.
        genuinely out of the attempt-consuming pool, not merely reporting
        PENDING while secretly still eligible for another tick."""
        register_action(SUPERVISOR_INVOCATION_ACTION_KEY, SupervisorInvocationAction())

        plan_key = f"{self._test_key_prefix}-wait-plan"
        supervisor = _WaitImmediatelySupervisor(plan_key)
        register_supervisor(plan_key, 1, supervisor)
        self.addCleanup(SUPERVISOR_REGISTRY.pop, (plan_key, 1), None)
        self.addCleanup(DEFAULT_SUPERVISOR_VERSION.pop, plan_key, None)
        register_default_version(plan_key, 1)

        definition = self._activated_definition(
            "supervisor-wait",
            step_graph=_graph(
                action_key=SUPERVISOR_INVOCATION_ACTION_KEY,
                max_attempts=5,
                on_success=None,
                action_config={"plan_key": plan_key},
            ),
        )
        instance = self._instance(definition)

        step_runner_worker.process_instance(self.db, instance)

        self.db.refresh(instance)
        self.assertEqual(instance.status, WorkflowInstanceStatus.WAITING, "WAIT must be a real suspension, not a retry loop")
        self.assertEqual(instance.current_step_id, "step_1", "WAIT must not advance the step")
        self.assertIsNone(instance.claimed_by, "a WAITING instance's claim must still be released, same as any other outcome")

        self.assertIn("_supervision_state", instance.context, "the suspended plan's state must persist into the real context column")
        suspended_history = instance.context["_supervision_state"]["history"]
        self.assertEqual(suspended_history[-1]["decision"]["kind"], "wait")

        invocations = self.db.query(WorkflowStepInvocation).filter(WorkflowStepInvocation.workflow_instance_id == instance.id).all()
        self.assertEqual(len(invocations), 1, "a WAIT suspension must record exactly one attempt, never a retry loop")
        self.assertEqual(invocations[0].attempt_number, 1)
        self.assertEqual(invocations[0].status, WorkflowStepInvocationStatus.PENDING)

        # A WAITING instance must be excluded from the claim query itself -
        # genuinely out of the pool that would ever consume another
        # attempt, not merely reporting PENDING while still claimable.
        claimed = step_runner_worker.claim_next_batch(self.db, 10, _now())
        self.db.commit()
        self.assertNotIn(instance.id, [i.id for i in claimed], "a WAITING instance must not be reclaimed for another attempt")

    # --- claim / stale-claim reclaim -----------------------------------------
    def test_claim_next_batch_only_claims_unclaimed_running_instances(self):
        register_action("test.claim_noop", _ScriptedAction([ActionOutput(status=ActionOutcome.SUCCESS)]))
        definition = self._activated_definition("claim-basic", step_graph=_graph(action_key="test.claim_noop"))
        instance = self._instance(definition)

        now = _now()
        claimed = step_runner_worker.claim_next_batch(self.db, 10, now)
        self.db.commit()
        self.assertEqual([i.id for i in claimed], [instance.id])

        self.db.refresh(instance)
        self.assertIsNotNone(instance.claimed_at)

        second_claim = step_runner_worker.claim_next_batch(self.db, 10, now)
        self.db.commit()
        self.assertEqual(second_claim, [], "an already (freshly) claimed instance must not be claimed again")

    def test_stale_claim_is_reclaimed(self):
        register_action("test.claim_stale", _ScriptedAction([ActionOutput(status=ActionOutcome.SUCCESS)]))
        definition = self._activated_definition("claim-stale", step_graph=_graph(action_key="test.claim_stale"))
        instance = self._instance(definition)

        instance.claimed_by = "some-other-dead-worker"
        instance.claimed_at = _now() - timedelta(minutes=999)
        self.db.commit()

        claimed = step_runner_worker.claim_next_batch(self.db, 10, _now())
        self.db.commit()
        self.assertEqual([i.id for i in claimed], [instance.id], "a stale claim must be reclaimable by a fresh claim pass")


if __name__ == "__main__":
    unittest.main()
