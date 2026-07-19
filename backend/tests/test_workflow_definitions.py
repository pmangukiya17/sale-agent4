"""
Real, DB-backed tests of app/workflow_engine/definitions.py (the
Compatibility Policy enforced as code) and the workflow_definitions
table's own constraints. M7.1 Part 1, Phase 2.

Requires a real database connection (SessionLocal) - run inside the
backend container against the real Postgres; not runnable in a sandbox
with no Docker/Postgres access.

Run standalone with:
    python -m unittest tests.test_workflow_definitions
"""
import unittest
import uuid

from sqlalchemy.exc import IntegrityError

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.db.session import SessionLocal
from app.models.company_profile import CompanyProfile
from app.models.enums import UserRole, WorkflowDefinitionStatus
from app.models.user import User
from app.models.workflow_definition import WorkflowDefinition
from app.workflow_engine.actions.base import Action, ActionInput, ActionOutcome, ActionOutput
from app.workflow_engine.actions.registry import ACTION_REGISTRY, register_action
from app.workflow_engine.definitions import (
    activate_definition,
    create_draft_definition,
    deprecate_definition,
    resolve_active_definition,
    update_draft_definition,
)


class _FakeAction(Action):
    def execute(self, input_data: ActionInput) -> ActionOutput:
        return ActionOutput(status=ActionOutcome.SUCCESS)


def _valid_graph() -> dict:
    return {
        "start_step_id": "step_1",
        "steps": {
            "step_1": {
                "action_key": "test.registered_action",
                "transitions": {"success": None, "failure": None},
                "max_attempts": 1,
            }
        },
    }


