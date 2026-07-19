"""
The engine's own built-in wait-for-event pseudo-action - M7.1 Part 1,
Phase 5. Registered under WAIT_FOR_EVENT_ACTION_KEY
("engine.wait_for_event") by
app.workflow_engine.actions.registry.ensure_builtin_actions_registered()
- called from BOTH is_action_registered() and get_action() in that same
module, so this class is guaranteed to be registered wherever the
registry is actually consulted (step_graph validation at DRAFT ->
ACTIVE activation time; real invocation by the Step Runner worker),
regardless of process import order and regardless of anything having
cleared ACTION_REGISTRY beforehand (as several of this milestone's own
tests deliberately do, for isolation, in their own setUp()). See that
function's own docstring for the full reasoning - this module itself no
longer performs any registration as an import side effect; it only
defines the class.

This is genuine self-registration by the engine, not a boundary
violation: the engine registering its own built-in action never
requires importing anything domain-specific (see actions/registry.py's
own docstring for the general rule this is a legitimate exception to -
there is no exception being made here, this action simply has no domain
dependency to begin with).

How it works, end to end, split across the two workers (see each
worker's own docstring for its half):
1. A WorkflowInstance's current step has action_key ==
   WAIT_FOR_EVENT_ACTION_KEY, action_config = {"event_type": "<...>"}.
2. The Step Runner invokes this Action. If context has no
   `_woken_by_event` marker yet, execute() returns PENDING - the Step
   Runner translates that into instance.status = WAITING, and does NOT
   advance current_step_id (the instance stays parked on this exact
   step until a matching event arrives).
3. Later, the Event Dispatcher worker finds this WAITING instance,
   matches an incoming event against this step's action_config.event_type
   (plus subject_id compatibility - see event_dispatcher_worker.py),
   writes context["_woken_by_event"] = {"event_type": ..., "payload":
   ...}, and flips status back to RUNNING.
4. The Step Runner picks the instance up again on a later tick,
   re-invokes this same Action (same step, a new attempt). This time
   execute() finds the marker, returns SUCCESS with a result that nulls
   the marker back out ("consumed and cleared" - see the class
   docstring below for exactly what "cleared" means here), and the Step
   Runner advances current_step_id via this step's transitions.success
   rule, same as it would for any other Action's SUCCESS.
"""
from app.workflow_engine.actions.base import Action, ActionInput, ActionOutcome, ActionOutput


class WaitForEventAction(Action):
    """Never touches the database, never calls out anywhere - a pure
    function of the ActionInput's own `context`. Whether an event has
    actually arrived is entirely the Event Dispatcher's job to decide
    and record (by writing the `_woken_by_event` marker); this class
    only ever reads that one reserved key.

    "Cleared" means the merged-back result sets `_woken_by_event` to
    None, not that the key is removed from the JSONB object entirely -
    the Step Runner's context merge (Part 1, Phase 5) is a plain
    shallow-merge pass-through, the same opaque mechanism every other
    Action's `result` goes through, so this class deliberately doesn't
    require the engine to grow a special "delete a key" merge rule just
    for its own reserved marker. A null value reads exactly the same as
    "absent" to every check this module (and event_dispatcher_worker.py)
    ever performs against this key.
    """

    def execute(self, input_data: ActionInput) -> ActionOutput:
        marker = input_data.context.get("_woken_by_event")
        if not marker:
            return ActionOutput(status=ActionOutcome.PENDING)

        return ActionOutput(
            status=ActionOutcome.SUCCESS,
            result={"_woken_by_event": None, "woken_by": marker},
        )
