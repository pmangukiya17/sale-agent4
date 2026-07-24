"""
tests.test_discovery_providers_route - M2 Phase 2 UX follow-up.

DB-backed - importing app.models.user (needed for a real `current_user`
argument) transitively requires sqlalchemy, which this project's
authoring sandbox does not have installed (no PyPI/network access - the
standing, disclosed constraint every *_e2e.py test in this project
already carries). See tests/test_discovery_provider_service_pure.py for
the service-layer coverage that IS genuinely executed here.

Calls the route function directly (same convention as
test_discovery_job_cancellation.py's TestCancelRoute) rather than going
through a real HTTP request/FastAPI TestClient - this route needs no DB
session at all (DiscoveryProviderService owns no Session dependency),
so the only reason a real User row is needed is to satisfy the route's
own `current_user: User = Depends(get_current_user)` signature - the
function itself never reads any attribute off it.

Run standalone with:
    python -m unittest tests.test_discovery_providers_route
"""
import unittest
import uuid
from unittest.mock import patch

# Must be imported before any ORM operation - see
# tests/test_conversation_models.py's own docstring for the full
# explanation (identical fix, identical failure mode).
from app.db import base as _base  # noqa: F401
from app.api.routes.discovery_providers import list_discovery_providers
from app.discovery.provider_service import DiscoveryProviderInfo
from app.models.enums import UserRole
from app.models.user import User


class TestListDiscoveryProvidersRoute(unittest.TestCase):
    def _make_user(self) -> User:
        # Deliberately NOT persisted (no db.add/commit) - the route
        # function never touches the database or reads any field off
        # current_user, so an in-memory instance is sufficient and
        # keeps this test independent of a real SessionLocal/company
        # profile fixture entirely.
        return User(id=uuid.uuid4(), email=f"m2-p2-ux-{uuid.uuid4()}@example.com", hashed_password="x", role=UserRole.ADMIN)

    def test_returns_one_read_model_per_registered_provider(self):
        fake_infos = [
            DiscoveryProviderInfo(key="manual_csv", name="Manual / CSV Import", enabled=True, capabilities={}),
            DiscoveryProviderInfo(
                key="brave_search", name="Brave Search", enabled=False,
                capabilities={"query_driven": True, "returns_contacts": False},
            ),
        ]
        with patch(
            "app.api.routes.discovery_providers.DiscoveryProviderService.list_providers",
            return_value=fake_infos,
        ):
            result = list_discovery_providers(current_user=self._make_user())

        self.assertEqual(len(result), 2)
        by_key = {r.key: r for r in result}
        self.assertTrue(by_key["manual_csv"].enabled)
        self.assertEqual(by_key["manual_csv"].name, "Manual / CSV Import")
        self.assertFalse(by_key["brave_search"].enabled)
        self.assertEqual(by_key["brave_search"].capabilities["query_driven"], True)

    def test_empty_provider_list_returns_empty_response(self):
        with patch("app.api.routes.discovery_providers.DiscoveryProviderService.list_providers", return_value=[]):
            result = list_discovery_providers(current_user=self._make_user())
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
