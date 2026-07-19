"""
Pure-logic tests for app/workflow_engine/definitions.py's
validate_step_graph() - no DB, no network, aside from the in-memory
Action Registry (snapshotted/restored per test, same discipline as
test_action_registry.py). M7.1 Part 1, Phase 2.

Run standalone with:
    python -m unittest tests.test_workflow_definition_validation
"""
import unittest

from app.workflow_engine.actions.base import Action, ActionInput, ActionOutcome, ActionOutput
from app.workflow_engine.actions.registry import ACTION_REGISTRY, register_action
from app.workflow_engine.definitions import validate_step_graph


class _FakeAction(Action):
    def execute(self, input_data: ActionInput) -> ActionOutput:
        return ActionOutput(status=ActionOutcome.SUCCESS)


def _valid_two_step_graph() -> dict:
    return {
        "start_step_id": "step_1",
        "steps": {
            "step_1": {
                "action_key": "test.registered_action",
                "transitions": {"success": "step_2", "failure": None},
                "max_attempts": 3,
            },
            "step_2": {
                "action_key": "test.registered_action",
                "transitions": {"success": None, "failure": None},
                "max_attempts": 1,
            },
        },
    }


class TestValidateStepGraph(unittest.TestCase):
    def setUp(self):
        self._saved_registry = dict(ACTION_REGISTRY)
        ACTION_REGISTRY.clear()
        register_action("test.registered_action", _FakeAction())

    def tearDown(self):
        ACTION_REGISTRY.clear()
        ACTION_REGISTRY.update(self._saved_registry)

    def test_valid_graph_has_no_errors(self):
        self.assertEqual(validate_step_graph(_valid_two_step_graph()), [])

    def test_non_dict_graph_is_rejected(self):
        errors = validate_step_graph("not a dict")
        self.assertTrue(errors)

    def test_missing_start_step_id_is_rejected(self):
        graph = _valid_two_step_graph()
        del graph["start_step_id"]
        errors = validate_step_graph(graph)
        self.assertTrue(any("start_step_id" in e for e in errors))

    def test_start_step_id_not_in_steps_is_rejected(self):
        graph = _valid_two_step_graph()
        graph["start_step_id"] = "does_not_exist"
        errors = validate_step_graph(graph)
        self.assertTrue(any("does_not_exist" in e for e in errors))

    def test_empty_steps_is_rejected(self):
        errors = validate_step_graph({"start_step_id": "step_1", "steps": {}})
        self.assertTrue(any("steps" in e for e in errors))

    def test_unregistered_action_key_is_rejected(self):
        graph = _valid_two_step_graph()
        graph["steps"]["step_1"]["action_key"] = "test.not_registered"
        errors = validate_step_graph(graph)
        self.assertTrue(any("test.not_registered" in e for e in errors))

    def test_missing_action_key_is_rejected(self):
        graph = _valid_two_step_graph()
        del graph["steps"]["step_1"]["action_key"]
        errors = validate_step_graph(graph)
        self.assertTrue(any("action_key" in e for e in errors))

    def test_unknown_transition_key_is_rejected(self):
        graph = _valid_two_step_graph()
        graph["steps"]["step_1"]["transitions"]["timeout"] = "step_2"
        errors = validate_step_graph(graph)
        self.assertTrue(any("timeout" in e for e in errors))

    def test_transition_to_unknown_step_is_rejected(self):
        graph = _valid_two_step_graph()
        graph["steps"]["step_1"]["transitions"]["success"] = "step_does_not_exist"
        errors = validate_step_graph(graph)
        self.assertTrue(any("step_does_not_exist" in e for e in errors))

    def test_non_positive_max_attempts_is_rejected(self):
        graph = _valid_two_step_graph()
        graph["steps"]["step_1"]["max_attempts"] = 0
        errors = validate_step_graph(graph)
        self.assertTrue(any("max_attempts" in e for e in errors))

    def test_unreachable_step_is_rejected(self):
        graph = _valid_two_step_graph()
        graph["steps"]["step_3_orphan"] = {
            "action_key": "test.registered_action",
            "transitions": {"success": None, "failure": None},
            "max_attempts": 1,
        }
        errors = validate_step_graph(graph)
        self.assertTrue(any("unreachable" in e and "step_3_orphan" in e for e in errors))

    def test_cycle_is_rejected(self):
        graph = _valid_two_step_graph()
        # step_2's success now points back at step_1 - a real cycle.
        graph["steps"]["step_2"]["transitions"]["success"] = "step_1"
        errors = validate_step_graph(graph)
        self.assertTrue(any("cycle" in e for e in errors))

    def test_self_loop_is_a_cycle(self):
        graph = {
            "start_step_id": "step_1",
            "steps": {
                "step_1": {
                    "action_key": "test.registered_action",
                    "transitions": {"success": "step_1", "failure": None},
                    "max_attempts": 1,
                }
            },
        }
        errors = validate_step_graph(graph)
        self.assertTrue(any("cycle" in e for e in errors))

    def test_single_step_terminal_graph_is_valid(self):
        graph = {
            "start_step_id": "only_step",
            "steps": {
                "only_step": {
                    "action_key": "test.registered_action",
                    "transitions": {"success": None, "failure": None},
                    "max_attempts": 1,
                }
            },
        }
        self.assertEqual(validate_step_graph(graph), [])


if __name__ == "__main__":
    unittest.main()
