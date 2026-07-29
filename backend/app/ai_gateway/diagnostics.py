"""
diagnostics.py - M8.3 Step 6 (AI Gateway Management & Control, Gateway
Diagnostics). Pure aggregation layer - same "pure core, impure shell"
split `routing_simulator.py`/`local_model_policy.resolve_local_model()`
already established for this milestone: no `settings`/sqlalchemy import at
module level, genuinely unit-testable in this project's sandbox with no
pydantic_settings/sqlalchemy installed.

Deliberately builds NOTHING new about routing/capability/configuration
truth. Every finding here is derived entirely from facts the caller
(`ui_query.get_diagnostics()`) already computed via EXISTING functions -
`ProviderClient.is_configured()`, `ui_query.get_provider_config()`,
`tiers.tier_of()`, `ui_query.list_routing_decisions()` (the exact same
live routing preview the Routing page already shows), plus one grouped
`AIRequestLog` read for observed failures. This module's only job is to
look at those already-true facts TOGETHER and decide what's worth telling
an admin about, with what severity and what actionable next step - per the
CEO's Step 6 requirement to "build diagnostics from existing gateway
telemetry rather than duplicating logic," this is explicitly NOT a second
routing/capability engine, and it never re-derives a routing decision
itself (see `RoutingOutcomeInput` below - it's handed a decision that was
already made, not asked to make one).

Severity vocabulary (the CEO's "clearly separate warnings from errors"
requirement): "error" (something is currently broken - a capability
literally cannot be routed, or an AI_MODE has no eligible provider at all),
"warning" (a real risk or silent gap - a provider is enabled but
misconfigured, requests have been failing) and "info" (worth knowing, not
a problem - a provider was intentionally disabled, a capability is
expected to wait for premium approval under current settings). Kept as a
plain `str`, not a real enum, so this module stays free of any
framework/pydantic import - `schemas/ai_gateway.py`'s own `Literal` is
where that gets narrowed for the API response.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderHealthInput:
    """One provider's already-resolved health facts - `enabled` is the
    admin's own on/off flag (`ProviderConfigRead.enabled`, defaults to
    True with no saved row); `configured` is the REAL effective state
    (`ProviderClient.is_configured()`, which already accounts for
    credentials/base URL AND the enabled flag together) - both are kept as
    separate fields specifically so this module can tell "disabled on
    purpose" apart from "enabled but broken," which a single boolean
    could not."""

    provider_key: str
    label: str
    tier: str
    enabled: bool
    configured: bool


@dataclass(frozen=True)
class RoutingOutcomeInput:
    """One capability's CURRENT live routing outcome - lifted directly
    from `ui_query.list_routing_decisions()`'s own `RoutingDecisionRead`
    (`outcome` is one of "success" | "waiting" | "failed", identical
    vocabulary), never recomputed here."""

    capability: str
    feature_label: str
    outcome: str


@dataclass(frozen=True)
class FailureSummaryInput:
    """One (provider_key, error_type) pair's observed failure count over
    the caller's own lookback window (`ui_query.get_diagnostics()` uses
    the last 24 hours, matching every other "requests_today"/"activity"
    window already established in this package) - PremiumApprovalRequiredError
    rows are excluded by the caller, since that's an expected pause state
    (see `RoutingOutcomeInput`'s own "waiting" outcome), never a failure."""

    provider_key: str | None
    label: str
    error_type: str
    count: int


@dataclass(frozen=True)
class DiagnosticFinding:
    category: str  # "provider_health" | "configuration" | "routing"
    severity: str  # "error" | "warning" | "info"
    title: str
    detail: str
    recommendation: str
    provider_key: str | None = None
    capability: str | None = None


# A recent-failure count at or above this threshold escalates from
# "warning" to "error" - repeated failures within one day are a stronger
# signal than a single transient blip, but this module has no opinion on
# WHY a provider is failing (network hiccup vs. a genuinely revoked key
# look identical from AIRequestLog's own recorded facts) - just how often.
_REPEATED_FAILURE_ERROR_THRESHOLD = 5


def build_diagnostics(
    *,
    providers: list[ProviderHealthInput],
    ai_mode: str,
    require_premium_approval: bool,
    routing_outcomes: list[RoutingOutcomeInput],
    recent_failures: list[FailureSummaryInput],
) -> list[DiagnosticFinding]:
    """Pure aggregation - deterministic given its inputs, no I/O, no
    randomness, no clock read (unlike `ui_query.get_diagnostics()`, which
    stamps `generated_at` itself). Order is deliberate and stable:
    provider health first (the most fundamental "can this even work"
    layer), then AI-mode/provider-interaction configuration issues, then
    live routing outcomes, then observed historical failures - roughly
    "structural" to "operational" to "historical," so an admin reading
    top-to-bottom sees causes before symptoms."""
    findings: list[DiagnosticFinding] = []

    # --- Provider health ---
    for p in providers:
        if not p.enabled:
            findings.append(
                DiagnosticFinding(
                    category="provider_health",
                    severity="info",
                    title=f"{p.label} is disabled",
                    detail=(
                        f"An admin has explicitly disabled {p.label}; it will never be used for routing "
                        "regardless of whether credentials are configured for it."
                    ),
                    recommendation=f"Re-enable {p.label} in Provider Management if this was unintentional.",
                    provider_key=p.provider_key,
                )
            )
        elif not p.configured:
            findings.append(
                DiagnosticFinding(
                    category="provider_health",
                    severity="warning",
                    title=f"{p.label} is enabled but not configured",
                    detail=(
                        f"{p.label} is enabled but has no valid credentials/base URL - the router will silently "
                        "skip it at request time and fall through to the next candidate."
                    ),
                    recommendation=(
                        f"Add credentials for {p.label} in Provider Management, or disable it there to make the "
                        "gap explicit rather than silent."
                    ),
                    provider_key=p.provider_key,
                )
            )

    # --- Configuration-level checks (AI mode / provider-tier interaction) ---
    configured_by_tier: dict[str, list[str]] = {"local": [], "free": [], "premium": []}
    for p in providers:
        if p.enabled and p.configured:
            configured_by_tier.setdefault(p.tier, []).append(p.provider_key)

    if ai_mode == "local_only" and not configured_by_tier.get("local"):
        findings.append(
            DiagnosticFinding(
                category="configuration",
                severity="error",
                title="AI mode is 'local_only' but no local provider is configured",
                detail=(
                    "AI_MODE=local_only means every capability routes exclusively to a local-tier provider - "
                    "none is currently both enabled and configured, so no request can succeed."
                ),
                recommendation="Configure a local provider (e.g. Ollama) in Provider Management, or change AI_MODE.",
            )
        )
    if ai_mode == "premium_only" and not configured_by_tier.get("premium"):
        findings.append(
            DiagnosticFinding(
                category="configuration",
                severity="error",
                title="AI mode is 'premium_only' but no premium provider is configured",
                detail=(
                    "AI_MODE=premium_only means every capability routes exclusively to a premium-tier provider - "
                    "none is currently both enabled and configured, so no request can succeed."
                ),
                recommendation="Configure a premium provider (e.g. Claude, OpenAI, Gemini) in Provider Management, or change AI_MODE.",
            )
        )
    if require_premium_approval and ai_mode != "local_only" and not configured_by_tier.get("premium"):
        findings.append(
            DiagnosticFinding(
                category="configuration",
                severity="warning",
                title="Premium approval is required, but no premium provider is configured",
                detail=(
                    "AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL is on, but there is no configured premium provider to "
                    "approve into - a request that exhausts local/free tiers will fail outright rather than pause "
                    "for approval."
                ),
                recommendation=(
                    "Configure at least one premium provider, or leave this as-is if premium is intentionally "
                    "unavailable for this deployment."
                ),
            )
        )

    # --- Live routing outcomes (reuses list_routing_decisions()'s own preview, never recomputed) ---
    for r in routing_outcomes:
        if r.outcome == "failed":
            findings.append(
                DiagnosticFinding(
                    category="routing",
                    severity="error",
                    title=f"'{r.feature_label}' cannot currently be routed",
                    detail=(
                        f"No configured provider is available to serve the '{r.feature_label}' capability under "
                        "the current AI mode and provider configuration - the next real request for it will fail."
                    ),
                    recommendation="Configure at least one candidate provider for this capability, or review its provider preference order in Settings.",
                    capability=r.capability,
                )
            )
        elif r.outcome == "waiting":
            findings.append(
                DiagnosticFinding(
                    category="routing",
                    severity="info",
                    title=f"'{r.feature_label}' will require premium approval",
                    detail=(
                        f"Local/free tier candidates are currently exhausted for '{r.feature_label}'; the next "
                        "request will pause for an explicit premium approval rather than complete automatically."
                    ),
                    recommendation="This is expected behavior under the current settings - no action needed unless the approval step itself is undesired.",
                    capability=r.capability,
                )
            )

    # --- Observed historical failures (what actually happened, not a hypothetical) ---
    for f in recent_failures:
        severity = "error" if f.count >= _REPEATED_FAILURE_ERROR_THRESHOLD else "warning"
        findings.append(
            DiagnosticFinding(
                category="routing",
                severity=severity,
                title=f"{f.label} failed {f.count} time{'s' if f.count != 1 else ''} in the last 24 hours",
                detail=f"Recent AI Gateway requests to {f.label} failed with '{f.error_type}'.",
                recommendation=f"Check {f.label}'s credentials/connectivity in Provider Management, or review recent Activity for this provider.",
                provider_key=f.provider_key,
            )
        )

    return findings
