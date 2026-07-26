"""
ProviderCapabilities - M-AIGW-1 (Provider-Neutral AI Gateway foundation).
See docs/architecture/provider-neutral-ai-gateway-plan.md Sections 6/7 for
the full design discussion and the CEO decisions this module implements.

Purpose: let the Gateway route/validate against what a provider can
actually DO, rather than ever branching on its name. Confirmed via
`grep -rn 'provider_key ==\\|== "claude"\\|== "openai"\\|== "gemini"' app/`
at design time that no such branching exists yet - this module is
genuinely preventive, closing off that failure mode before a sixth or
seventh provider tempts someone into writing it, not a fix for an
existing violation.

Deliberately pure - no `settings` import, no sqlalchemy, fully testable
in this project's sandbox without pydantic_settings (same discipline
`confidence.py`/`tiers.py` already established). The two places that
actually need live data (`PROVIDER_CLIENT_REGISTRY` for provider-level
declarations) do their own lazy import at the call site, exactly like
`router.py::ProviderRouter.select()` already does for `settings` - this
module itself never imports either.

Two-level granularity (CEO decision, Section 7): protocol-level booleans
(`structured_output`, `tool_calling`, `streaming`, `vision`, `embeddings`)
are a fixed fact about a provider's wire-format/SDK integration - declared
once as a `ClassVar[ProviderCapabilities]` on each concrete `ProviderClient`
(see providers/base.py). `max_context_tokens`/`max_output_tokens`/
`reasoning_support` genuinely vary PER MODEL (the same provider_key can be
configured with a small or a large model) - `_CAPABILITY_OVERRIDES` below
keys these by `(provider_key, model)`, mirroring `accounting.py`'s own
`_MODEL_PRICE_OVERRIDES_USD_PER_1K` keying exactly (M-AIGW-4's per-model
override table - see that module's own docstring for its two-level
provider-default/per-model-override split). `resolve_capabilities()` starts
from the provider-level default and merges in an override's fields when
the caller knows the concrete model; when `model` is None (every existing
caller today - see this module's own limitation note below),
`resolve_capabilities()` can only ever return the provider-level default.

Disclosed limitation: `GatewayRequest.model` is None for every real
caller in this codebase today (every existing ExecutionPolicy lets the
provider layer pick its own configured default model - see
`prompt_builder/policy.py`'s own docstring). This means the per-model
override table exists and is fully queryable, but its practical effect on
today's routing decisions is currently limited to callers that start
setting an explicit `model` - not a bug, just an honest statement of
scope for this pass.

`streaming` is declared False for every provider as of this module's
introduction, regardless of the underlying SDK's real capability -
`AIGateway.stream()` itself raises NotImplementedError unconditionally
(see client.py's own docstring), so declaring streaming=True for any
provider right now would describe a capability the Gateway cannot yet
deliver. Revisit provider declarations once stream() is implemented.

`vision`/`embeddings` are declared (correctly, per each provider's real
SDK capability) but functionally inert this pass - `GatewayRequest.messages`
has no image-content shape, and embeddings are not a chat-completion call
at all (a different response shape entirely). Declared now for future-
readiness, per CEO decision; wiring up real vision/embeddings request
support is explicitly out of scope for M-AIGW-1.
"""
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class ProviderCapabilities:
    """Missing/unknown defaults to the conservative direction (False/None)
    - same 'fail safe, not fail permissive' precedent
    `tiers.tier_of()` already established for an unclassified provider
    defaulting to PREMIUM. A provider that hasn't declared a capability is
    treated as NOT having it, never assumed capable."""

    structured_output: bool = False
    tool_calling: bool = False
    streaming: bool = False
    vision: bool = False
    embeddings: bool = False
    max_context_tokens: int | None = None
    max_output_tokens: int | None = None
    reasoning_support: bool = False


@dataclass(frozen=True)
class RequiredCapabilities:
    """What a single GatewayRequest actually needs, derived by
    `derive_required_capabilities()` below - never constructed directly by
    a caller. Only the three capabilities with a real, live routing effect
    this pass (see module docstring re: vision/embeddings/streaming being
    declared-but-inert, and max_context_tokens/max_output_tokens being
    informational rather than a pass/fail gate this milestone)."""

    structured_output: bool = False
    tool_calling: bool = False
    reasoning_support: bool = False

    def any_required(self) -> bool:
        return self.structured_output or self.tool_calling or self.reasoning_support


