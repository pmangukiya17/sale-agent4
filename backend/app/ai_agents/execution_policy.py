"""
Execution Policy resolution - M7.2, added per the user's refinement #2.
The ExecutionPolicy TYPE itself is defined one layer down, in
app.prompt_builder.policy (see that module's own docstring for why -
short version: the dependency arrow in this stack only ever points
downward, and PromptBuilder.build() is the layer that actually reads
every field). This module owns the RESOLUTION side: which policy a given
agent_key gets, decided by AgentRuntime.run() (runtime.py), never by the
Agent itself (an Agent's build_context()/interpret() methods have no
signature path to an ExecutionPolicy at all - see base.py).

EXECUTION_POLICY_REGISTRY is a plain code-level dict, same "adding an
entry is a code change, not a migration" convention as
app.ai_gateway.router.ROUTING_POLICY and app.ai_gateway.accounting's own
price table - not a database table, for the same reason ROUTING_POLICY
isn't one: no feature yet needs a runtime-editable policy (e.g. a future
admin UI for "which model does the research agent use"), and adding one
speculatively ahead of that need would be exactly the anticipatory
schema/storage this project's own discipline avoids.
"""
from app.prompt_builder.policy import ExecutionPolicy

# Matches app.ai_gateway.router.ROUTING_POLICY's own "default" capability
# key - an agent with no specific entry below routes through the same
# single-provider, no-fallback default the Gateway's own routing policy
# already defines for "default".
DEFAULT_EXECUTION_POLICY = ExecutionPolicy(provider_capability="default")

EXECUTION_POLICY_REGISTRY: dict[str, ExecutionPolicy] = {}


def register_execution_policy(agent_key: str, policy: ExecutionPolicy) -> None:
    """Raises on a duplicate agent_key - same "no silent overwrite" guard
    as register_agent()/register_action(), for the same reason: two call
    sites disagreeing about one agent's policy is a bug worth catching
    loudly, not silently resolving by import order."""
    if agent_key in EXECUTION_POLICY_REGISTRY:
        raise KeyError(f"Execution policy for agent '{agent_key}' is already registered")
    EXECUTION_POLICY_REGISTRY[agent_key] = policy


def resolve_execution_policy(agent_key: str) -> ExecutionPolicy:
    """Never raises - an agent with no explicitly registered policy gets
    DEFAULT_EXECUTION_POLICY, so AgentRuntime.run() never fails an
    invocation merely because nobody has tuned that agent's policy yet."""
    return EXECUTION_POLICY_REGISTRY.get(agent_key, DEFAULT_EXECUTION_POLICY)