class TestWorkflowDefinitions(unittest.TestCase):
    def setUp(self):
        self._saved_registry = dict(ACTION_REGISTRY)
        ACTION_REGISTRY.clear()
        register_action("test.registered_action", _FakeAction())

        self.db = SessionLocal()

        self.user = User(email=f"m7.1-definitions-test-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)
        self.db.add(self.user)
        self.db.flush()

        self.company_profile = CompanyProfile(owner_user_id=self.user.id, name="M7.1 Definitions Test Co", is_default=False)
        self.db.add(self.company_profile)
        self.db.commit()

        self._test_key = f"test-workflow-{uuid.uuid4()}"

    def tearDown(self):
        self.db.rollback()
        ACTION_REGISTRY.clear()
        ACTION_REGISTRY.update(self._saved_registry)

        self.db.query(WorkflowDefinition).filter(WorkflowDefinition.key.like("test-workflow-%")).delete(synchronize_session=False)
        self.db.commit()
        self.db.query(CompanyProfile).filter(CompanyProfile.id == self.company_profile.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()

    # --- create_draft_definition -----------------------------------------
    def test_create_draft_definition_starts_at_version_1_and_status_draft(self):
        definition = create_draft_definition(
            self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=_valid_graph()
        )
        self.assertEqual(definition.version, 1)
        self.assertEqual(definition.status, WorkflowDefinitionStatus.DRAFT)
        self.assertIsNone(definition.company_profile_id)

    def test_create_draft_definition_increments_version_for_same_key(self):
        first = create_draft_definition(self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=_valid_graph())
        activate_definition(self.db, first)
        second = create_draft_definition(self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=_valid_graph())

        self.assertEqual(second.version, 2)
        self.assertEqual(second.status, WorkflowDefinitionStatus.DRAFT)

    def test_create_draft_definition_does_not_validate_the_graph(self):
        # A DRAFT is allowed to be incomplete/invalid while being edited -
        # validation is a hard gate only at activate_definition() time.
        broken_graph = {"start_step_id": "missing", "steps": {}}
        definition = create_draft_definition(self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=broken_graph)
        self.assertEqual(definition.status, WorkflowDefinitionStatus.DRAFT)

    # --- resolve_active_definition -----------------------------------------
    def test_resolve_active_definition_returns_none_when_no_active_version(self):
        create_draft_definition(self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=_valid_graph())
        self.assertIsNone(resolve_active_definition(self.db, key=self._test_key))

    def test_resolve_active_definition_returns_the_active_version(self):
        definition = create_draft_definition(self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=_valid_graph())
        activate_definition(self.db, definition)

        resolved = resolve_active_definition(self.db, key=self._test_key)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, definition.id)
        self.assertEqual(resolved.version, 1)

    # --- activate_definition -------------------------------------------------
    def test_activate_definition_demotes_previous_active_to_deprecated(self):
        v1 = create_draft_definition(self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=_valid_graph())
        activate_definition(self.db, v1)

        v2 = create_draft_definition(self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=_valid_graph())
        activate_definition(self.db, v2)

        self.db.refresh(v1)
        self.assertEqual(v1.status, WorkflowDefinitionStatus.DEPRECATED)
        self.assertEqual(v2.status, WorkflowDefinitionStatus.ACTIVE)

        # v1's own content survives, untouched - deprecation never
        # deletes or mutates anything but status.
        self.assertEqual(v1.trigger_event_type, "test.trigger")
        self.assertEqual(v1.step_graph, _valid_graph())

        resolved = resolve_active_definition(self.db, key=self._test_key)
        self.assertEqual(resolved.id, v2.id)

    def test_activate_definition_fails_if_not_draft(self):
        definition = create_draft_definition(self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=_valid_graph())
        activate_definition(self.db, definition)

        with self.assertRaises(ValueError):
            activate_definition(self.db, definition)

    def test_activate_definition_fails_on_invalid_step_graph(self):
        broken_graph = {"start_step_id": "missing", "steps": {}}
        definition = create_draft_definition(self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=broken_graph)

        with self.assertRaises(ValueError):
            activate_definition(self.db, definition)

        self.db.refresh(definition)
        self.assertEqual(definition.status, WorkflowDefinitionStatus.DRAFT, "a failed activation must not change status")

    # --- update_draft_definition -------------------------------------------
    def test_update_draft_definition_succeeds_while_draft(self):
        definition = create_draft_definition(self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=_valid_graph())
        updated = update_draft_definition(self.db, definition, trigger_event_type="test.trigger.v2")
        self.assertEqual(updated.trigger_event_type, "test.trigger.v2")

    def test_update_draft_definition_fails_once_active(self):
        definition = create_draft_definition(self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=_valid_graph())
        activate_definition(self.db, definition)

        with self.assertRaises(ValueError):
            update_draft_definition(self.db, definition, trigger_event_type="should.not.apply")

    def test_update_draft_definition_fails_once_deprecated(self):
        definition = create_draft_definition(self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=_valid_graph())
        activate_definition(self.db, definition)
        deprecate_definition(self.db, definition)

        with self.assertRaises(ValueError):
            update_draft_definition(self.db, definition, trigger_event_type="should.not.apply")

    # --- deprecate_definition -----------------------------------------------
    def test_deprecate_definition_leaves_key_with_zero_active_versions(self):
        definition = create_draft_definition(self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=_valid_graph())
        activate_definition(self.db, definition)
        deprecate_definition(self.db, definition)

        self.assertIsNone(resolve_active_definition(self.db, key=self._test_key))

    def test_deprecate_definition_fails_if_not_active(self):
        definition = create_draft_definition(self.db, key=self._test_key, trigger_event_type="test.trigger", step_graph=_valid_graph())
        with self.assertRaises(ValueError):
            deprecate_definition(self.db, definition)

    # --- database-level constraint (defense in depth, not just service-layer) ---
    def test_database_rejects_a_second_active_row_for_the_same_key(self):
        first = WorkflowDefinition(
            key=self._test_key,
            version=1,
            status=WorkflowDefinitionStatus.ACTIVE,
            trigger_event_type="test.trigger",
            step_graph=_valid_graph(),
        )
        self.db.add(first)
        self.db.commit()

        second = WorkflowDefinition(
            key=self._test_key,
            version=2,
            status=WorkflowDefinitionStatus.ACTIVE,
            trigger_event_type="test.trigger",
            step_graph=_valid_graph(),
        )
        self.db.add(second)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_database_rejects_duplicate_version_for_the_same_key(self):
        first = WorkflowDefinition(
            key=self._test_key,
            version=1,
            status=WorkflowDefinitionStatus.DRAFT,
            trigger_event_type="test.trigger",
            step_graph=_valid_graph(),
        )
        self.db.add(first)
        self.db.commit()

        duplicate_version = WorkflowDefinition(
            key=self._test_key,
            version=1,
            status=WorkflowDefinitionStatus.DRAFT,
            trigger_event_type="test.trigger",
            step_graph=_valid_graph(),
        )
        self.db.add(duplicate_version)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()


if __name__ == "__main__":
    unittest.main()
