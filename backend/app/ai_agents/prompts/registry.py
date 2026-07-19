"""
PROMPT_REGISTRY - M7.2. Code-based, versioned prompt template storage -
same "plain dict, updating an entry is a normal code change, not a
migration" convention as app.ai_gateway.accounting's own price table, not
a duplicate-guarded registry like ACTION_REGISTRY/AGENT_REGISTRY (a new
prompt VERSION for an existing agent_key is an expected, routine
operation, not a collision to catch).

Exists so a concrete Agent's build_context() can look up its own
system-instructions text by (agent_key, version) instead of hardcoding
prompt copy inline in the Agent class - letting a prompt be revised (a
new version registered) without redeploying the Agent's own logic,
provided the Agent reads its version via get_prompt_template() rather
than a literal string. Using this is each Agent's own choice, not
enforced by the Agent contract (base.py) - a simple Agent may still
construct its own PromptContext.system_instructions directly; nothing
about the Agent ABC requires going through this registry.

Deliberately empty and content-free in M7.2: no concrete Agent
implementation exists yet in this codebase (see app/ai_agents/__init__.py's
own scope note), so there is no real prompt copy to version. This file
ships the mechanism only, ready for the first real Agent (M7.3+) to
populate.

DB-backed prompt governance (draft/active/deprecated lifecycle, mirroring
WorkflowDefinition's own) is explicitly deferred beyond this milestone -
this code-level registry is the v1, matching the same
"defer storage until a real feature needs it" discipline used throughout
this project.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    agent_key: str
    version: int
    system_instructions: str | None = None


PROMPT_REGISTRY: dict[tuple[str, int], PromptTemplate] = {}


def register_prompt_template(template: PromptTemplate) -> None:
    PROMPT_REGISTRY[(template.agent_key, template.version)] = template


def get_prompt_template(agent_key: str, version: int) -> PromptTemplate:
    template = PROMPT_REGISTRY.get((agent_key, version))
    if template is None:
        raise KeyError(f"No prompt template registered for agent_key={agent_key!r} version={version}")
    return template


def latest_prompt_version(agent_key: str) -> int | None:
    versions = [version for (key, version) in PROMPT_REGISTRY if key == agent_key]
    return max(versions) if versions else None
