"""
SUPERVISOR_REGISTRY - M7.3, VERSIONED as of M7.4. Self-registration, same
"registry file never imports a concrete implementation at module level"
discipline as AGENT_REGISTRY/ACTION_REGISTRY.

M7.4 change (a breaking change to this file's own API, not an additive
one - see below for why that's safe): M7.3 shipped SUPERVISOR_REGISTRY as
`dict[str, Supervisor]` - one implementation per plan_key, no versioning
concept at all. M7.4's own architecture review (the "Supervisor plan
lifecycle" clarification) settled on a DIFFERENT model than
WorkflowDefinition's own DB-governed DRAFT/ACTIVE/DEPRECATED lifecycle:
Supervisor plan versions are CODE, not DATA (a new version only ever
ships via a deploy), so the registry itself just needs to hold multiple
versions of the same plan_key side by side, plus a lightweight code-level
"which version do NEW plan starts get" mapping - not a DB-backed
activation workflow. SUPERVISOR_REGISTRY is now keyed by (plan_key,
version) so a SupervisionState pinned to `plan_version=3` (see
app.supervisor.base's own docstring on why that field exists) always
resolves to the exact version-3 implementation it started on, even after
a version-4 deploy - mirroring WorkflowDefinition's own "already-running
instances stay pinned to whatever version they started on" rule, just
enforced in code rather than a database row's status column.

This IS a breaking change to register_supervisor()/get_supervisor()'s own
signatures (both now require an explicit `version: int`), not an
additive parallel API - a genuinely additive change is impossible here:
M7.3's registry shape (`dict[str, Supervisor]`, one slot per plan_key)
cannot represent "more than one version of the same plan_key" at all: the
underlying dict itself has to change shape. This is deliberately judged
SAFE despite being a signature break, for a reason worth stating
explicitly rather than assuming: M7.3 shipped ZERO concrete Supervisor
implementations and nothing outside this package's own test file
(tests/test_supervisor_e2e.py, updated in this same milestone) ever
called register_supervisor()/get_supervisor() directly - there is no real
production caller this change could silently break. Changing an API
surface with zero production callers is a materially different, lower-
risk action than changing one with real callers (contrast
AgentRuntime.run(), M7.3's own AgentExecutionResult addition, which WAS
kept byte-identical specifically because M7.2 already had conceptual
callers depending on its exact shape).
"""
from app.supervisor.base import Supervisor

SUPERVISOR_REGISTRY: dict[tuple[str, int], Supervisor] = {}

# Code-level "which version do brand-new plan starts get" mapping - the
# lightweight equivalent of WorkflowDefinition's DB-governed ACTIVE
# status, but resolved entirely in-process (no table, no migration).
# Deliberately separate from SUPERVISOR_REGISTRY itself: a version can be
# registered (available to resume an already-suspended plan pinned to it)
# without being the default for NEW starts - the same "old code stays
# runnable for whatever is still pinned to it, even after a newer version
# becomes the default for new work" property WorkflowDefinition's own
# DEPRECATED status gives a retiring version, achieved here without any
# governance lifecycle at all.
DEFAULT_SUPERVISOR_VERSION: dict[str, int] = {}


def register_supervisor(plan_key: str, version: int, supervisor: Supervisor) -> None:
    """Raises on a duplicate (plan_key, version) pair - same "no silent
    overwrite" guard as register_agent()/register_action(). Registering
    a NEW version of an already-registered plan_key is expected and
    normal (that's the whole point of versioning); it is only the exact
    same (plan_key, version) pair twice that is rejected."""
    key = (plan_key, version)
    if key in SUPERVISOR_REGISTRY:
        raise KeyError(f"Supervisor plan '{plan_key}' version {version} is already registered")
    SUPERVISOR_REGISTRY[key] = supervisor


def get_supervisor(plan_key: str, version: int) -> Supervisor:
    supervisor = SUPERVISOR_REGISTRY.get((plan_key, version))
    if supervisor is None:
        raise KeyError(
            f"Unknown Supervisor plan '{plan_key}' version {version}. "
            f"Registered (plan_key, version) pairs: {sorted(SUPERVISOR_REGISTRY)}"
        )
    return supervisor


def is_supervisor_registered(plan_key: str, version: int) -> bool:
    return (plan_key, version) in SUPERVISOR_REGISTRY


def register_default_version(plan_key: str, version: int) -> None:
    """Marks `version` as the version a brand-new SupervisionState.start()
    for `plan_key` should be pinned to (see
    app.supervisor.runtime.SupervisorRuntime.start_plan(), the only
    caller of resolve_default_version() below). Deliberately validates
    that (plan_key, version) is ALREADY registered first - setting a
    default that points at nothing would silently break every future new
    plan start with a confusing KeyError three calls later inside
    get_supervisor(), instead of failing loudly, immediately, at the
    misconfiguration's own source."""
    if not is_supervisor_registered(plan_key, version):
        raise KeyError(
            f"cannot set version {version} as the default for Supervisor plan '{plan_key}': "
            "that version is not registered yet - call register_supervisor() first"
        )
    DEFAULT_SUPERVISOR_VERSION[plan_key] = version


def resolve_default_version(plan_key: str) -> int:
    version = DEFAULT_SUPERVISOR_VERSION.get(plan_key)
    if version is None:
        raise KeyError(
            f"no default version is set for Supervisor plan '{plan_key}' - "
            "call register_default_version() before starting a new plan execution"
        )
    return version
