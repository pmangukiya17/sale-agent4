"""
DiscoveryProviderService - CEO-directed architectural refinement to the
Phase 2 UX work: the API layer does not depend on
app.discovery.providers.registry directly. Instead:

    API route  ->  DiscoveryProviderService  ->  registry.py

registry.py remains exactly what it always was - the wiring table
app.discovery.pipeline/app.discovery.search_service actually use to
RESOLVE and EXECUTE a provider during a real Discovery job. That
contract is untouched by this module. This service exists for a
DIFFERENT question a route now needs answered - "what providers exist,
and are they usable right now" - which is a read-only, presentation-
adjacent concern, not a job-execution concern. Keeping that question
behind its own thin service, rather than having the route call
registry.py's own functions directly, means future, genuinely new
concerns that are NOT about executing a search - aggregating health
across providers, formatting capability discovery for a UI, provider
ordering, licensing/feature-flag gating, per-workspace enable/disable,
provider usage statistics - all have one obvious place to grow into,
without ever leaking API-response-shaped concerns into registry.py
itself, and without a future route reaching past this service into
registry internals the way this one almost did.

Deliberately thin today: every method here is a direct delegation to
registry.py, no new logic, no new state. That is the point of adding
this boundary now rather than later - it's nearly free to insert while
only one route needs it, and it would be real, disruptive rework to
retrofit once several routes/tests depended on registry.py directly.
"""
from dataclasses import dataclass
from typing import Any

from app.discovery.providers.registry import get_provider, list_registered_provider_keys


@dataclass(frozen=True)
class DiscoveryProviderInfo:
    """Plain data, not a Pydantic model - this service returns domain
    data; translating it into an HTTP response shape
    (DiscoveryProviderRead) is the route's own job, same separation
    app.opportunities.service/app.discovery.pipeline already use
    (return a plain/ORM value, let the route layer apply
    response_model)."""

    key: str
    name: str
    enabled: bool
    capabilities: dict[str, Any]


class DiscoveryProviderService:
    def list_providers(self) -> list[DiscoveryProviderInfo]:
        """Every registered provider, with its current display name,
        health, and capabilities - never raises. A provider whose own
        class fails to import or construct (a genuinely broken plugin,
        or a missing third-party dependency in a non-Docker dev
        environment) is reported as present-but-unhealthy rather than
        propagating an exception - the API route calling this should
        never have to handle a provider-construction failure as a
        special case; "not enabled" already covers it correctly from a
        caller's perspective."""
        results: list[DiscoveryProviderInfo] = []
        for key in list_registered_provider_keys():
            try:
                provider = get_provider(key)
                results.append(
                    DiscoveryProviderInfo(
                        key=key,
                        name=provider.provider_name(),
                        enabled=provider.health(),
                        capabilities=provider.capabilities(),
                    )
                )
            except Exception:  # noqa: BLE001 - deliberately broad, see docstring
                results.append(DiscoveryProviderInfo(key=key, name=key, enabled=False, capabilities={}))
        return results
