"""
M8.3 Step 7 (Premium Approval UI) - pure, zero-third-party-dependency
tests for app.ai_gateway.premium_approval_resolver. Genuinely executable
and executed in the authoring sandbox (no Docker, no pydantic_settings, no
sqlalchemy) - unlike AIGateway itself (see test_ai_provider_hierarchy_e2e.py's
own docstring: constructing AIGateway needs app.core.config.settings at
import time, which needs pydantic_settings), this module's own top-level
imports are deliberately stdlib-only (logging/uuid/abc - see its own module
docstring), so the ABC, its fail-safe short-circuit paths, and the
singleton factory can all be exercised directly here.

NOT covered here (needs Docker - see test_premium_approval_e2e.py):
SQLAlchemyPremiumApprovalResolver.is_preauthorized()'s real-DB branch (a
valid company_profile_id UUID that actually reaches
has_live_preauthorization()), and AIGateway.complete()/preflight()'s own
wiring of an injected resolver into the gate check (covered in
test_ai_provider_hierarchy_e2e.py's TestPremiumApprovalGate, extended for
this step - that file needs settings at import time regardless of whether
the resolver itself does).
"""
import unittest
import uuid

from app.ai_gateway.premium_approval_resolver import (
    PremiumApprovalResolver,
    SQLAlchemyPremiumApprovalResolver,
    get_premium_approval_resolver,
)


class _ConformingFakeResolver(PremiumApprovalResolver):
    """Proves the ABC's contract is genuinely implementable by a
    dependency-injected fake - the same shape AIGateway's own
    `premium_approval_resolver` constructor param expects (see
    client.py's own docstring)."""

    def __init__(self, *, result: bool):
        self.result = result
        self.calls: list[tuple[str | None, str]] = []

    def is_preauthorized(self, *, company_profile_id: str | None, capability: str) -> bool:
        self.calls.append((company_profile_id, capability))
        return self.result


class TestPremiumApprovalResolverABC(unittest.TestCase):
    def test_cannot_instantiate_abstract_base_directly(self):
        with self.assertRaises(TypeError):
            PremiumApprovalResolver()  # type: ignore[abstract]

    def test_conforming_subclass_can_be_instantiated_and_called(self):
        resolver = _ConformingFakeResolver(result=True)
        self.assertTrue(resolver.is_preauthorized(company_profile_id=str(uuid.uuid4()), capability="research_analysis"))
        self.assertEqual(len(resolver.calls), 1)


class TestSQLAlchemyResolverFailSafeShortCircuits(unittest.TestCase):
    """Every branch below returns False WITHOUT ever importing sqlalchemy/
    the DB layer - see is_preauthorized()'s own docstring for why these
    specific inputs must short-circuit before that import is even
    attempted. Genuinely proves the "fail safe, not fail open" contract
    for the two cheapest-to-hit invalid-input cases without needing
    Docker."""

    def setUp(self):
        self.resolver = SQLAlchemyPremiumApprovalResolver()

    def test_none_company_profile_id_returns_false(self):
        self.assertFalse(self.resolver.is_preauthorized(company_profile_id=None, capability="research_analysis"))

    def test_empty_string_company_profile_id_returns_false(self):
        self.assertFalse(self.resolver.is_preauthorized(company_profile_id="", capability="research_analysis"))

    def test_non_uuid_company_profile_id_returns_false(self):
        self.assertFalse(
            self.resolver.is_preauthorized(company_profile_id="definitely-not-a-uuid", capability="research_analysis")
        )

    def test_valid_uuid_in_sandbox_without_db_layer_still_fails_safe(self):
        # A well-formed UUID clears the parse step and reaches the lazy
        # `from app.db import base as _base` / `SessionLocal` import -
        # which genuinely fails in this sandbox (no sqlalchemy/
        # pydantic_settings installed, same disclosure every other e2e
        # test file in this project already makes). This is exactly the
        # "any underlying error -> False, never raise" contract the
        # method's own docstring requires, exercised for real (not
        # mocked) rather than assumed.
        result = self.resolver.is_preauthorized(company_profile_id=str(uuid.uuid4()), capability="research_analysis")
        self.assertFalse(result)


class TestGetPremiumApprovalResolverSingleton(unittest.TestCase):
    def test_returns_a_sqlalchemy_resolver_instance(self):
        self.assertIsInstance(get_premium_approval_resolver(), SQLAlchemyPremiumApprovalResolver)

    def test_returns_the_same_instance_on_repeated_calls(self):
        self.assertIs(get_premium_approval_resolver(), get_premium_approval_resolver())


if __name__ == "__main__":
    unittest.main()
