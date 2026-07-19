"""
ExecutionPolicy - M7.2, added per the user's refinement #2. Carries every
provider/model-shaped knob an Agent must never hardcode: provider
capability, model, temperature, token limits, timeout, budget, and
structured-output requirements. AgentRuntime resolves one of these per
Agent invocation (see app.ai_agents.execution_policy.resolve_execution_policy)
and passes it into PromptBuilder.build() - an Agent never constructs or
even sees an ExecutionPolicy instance (see app.ai_agents.base.Agent's own
docstring).

Deliberately defined HERE, in app.prompt_builder, rather than in
app.ai_agents where it is resolved. Layer dependencies in this stack only
ever point downward (Agent Runtime -> Prompt Builder -> AI Gateway -> the
provider router/clients) - PromptBuilder.build()'s own signature takes an
ExecutionPolicy as a parameter, so if the type were defined up in
app.ai_agents instead, this package would need an upward import to type
it, breaking that rule. Owning the type at the layer that actually reads
every one of its fields (PromptBuilder.build() is the one place that
turns provider_capability/model/temperature/... into a GatewayRequest)
keeps the dependency arrow pointing the same direction as everywhere
else: app.ai_agents.execution_policy imports ExecutionPolicy from here,
not the other way around - exactly how it already imports GatewayRequest
from app.ai_gateway.request one layer further down.
"""
from dataclasses import dataclass

from app.ai_gateway.request import ResponseFormat


@dataclass(frozen=True)
class ExecutionPolicy:
    """`provider_capability` becomes GatewayRequest.capability - the
    ROUTING key (see app.ai_gateway.router's own docstring for why that
    stays a separate vocabulary from agent_key/provider name).
    `model`/`temperature`/`max_tokens`/`timeout_seconds`/`response_format`
    map directly onto the GatewayRequest fields of the same name.
    `budget_usd` maps onto GatewayRequest.budget_usd, enforced softly by
    AIGateway.complete() (see app.ai_gateway.client's own docstring for
    why hard enforcement is out of scope this milestone).

    All fields but `provider_capability` are optional - `None` means "let
    the provider layer decide" (e.g. model=None lets a ProviderClient
    fall back to its own settings.<PROVIDER>_DEFAULT_MODEL), never a
    silently-guessed value invented by this dataclass itself.
    """

    provider_capability: str
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None
    budget_usd: float | None = None
    response_format: ResponseFormat | None = None