def derive_required_capabilities(request) -> RequiredCapabilities:
    """`request` is a GatewayRequest - typed loosely (not imported here) to
    avoid a hard dependency edge; every field this function reads
    (`response_format`, `tools`, `requires_deep_reasoning`) is a plain
    dataclass field, so a structurally-compatible fake works fine too
    (see tests/test_ai_gateway_capabilities_pure.py for exactly that).

    Maps GatewayRequest's existing implicit capability requirements onto
    RequiredCapabilities: `response_format.type == JSON` wants
    `structured_output`; a non-empty `tools` list wants `tool_calling`;
    `requires_deep_reasoning=True` wants `reasoning_support`."""
    from app.ai_gateway.request import ResponseFormatType

    response_format = getattr(request, "response_format", None)
    structured_output = bool(response_format and response_format.type == ResponseFormatType.JSON)
    tool_calling = bool(getattr(request, "tools", None))
    reasoning_support = bool(getattr(request, "requires_deep_reasoning", False))
    return RequiredCapabilities(
        structured_output=structured_output, tool_calling=tool_calling, reasoning_support=reasoning_support
    )


def satisfies(capabilities: ProviderCapabilities, required: RequiredCapabilities) -> bool:
    if required.structured_output and not capabilities.structured_output:
        return False
    if required.tool_calling and not capabilities.tool_calling:
        return False
    if required.reasoning_support and not capabilities.reasoning_support:
        return False
    return True


# (provider_key, model) -> partial field overrides, merged on top of that
# provider's own ClassVar default. Mirrors accounting.py's
# _MODEL_PRICE_OVERRIDES_USD_PER_1K keying exactly (M-AIGW-4's per-model
# override table) - see module docstring for why
# this granularity is necessary for max_context_tokens/max_output_tokens/
# reasoning_support specifically. Empty by default; populated via
# register_capability_override() as real per-model facts are confirmed,
# same "extend as real usage accumulates" discipline accounting.py's own
# price table already uses.
_CAPABILITY_OVERRIDES: dict[tuple[str, str], dict] = {}


def register_capability_override(provider_key: str, model: str, **fields) -> None:
    """Adds/overwrites one (provider_key, model) capability override -
    same "re-registering is a normal operation, not a bug" convention as
    accounting.register_price(). `fields` must be a subset of
    ProviderCapabilities' own field names - validated via
    dataclasses.replace() raising TypeError on an unknown kwarg, not
    silently ignored."""
    _CAPABILITY_OVERRIDES[(provider_key, model)] = fields


def resolve_capabilities(
    provider_key: str, model: str | None, *, provider_level: dict[str, ProviderCapabilities]
) -> ProviderCapabilities:
    """`provider_level` is the caller-supplied {provider_key: ProviderCapabilities}
    map (in production, built from PROVIDER_CLIENT_REGISTRY's own
    `.capabilities` ClassVars - see router.py's lazy import of this at the
    one real call site). A provider_key missing from `provider_level`
    resolves to the all-conservative ProviderCapabilities() default - the
    same safe-fail direction as an unclassified tier."""
    base = provider_level.get(provider_key, ProviderCapabilities())
    if model is None:
        return base
    override = _CAPABILITY_OVERRIDES.get((provider_key, model))
    if not override:
        return base
    return replace(base, **override)


def filter_capable(
    provider_keys: list[str],
    required: RequiredCapabilities,
    *,
    model: str | None,
    provider_level: dict[str, ProviderCapabilities],
) -> tuple[list[str], list[str]]:
    """Splits an ordered provider_key list into (capable, excluded),
    preserving relative order within each group - same shape/intent as
    tiers.partition(). Returns (provider_keys, []) unchanged, without
    resolving any capability, when `required.any_required()` is False -
    the fast path that keeps every existing caller (none of which set
    `requires_deep_reasoning`, and whose `response_format`/`tools` never
    exceed what every real provider already declares - see this module's
    provisional capability table in the plan doc) byte-for-byte
    unaffected."""
    if not required.any_required():
        return list(provider_keys), []
    capable: list[str] = []
    excluded: list[str] = []
    for key in provider_keys:
        caps = resolve_capabilities(key, model, provider_level=provider_level)
        if satisfies(caps, required):
            capable.append(key)
        else:
            excluded.append(key)
    return capable, excluded
