"""
local_model_policy.py - Task-based local-model selection (M8.2 addendum,
approved 2026-07-28). The single centralized place inside the AI Gateway
that decides WHICH locally-hosted model `LocalOllamaProviderClient` should
ask Ollama (or any OpenAI-compatible local server) for, based on
`GatewayRequest.capability` - a strictly provider-internal concern, never
visible to `ProviderRouter`/`RoutingDecision`. Router.py's own principle
is unextended and unchanged by this file: the router decides WHICH
provider_key to try (local/free/premium), never which model a given
provider_key uses internally - see router.py's own docstring. Model
selection has always been a per-provider concern (`default_model` is
already a per-ProviderClient property); this module only makes that
existing concern capability-aware for exactly one provider.

Two-level indirection - capability -> ordered semantic ROLE preference ->
configured model string - never capability -> model directly, and
deliberately NOT positional ("default"/"secondary") naming. A role name
describes WHAT KIND of task the model is being asked to do ("research",
"writing", and, as this table grows, "coding"/"vision"/"reasoning"/
"embeddings"...), so a future third or fourth local model slots in as a
new role without ever renaming an existing one - the exact failure mode
positional naming ("tertiary", "quaternary"...) would eventually hit.

This is the same two-level shape every other policy table in this
package already uses: `router.CAPABILITY_PROVIDER_PREFERENCE` is
capability -> ordered provider_key preference; `tiers.PROVIDER_TIER_REGISTRY`
is provider_key -> tier; `accounting`'s price table is (provider_key,
model) -> price. This is capability -> ordered semantic-role preference
-> settings attribute. Nothing here is a new pattern.

`LOCAL_MODEL_ROLES` maps a role name to a SETTINGS ATTRIBUTE NAME, not a
resolved value - `resolve_local_model()` imports `app.core.config.settings`
lazily, at call time, mirroring `router.py`'s own "testable without
pydantic_settings installed" discipline (this module itself never
imports `app.core.config` at module level, so it stays importable and
unit-testable in a bare Python environment exactly like
`capabilities.py`/`tiers.py` already are).

Extending this for the future is always exactly two additive edits, per
the CEO's own stated requirement:
  1. Add a new `LOCAL_MODEL_<NAME>_MODEL` setting to `app/core/config.py`
     (following `LOCAL_MODEL_SECONDARY_MODEL`'s own comment as the
     template).
  2. Add one `"<role_name>": "LOCAL_MODEL_<NAME>_MODEL"` entry to
     `LOCAL_MODEL_ROLES` below, then reference `"<role_name>"` in
     whichever capability's preference list in
     `CAPABILITY_LOCAL_MODEL_ROLE` should use it.
Neither edit ever touches `LocalOllamaProviderClient`, `router.py`,
`client.py`, `capabilities.py`, or any other provider client - the exact
"business logic never changes" property required.

Disclosed scope note: `CAPABILITY_LOCAL_MODEL_ROLE` includes two entries
("buyer_discovery", "crm_data_extraction") that are NOT live
`GatewayRequest.capability` traffic yet - neither `app/discovery` nor
`app/crm_automation` calls the AI Gateway today (confirmed by grep at
design time: no `AIGateway`/`GatewayRequest` usage in either package).
These are forward-looking, inert placeholders - safe to declare ahead of
use, same convention `GOOGLE_AI_STUDIO_API_KEY` already established in
this codebase (an unset/unused setting or table entry changes nothing
until something actually reads it). The two capabilities genuinely live
today are `"research_analysis"` (Research's `LLMAnalysisEngine` - see
`app/research/analysis/llm_agent.py`'s `RESEARCH_ANALYSIS_AGENT_KEY`) and
`"outreach_email_generation"` (Outreach's LLM email channel - see
`app/outreach/channels/llm_agent.py`'s `OUTREACH_EMAIL_AGENT_KEY`).
"""

# role name -> settings attribute name (never the resolved value itself -
# see module docstring for why this stays a lazy lookup). Semantic, not
# positional - see module docstring for why that distinction matters long
# term.
LOCAL_MODEL_ROLES: dict[str, str] = {
    "research": "LOCAL_MODEL_DEFAULT_MODEL",
    "writing": "LOCAL_MODEL_SECONDARY_MODEL",
}

# capability -> ordered role preference (most-preferred role first, same
# "ordered list, first configured wins" shape router.py's own
# CAPABILITY_PROVIDER_PREFERENCE already uses one level up). A capability
# absent from this dict falls back to _FALLBACK_ROLE_PREFERENCE - same
# "must always resolve to something" convention
# CAPABILITY_PROVIDER_PREFERENCE's own `_DEFAULT_CAPABILITY_KEY` entry
# already established.
#
# "outreach_email_generation" prefers "writing" (LOCAL_MODEL_SECONDARY_MODEL,
# e.g. llama3.1:8b) and falls back to "research" (LOCAL_MODEL_DEFAULT_MODEL,
# e.g. qwen3:8b) if the writing role isn't configured - this is what
# delivers "prefer llama3.1:8b, fall back to qwen3:8b if unavailable"
# without ever hardcoding either model name here.
CAPABILITY_LOCAL_MODEL_ROLE: dict[str, list[str]] = {
    "research_analysis": ["research"],
    "outreach_email_generation": ["writing", "research"],
    # Not yet live traffic - see module docstring's disclosed scope note.
    "buyer_discovery": ["research"],
    "crm_data_extraction": ["research"],
}
_FALLBACK_ROLE_PREFERENCE = ["research"]


def resolve_local_model(capability: str, *, settings_obj=None) -> str | None:
    """Walks `capability`'s role preference list (or the fallback, for an
    unlisted capability), returning the first role whose settings
    attribute is actually configured (a non-empty string) - same
    "unconfigured is normal, skip it, never an error" fail-safe
    convention `accounting.py`/`tiers.py` already use. An unrecognized
    role name in the preference list (a data bug in this table, not a
    runtime condition) is likewise just skipped, never raised - this
    function must never throw, since its one caller
    (`LocalOllamaProviderClient._resolve_model()`) already has a safe
    final fallback (`self.default_model`) it can use if this returns
    None.

    `settings_obj` is a deliberate testability seam, same convention as
    `AIGateway`'s own `provider_lookup` constructor param
    (`app.ai_gateway.client`) and `SearchService`'s own DI seam
    (`app.discovery.search_service`) - both documented there for the
    identical reason: this project's test sandbox has neither
    `pydantic_settings` nor `sqlalchemy` installed, so any test that
    imports the real `app.core.config.settings` cannot run as a "pure"
    test (see `tests/test_ai_provider_hierarchy_pure.py`'s own header
    disclosure). Passing any object with the relevant
    `LOCAL_MODEL_*_MODEL` attributes set lets
    `tests/test_local_model_policy_pure.py` exercise this function's
    real branching logic with zero third-party dependencies. Production
    code never passes this - the default (`None`) triggers the real,
    lazy `app.core.config.settings` import, unchanged from before this
    seam existed."""
    if settings_obj is None:
        from app.core.config import settings as settings_obj  # lazy - see module docstring

    for role in CAPABILITY_LOCAL_MODEL_ROLE.get(capability, _FALLBACK_ROLE_PREFERENCE):
        attr = LOCAL_MODEL_ROLES.get(role)
        if attr is None:
            continue
        value = getattr(settings_obj, attr, None)
        if value:
            return value
    return None
