"""
Provider registry: the one place a new research provider plugin gets
wired in - exact mirror of Discovery's registry.py. Adding a provider is
adding an import + a dict entry here - no schema change, no change
anywhere else in the pipeline.
"""
from app.research.providers.base import ResearchProvider
from app.research.providers.manual_document import ManualDocumentProvider

PROVIDER_REGISTRY: dict[str, type[ResearchProvider]] = {
    ManualDocumentProvider.key: ManualDocumentProvider,
}


def get_provider(provider_key: str) -> ResearchProvider:
    provider_cls = PROVIDER_REGISTRY.get(provider_key)
    if provider_cls is None:
        raise KeyError(f"Unknown research provider '{provider_key}'. Registered providers: {list(PROVIDER_REGISTRY)}")
    return provider_cls()
