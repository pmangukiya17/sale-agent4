"""
GET /discovery-providers - M2 Phase 2 UX follow-up (Provider Visibility).

Deliberately NOT nested under /company-profiles/{id}/... - which
provider plugins are registered and healthy is a platform-wide fact
(driven by env-var configuration like BRAVE_SEARCH_API_KEY), not
tenant-specific data, exactly like /buyer-types, /industries,
/countries, /languages in app.api.routes.reference_data - same
read-only, get_current_user-only auth shape, no company-profile
ownership check needed.

Depends on app.discovery.provider_service.DiscoveryProviderService, NOT
on app.discovery.providers.registry directly - see that service's own
docstring for why this boundary exists.
"""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.discovery.provider_service import DiscoveryProviderService
from app.models.user import User
from app.schemas.discovery_provider import DiscoveryProviderRead

router = APIRouter()


@router.get("/discovery-providers", response_model=list[DiscoveryProviderRead])
def list_discovery_providers(current_user: User = Depends(get_current_user)) -> list[DiscoveryProviderRead]:
    providers = DiscoveryProviderService().list_providers()
    return [DiscoveryProviderRead.model_validate(p) for p in providers]
