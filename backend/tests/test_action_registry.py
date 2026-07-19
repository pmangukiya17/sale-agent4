"""
Pure-logic tests for app/workflow_engine/actions/registry.py - no DB, no
network. M7.1 Part 1, Phase 2.

Run standalone with:
    python -m unittest tests.test_action_registry
"""
import unittest
import uuid

from app.workflow_engine.actions.base import Action, ActionInput, ActionOutcome, ActionOutput
from app.workflow_engine.actions.registry import ACTION_REGISTRY, get_action, is_action_registered, register_action


class _FakeAction(Action):
    def execute(self, input_data: ActionInput) -> ActionOutput:
        return ActionOutput(status=ActionOutcome.SUCCESS, result={"echo": input_data.context})


class TestActionRegistry(unittest.TestCase):
    def setUp(self):
        # ACTION_REGISTRY is process-global state - snapshot and restore
        # it around every test so tests never leak registrations into
        # each other or into any other test module that imports this
        # registry.
        self._saved_registry = dict(ACTION_REGISTRY)
        ACTION_REGISTRY.clear()

    def tearDown(self):
        ACTION_REGISTRY.clear()
        ACTION_REGISTRY.update(self._saved_registry)

    def test_register_and_get_action_round_trip(self):
        action = _FakeAction()
        register_action("test.fake_action", action)

        self.assertIs(get_action("test.fake_action"), action)

    def test_is_action_registered_true_and_false(self):
        register_action("test.fake_action", _FakeAction())

        self.assertTrue(is_action_registered("test.fake_action"))
        self.assertFalse(is_action_registered("test.unregistered_action"))

    def test_get_unknown_action_raises_key_error(self):
        with self.assertRaises(KeyError):
            get_action("test.does_not_exist")

    def test_re_registering_the_same_key_raises(self):
        register_action("test.fake_action", _FakeAction())
        with self.assertRaises(KeyError):
            register_action("test.fake_action", _FakeAction())

    def test_registered_action_executes_and_returns_expected_shape(self):
        register_action("test.fake_action", _FakeAction())
        action = get_action("test.fake_action")

        result = action.execute(
            ActionInput(
                workflow_instance_id=uuid.uuid4(),
                step_id="step_1",
                context={"hello": "world"},
                idempotency_key="wf-instance:step_1",
            )
        )

        self.assertEqual(result.status, ActionOutcome.SUCCESS)
        self.assertEqual(result.result, {"echo": {"hello": "world"}})
        self.assertIsNone(result.error)


if __name__ == "__main__":
    unittest.main()
