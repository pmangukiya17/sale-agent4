"""
PromptContext - M7.2. The one input shape every Agent.build_context()
implementation produces (see app.ai_agents.base.Agent), and the one input
PromptBuilder.build() consumes alongside an ExecutionPolicy.

Deliberately NOT a rigid dataclass with one named field per business
input the user listed (Company Profile, ICP, Buyer Persona, Knowledge
Base, CRM Context, Previous Emails, Conversation History, RAG Results).
A fixed schema would need to change - and every existing Agent's
build_context() would need to change with it - every time a new context
type is added, which contradicts the whole point of this refinement
("keeps agents focused on business logic instead of prompt
construction"). Instead: `business_context` is a fully opaque dict, keyed
however the calling Agent and PromptBuilder's own rendering logic agree
on (see builder.py's own docstring for the v1 rendering convention this
project starts with). This is the same "opaque bag, not rigid schema"
discipline already used for ActionInput.context/AgentInput.context/
Event.payload throughout this codebase - PromptContext is not a new
pattern, it's this project's existing pattern applied one layer further
up the stack.

`system_instructions`/`user_instructions` stay as distinct, named,
optional strings (not folded into business_context) because every Agent
needs to express these two things, and they map onto a near-universal
concept every provider's chat-completion API already has a slot for
(system role / first user-role message) - unlike the business_context
entries, which are provider-agnostic AND agent-specific.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PromptContext:
    system_instructions: str | None = None
    user_instructions: str | None = None
    business_context: dict = field(default_factory=dict)
