"""
Action Registry - code-based, mirroring the SPIRIT of this codebase's
existing plugin-registry pattern (PROVIDER_REGISTRY/
CREDENTIAL_STORE_REGISTRY/REPLY_CLASSIFIER_REGISTRY): adding an action is
a code change, never a migration. The MECHANISM necessarily differs from
those precedents in one way: this file must NEVER import a concrete
domain Action implementation AT MODULE LEVEL - doing so would violate
the engine's hard "zero import dependency on any domain package"
boundary (see app/workflow_engine/__init__.py's own docstring).
PROVIDER_REGISTRY safely imports GmailProvider/OutlookProvider because
those live within the SAME delivery domain the registry itself belongs
to; the Workflow Engine's Action Registry is different by design -
domain modules register THEMSELVES into it, so the import arrow always
points from domain to engine, never the reverse.

Domain modules call register_action() from their own module (not solved
by Part 1 of this milestone - no domain action exists yet; the pilot
action arrives in a later phase).

The engine's own built-in actions (currently just the reserved
wait-for-event pseudo-action, Part 1 Phase 5 - see actions/
wait_for_event.py) are different from a domain action in one important
way: the engine must be able to guarantee they are ALWAYS present in
ACTION_REGISTRY, in every process and at every call site that reads
from this registry - unlike a domain action, nothing external is ever
responsible for registering them. Guaranteeing that ONLY via a
module-import side effect (e.g. "some module transitively imports
actions/wait_for_event.py, which registers itself at import time") is
fragile: it silently stops holding the moment anything clears or
otherwise mutates ACTION_REGISTRY after that one-time import already
ran (module imports are cached per-process, so the registration code
only ever executes once) - exactly what happened in this project's own
test suite, where several tests' own setUp() intentionally clears
ACTION_REGISTRY for isolation, wiping out the built-in registration
along with everything else, with nothing re-establishing it before
validate_step_graph()/get_action() ran again.

ensure_builtin_actions_registered() below is the actual fix: it is
called from BOTH is_action_registered() and get_action() - the two
functions every other caller in this codebase (validate_step_graph() at
validation time; the Step Runner worker at execution time) already goes
through - so the guarantee "the engine's own built-in actions are
registered" holds unconditionally, regardless of what has happened to
ACTION_REGISTRY before, with no separate initialization step any caller
needs to remember or any import order any caller needs to get right.
This directly satisfies validate_step_graph()'s own uniform "is this
action_key registered" check for EVERY action_key without ever
special-casing the built-in one - the check itself never changes; what
changes is that the registry now guarantees its own correctness before
answering.

The import of actions/wait_for_event.py inside
ensure_builtin_actions_registered() is deliberately a FUNCTION-LOCAL
import, not a module-level one: wait_for_event.py imports
register_action/is_action_registered FROM this module, so a module-level
import here would be circular. A function-local import breaks the cycle
- by the time this function is actually CALLED, both modules have
already finished loading, so the lazy import just returns (or, on the
very first call in this process, populates) the already-consistent
module object.
"""
from app.workflow_engine.actions.base import Action

ACTION_REGISTRY: dict[str, Action] = {}


def register_action(action_key: str, action: Action) -> None:
    """Registers one Action INSTANCE (not a class) under `action_key`.
    Unlike PROVIDER_REGISTRY (which stores classes and instantiates
    fresh per call), Actions are expected to be stateless thin adapters,
    so one shared instance per key is sufficient and avoids
    re-constructing an adapter on every step invocation.

    Re-registering an already-registered key raises - a deliberate "no
    silent overwrite" guard. Two different modules accidentally claiming
    the same action_key is exactly the kind of bug the engine's own
    opacity to action_key strings makes otherwise hard to catch, so this
    fails loudly instead of letting the second registration silently win.
    This guard is for genuine caller-vs-caller collisions only - it is
    deliberately NOT what ensure_builtin_actions_registered() below uses
    to (re-)establish the engine's own built-in actions, since that is
    expected to run more than once per process and must be a true no-op
    when the action is already present, not an error.
    """
    if action_key in ACTION_REGISTRY:
        raise KeyError(f"Action '{action_key}' is already registered")
    ACTION_REGISTRY[action_key] = action


def ensure_builtin_actions_registered() -> None:
    """Idempotent, side-effect-only, safe to call any number of times
    from anywhere - guarantees every action the ENGINE ITSELF owns
    (currently just WAIT_FOR_EVENT_ACTION_KEY) is present in
    ACTION_REGISTRY, independent of whatever has happened to the
    registry before this call. Writes to ACTION_REGISTRY directly
    (bypassing register_action()'s duplicate-key guard on purpose - see
    that function's own docstring) rather than calling
    is_action_registered() itself, so this function can safely be called
    FROM is_action_registered() below without recursing."""
    from app.workflow_engine.actions.base import WAIT_FOR_EVENT_ACTION_KEY
    from app.workflow_engine.actions.wait_for_event import WaitForEventAction

    if WAIT_FOR_EVENT_ACTION_KEY not in ACTION_REGISTRY:
        ACTION_REGISTRY[WAIT_FOR_EVENT_ACTION_KEY] = WaitForEventAction()


def get_action(action_key: str) -> Action:
    ensure_builtin_actions_registered()
    action = ACTION_REGISTRY.get(action_key)
    if action is None:
        raise KeyError(f"Unknown action '{action_key}'. Registered actions: {sorted(ACTION_REGISTRY)}")
    return action


def is_action_registered(action_key: str) -> bool:
    """Existence check, used by
    app.workflow_engine.definitions.validate_step_graph() (Part 1, Phase
    2) to catch a typo'd action_key at DRAFT -> ACTIVE validation time,
    without needing to actually invoke anything. Calls
    ensure_builtin_actions_registered() first (see that function's own
    docstring for why this - not a separate initialization step - is
    what guarantees the engine's own built-in actions are always
    available wherever a step_graph is validated)."""
    ensure_builtin_actions_registered()
    return action_key in ACTION_REGISTRY
