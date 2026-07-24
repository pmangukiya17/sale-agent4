from typing import Any

from pydantic import BaseModel, ConfigDict


class DiscoveryProviderRead(BaseModel):
    """API response shape for GET /discovery-providers - not backed by
    any ORM model (this isn't a table; app.discovery.provider_service.
    DiscoveryProviderInfo is the plain-data value this is built from).
    `from_attributes=True` lets the route construct this directly from
    a DiscoveryProviderInfo dataclass instance without a manual
    field-by-field dict, the same way every other *Read schema here
    already does from an ORM row."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    enabled: bool
    capabilities: dict[str, Any]
