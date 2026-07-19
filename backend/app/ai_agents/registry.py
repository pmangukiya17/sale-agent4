"""
AGENT_REGISTRY - M7.2, self-registration, mirroring
app.workflow_engine.actions.registry.ACTION_REGISTRY exactly (same
reasoning: this file must never import a concrete Agent implementation
at module level, so the import arrow always points from a concrete
Agent's own module into this registry, never the reverse). No
ensure_builtin-style bootstrap exists here, unlike ACTION_REGISTRY's own
ensure_builtin_actions_registered() - the AI Agent Runtime owns no
built-in agents of its own the way the Workflow Engine owns its
wait-for-event pseudo-action; every entry in AGENT_REGISTRY will always
be a real, domain-registered concrete Agent.
"""
from app.ai_agents.base import Agent

AGENT_REGISTRY: dict[str, Agent] = {}


def register_agent(agent_key: str, agent: Agent) -> None:
    """Registers one Agent INSTANCE under `agent_key`. Raises on a
    duplicate key - same "no silent overwrite" guard as
    register_action() one layer down, for the same reason: two Agents
    accidentally claiming the same key is a bug worth failing loudly on,
    not silently resolving in registration order."""
    if agent_key in AGENT_REGISTRY:
        raise KeyError(f"Agent '{agent_key}' is already registered")
    AGENT_REGISTRY[agent_key] = agent


def get_agent(agent_key: str) -> Agent:
    agent = AGENT_REGISTRY.get(agent_key)
    if agent is None:
        raise KeyError(f"Unknown agent '{agent_key}'. Registered agents: {sorted(AGENT_REGISTRY)}")
    return agent


def is_agent_registered(agent_key: str) -> bool:
    return agent_key in AGENT_REGISTRY
