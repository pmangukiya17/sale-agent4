"""
Process entrypoint for the Step Runner worker - M7.1 Part 2. Composition-
root code, not engine code: deliberately the ONE place in this codebase
allowed to import both app.workflow_engine.step_runner_worker (the
engine) AND app.workflow_actions (a concrete, registered Action
implementation), because it lives OUTSIDE app/workflow_engine/ entirely.

Why this file exists rather than just running
`python -m app.workflow_engine.step_runner_worker` directly (which is
what Part 1 did, before any real Action existed to register): the
engine must never import a concrete Action-providing package by name -
see app/workflow_actions/__init__.py's own docstring, and
step_runner_worker.py's own `if __name__ == "__main__":` block, which
explicitly does NOT perform this import for exactly this reason. But
SOMETHING has to, before the worker process can execute anything beyond
the engine's own built-in wait-for-event pseudo-action - ACTION_REGISTRY
is in-memory and per-process, so this has to happen once, early, in
whichever process actually runs the Step Runner. This script is that
"something": a thin composition root, not part of the engine's own
importable module graph, matching the exact same reasoning
app/main.py's own bootstrap_builtin_workflows() -> app.workflow_bootstrap
-> app.workflow_actions import chain already uses for the backend
process.

docker-compose.yml's workflow_step_runner_worker service invokes this
script (`python -m app.run_step_runner_worker`), not
app.workflow_engine.step_runner_worker directly.
"""
import logging

import app.workflow_actions  # noqa: F401  (registers every action this package owns, before the worker loop starts)
from app.workflow_engine import step_runner_worker

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    step_runner_worker.run_forever()
