"""
ProviderClient - the contract every concrete provider adapter
implements - M7.2. One method that does real work (`complete`), one that
never touches the network (`is_configured`) - mirrors
app.delivery.providers.base's own ChannelProvider shape (that precedent
already established "is_configured() as a cheap, no-network readiness
check" in this codebase; M7.2 reuses it rather than inventing a new
one).
"""
from abc import ABC, abstractmethod
from typing import ClassVar

from app.ai_gateway.request import GatewayRequest, GatewayResponse


class ProviderClient(ABC):
    key: ClassVar[str]

    @abstractmethod
    def complete(self, request: GatewayRequest) -> GatewayResponse:
        """Must raise one of app.ai_gateway.errors' normalized
        GatewayError subclasses for every failure mode - never let a
        provider SDK's own exception type escape this method."""
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        """True only if this provider has everything it needs (API key
        at minimum) to attempt a real call - never makes a network call
        itself. AIGateway.complete() checks this before attempting a
        provider in the routing chain, so a genuinely unconfigured
        provider fails fast with a clear ProviderAuthError-shaped
        message instead of an opaque SDK-level exception."""
        raise NotImplementedError
