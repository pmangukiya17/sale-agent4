"""
Provider registry: the one place a new provider plugin gets wired in.
Adding a provider is adding an entry to _PROVIDER_IMPORT_PATHS below (plus
a DIRECT_PROVIDER_KEYS/SEARCH_PROVIDER_KEYS classification) - no schema
change, no change anywhere else in the pipeline.

M2 Phase 2 changes:

1. Lazy import. Provider classes are now imported lazily, inside
   get_provider(), rather than at this module's own top level. Mirrors
   app.ai_gateway.client.AIGateway._resolve_provider()'s own precedent
   exactly - see that method's docstring for the full reasoning. The
   short version: BraveSearchProvider imports `httpx` at module level,
   a real third-party HTTP library this project's own authoring sandbox
   cannot install (no PyPI/network access - a disclosed, standing
   constraint). If this registry imported brave_search.py at MODULE
   level (the old, Phase 1 style, back when the only provider was the
   zero-dependency ManualCSVProvider), merely importing
   app.discovery.providers.registry - which app.discovery.pipeline
   already does unconditionally - would fail wherever httpx isn't
   installed, which would make every pure-logic Discovery test
   (dedup/normalization/validation/scoring/query_planner) collateral
   damage of a completely unrelated provider's dependency. Importing
   each provider class lazily, only at the moment get_provider()
   actually needs it, keeps this module (and therefore pipeline.py)
   importable with zero third-party dependencies beyond sqlalchemy
   itself.

2. SEARCH_PROVIDER_KEYS / DIRECT_PROVIDER_KEYS. Per
   docs/architecture/m2-discovery-provider-strategy.md Section 11.1
   (CEO-approved Search Service refinement): a query-driven ("search-
   type") provider like BraveSearchProvider is never called directly by
   app.discovery.pipeline - it's called by
   app.discovery.search_service.SearchService, which owns building a
   QueryPlan and merging per-variation results before pipeline.py ever
   sees a ProviderSearchOutcome. A row-driven ("direct") provider like
   ManualCSVProvider has no query to plan in the first place (query_spec
   IS already the complete input, a manually-provided row list) and
   stays called directly by pipeline.py exactly as it always has been -
   see that architecture doc's own explicit carve-out ("manual_csv...
   stays exactly where it is today, called directly by the Discovery
   Engine... outside the Search Service entirely").

3. iter_enabled_providers(). New - the Provider Registry's own
   "iterate active providers" requirement. A provider is "enabled" if it
   is registered here AND its own health() returns True (see
   app.discovery.providers.base.DiscoveryProvider.health()'s docstring
   for what that means per-provider) - there is no separate, redundant
   enabled/disabled boolean stored anywhere else; health() IS the single
   source of truth for "ready to use right now."
"""
import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.discovery.providers.base import DiscoveryProvider

# provider_key -> (module path, class name). Deliberately data, not
# imports - see this module's own docstring for why.
_PROVIDER_IMPORT_PATHS: dict[str, tuple[str, str]] = {
    "manual_csv": ("app.discovery.providers.manual_csv", "ManualCSVProvider"),
    "brave_search": ("app.discovery.providers.brave_search", "BraveSearchProvider"),
}

# Row-driven: called directly by app.discovery.pipeline, exactly as
# every provider was before Phase 2.
DIRECT_PROVIDER_KEYS: frozenset[str] = frozenset({"manual_csv"})

# Query-driven: called only via app.discovery.search_service.SearchService
# - see this module's own docstring, point 2.
SEARCH_PROVIDER_KEYS: frozenset[str] = frozenset({"brave_search"})


def get_provider(provider_key: str) -> "DiscoveryProvider":
    entry = _PROVIDER_IMPORT_PATHS.get(provider_key)
    if entry is None:
        raise KeyError(
            f"Unknown discovery provider '{provider_key}'. Registered providers: {list(_PROVIDER_IMPORT_PATHS)}"
        )
    module_path, class_name = entry
    module = importlib.import_module(module_path)
    provider_cls = getattr(module, class_name)
    return provider_cls()


def is_search_provider(provider_key: str) -> bool:
    """True if this provider_key must be routed through
    app.discovery.search_service.SearchService rather than called
    directly. Raises no KeyError for an unknown key (returns False) -
    app.discovery.pipeline's own existing get_provider() call already
    surfaces "unknown provider" as a KeyError at the point it actually
    tries to use one; this function is purely a routing decision, not a
    second place that validates a provider_key exists."""
    return provider_key in SEARCH_PROVIDER_KEYS


def iter_enabled_providers() -> list[str]:
    """Every registered provider_key whose own health() currently
    returns True - the Provider Registry's "iterate active providers"
    requirement. Never raises: a provider whose class fails to import
    (e.g. a genuinely broken plugin) is treated as not-enabled rather
    than crashing the caller, since this is meant for
    diagnostic/admin-facing use (e.g. "which providers can I pick for a
    new DiscoverySearch"), not a hot path any job execution depends on."""
    enabled: list[str] = []
    for provider_key in _PROVIDER_IMPORT_PATHS:
        try:
            provider = get_provider(provider_key)
            if provider.health():
                enabled.append(provider_key)
        except Exception:  # noqa: BLE001 - deliberately broad, see docstring
            continue
    return enabled
