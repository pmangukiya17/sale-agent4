"""
Provider registry: the one place a new provider plugin gets wired in.
Adding a provider is adding an import + a dict entry here - no schema
change, no change anywhere else in the pipeline.
"""
from app.discovery.providers.base import DiscoveryProvider
from app.discovery.providers.manual_csv import ManualCSVProvider

PROVIDER_REGISTRY: dict[str, type[DiscoveryProvider]] = {
    ManualCSVProvider.key: ManualCSVProvider,
}


def get_provider(provider_key: str) -> DiscoveryProvider:
    provider_cls = PROVIDER_REGISTRY.get(provider_key)
    if provider_cls is None:
        raise KeyError(f"Unknown discovery provider '{provider_key}'. Registered providers: {list(PROVIDER_REGISTRY)}")
    return provider_cls()
