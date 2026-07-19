"""
Home for Action implementations that are registered INTO the Workflow
Engine but aren't naturally owned by any single existing domain module -
M7.1 Part 2. Distinct from app/workflow_engine/actions/, which is
reserved exclusively for the engine's OWN built-in pseudo-actions (e.g.
the reserved wait-for-event action) - everything in THIS package is a
real, registered Action the Step Runner can be asked to execute for an
actual WorkflowDefinition step, the same way a future domain-owned
Action (e.g. app/delivery/actions/send_followup_action.py, self-
registering the same way, from within its own owning domain module)
would be.

Importing this package (`import app.workflow_actions`) is the one
required bootstrap step for whichever process needs these actions
available - it imports every action submodule below, each of which
self-registers into app.workflow_engine.actions.registry.ACTION_REGISTRY
idempotently as an import side effect. Two call sites need this: the
Step Runner worker's own process entrypoint (it actually EXECUTES
Actions - see step_runner_worker.py's `if __name__ == "__main__":`
block) and app/workflow_bootstrap.py (it calls activate_definition(),
which validates a step_graph's action_key references via
is_action_registered() - a built-in workflow referencing an action from
this package needs it registered before activation, not just before
execution).

This import is deliberately NEVER made from anywhere inside
app/workflow_engine/ itself - the engine must never know these actions
exist by name; it only ever calls get_action(action_key) generically.
The dependency arrow points app.workflow_actions -> app.workflow_engine
(this package freely imports the engine's Action contract/registry),
never the other way.

M7.4 addition: supervisor_invocation_action.py is the first module in
this package to ALSO import app.supervisor - a deliberate, sanctioned
second dependency edge (app.workflow_actions -> app.supervisor), added
specifically so a Workflow Action can bridge into the Supervisor /
Supervisor Runtime layer without app/workflow_engine/ itself ever
learning that layer exists, the same "domain imports engine/AI-stack,
never the reverse" shape this package already applies to
app.workflow_engine. See that module's own docstring for the full
reasoning, including the honest, disclosed gap in how it currently
resumes a suspended plan's WAIT decision.
"""
from app.workflow_actions import record_execution_action  # noqa: F401  (self-registration side effect)
from app.workflow_actions import supervisor_invocation_action  # noqa: F401  (self-registration side effect)
