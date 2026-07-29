"""
M11 (AI Provider Hierarchy) - E2E tests requiring Docker (sqlalchemy is not
imported here, but `app.core.config.settings` IS - constructing it needs
pydantic_settings, unavailable in the authoring sandbox - confirmed by
direct import attempt AND a direct `pip install pydantic-settings
--break-system-packages` attempt, both failing the same way every prior
milestone's own disclosure in this project already documents). Only
py_compile-checked in the authoring sandbox - run for real via
verify_m9_ai_provider_hierarchy.sh, in Docker.

Exercises AIGateway.complete()'s new premium-approval gate end to end,
using the SAME provider_lookup DI seam test_ai_execution_platform_e2e.py
already established (fake ProviderClients, no real anthropic/openai/
google.genai SDK calls) - only settings.AI_MODE /
settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL are read for real, via
monkeypatching the actual settings object for the duration of each test
(restored in tearDown - same discipline as every other test in this
project that temporarily mutates shared config/registries).

M-AIGW-1 (Provider-Neutral AI Gateway foundation) addition:
TestCapabilityAwareRouting below deliberately does NOT use the
ROUTING_POLICY test-only override (that bypasses capability-filtering
entirely by design - see router.py's own docstring) or a fake
provider_lookup for routing itself - it exercises ProviderRouter.select()
against the REAL PROVIDER_CLIENT_REGISTRY/CAPABILITY_PROVIDER_PREFERENCE
default list and each real client's own declared _CAPABILITIES, which is
why it needs Docker (importing the real registry needs
anthropic/openai/google.genai installed) even more directly than the
tests above. TestPreflight below DOES use the same fake provider_lookup DI
seam as the rest of this file, since preflight() only calls
`is_configured()` (never `complete()`) on whatever the DI seam resolves.

M8.2 regression-sweep fix (see verify_m8_2_ai_gateway_backend.sh step 4):
this class used to hardcode the expected default preference list
(["local_ollama", "groq", "claude"]) and the resulting chain/premium/
excluded sets directly in each assertion. That was accurate the day
TestCapabilityAwareRouting was written, but went stale the moment
M-AIGW-3 added "gemini_ai_studio" to CAPABILITY_PROVIDER_PREFERENCE's
"default" entry - this test file was only py_compile-checked in every
sandbox between M-AIGW-3 and M8.2, so nothing ever caught the drift until
a real Docker run finally executed it. Per the CEO's explicit direction
("avoid brittle hardcoded provider lists... derive the expected provider
chain from the routing policy or registry"), the assertions below now
derive their expectations live from CAPABILITY_PROVIDER_PREFERENCE,
tiers.partition(), and each registered provider's own declared
capabilities - so a future provider addition to the default preference
list changes what this test expects automatically, instead of silently
breaking it again.

M8.3 Step 7 (Premium Approval UI) addition: TestPremiumApprovalGate below
gained a second cluster of tests covering the new `premium_approval_resolver`
constructor-injection seam (see client.py's own docstring) - a fake
PremiumApprovalResolver, injected the exact same way a fake `provider_lookup`
already is via `_make_gateway()`, proves the gate now also consults
`is_preauthorized()` (and, just as importantly, when it does NOT: the
`request.premium_approved=True` fast path must never pay for that call -
see client.py's own comment on `complete()`'s gate check for why that
ordering matters). Genuinely needs Docker for the same reason every other
test in this class does (constructing `AIGateway` needs `settings` at
`client.py` import time) - the resolver module itself IS pure and has its
own dedicated pure test file, tests/test_premium_approval_resolver_pure.py,
for the parts that don't need AIGateway at all.
"""
import unittest

from app.ai_gateway.client import AIGateway
from app.ai_gateway.errors import NoCapableProviderError, PremiumApprovalRequiredError
from app.ai_gateway.premium_approval_resolver import PremiumApprovalResolver
from app.ai_gateway.providers.base import ProviderClient
from app.ai_gateway.providers.registry import PROVIDER_CLIENT_REGISTRY
from app.ai_gateway.request import GatewayRequest, GatewayResponse, TokenUsage
from app.ai_gateway.router import CAPABILITY_PROVIDER_PREFERENCE, ROUTING_POLICY, ProviderRouter, RoutingDecision
from app.ai_gateway.tiers import partition
from app.core.config import settings


def _response(text: str, provider_key: str) -> GatewayResponse:
    return GatewayResponse(
        content=text,
        tool_calls=None,
        usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20, cost_usd=None),
        provider_key=provider_key,
        model="fake-model",
        finish_reason="stop",
    )


class _AlwaysUnavailableProviderClient(ProviderClient):
    key = "fake_local_down"

    def is_configured(self):
        return True

    def complete(self, request):
        from app.ai_gateway.errors import ProviderUnavailableError

        raise ProviderUnavailableError("simulated: local server not running", provider_key=self.key)


class _UnconfiguredProviderClient(ProviderClient):
    key = "fake_free_unconfigured"

    def is_configured(self):
        return False

    def complete(self, request):
        raise AssertionError("must never be called - is_configured() is False")


class _OkPremiumProviderClient(ProviderClient):
    key = "fake_premium_ok"

    def is_configured(self):
        return True

    def complete(self, request):
        return _response("premium response", provider_key=self.key)


def _make_gateway(clients: dict[str, ProviderClient], *, premium_approval_resolver=None) -> AIGateway:
    def provider_lookup(key: str) -> ProviderClient:
        client = clients.get(key)
        if client is None:
            raise KeyError(key)
        return client

    return AIGateway(provider_lookup=provider_lookup, premium_approval_resolver=premium_approval_resolver)


class _FakePremiumApprovalResolver(PremiumApprovalResolver):
    """M8.3 Step 7 - the same injected-fake shape `_make_gateway()`'s own
    `provider_lookup` closure already establishes, extended to the new
    seam. Records every call so tests can assert not just the return value
    but whether/how the gate actually consulted it."""

    def __init__(self, *, result: bool):
        self.result = result
        self.calls: list[tuple[str | None, str]] = []

    def is_preauthorized(self, *, company_profile_id: str | None, capability: str) -> bool:
        self.calls.append((company_profile_id, capability))
        return self.result


class TestPremiumApprovalGate(unittest.TestCase):
    CAPABILITY = "test_m9_capability"

    def setUp(self):
        self._original_mode = settings.AI_MODE
        self._original_gate = settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL
        settings.AI_MODE = "hybrid_recommended"
        settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL = True
        ROUTING_POLICY[self.CAPABILITY] = RoutingDecision(
            primary="fake_local_down",
            fallbacks=["fake_free_unconfigured"],
            premium=["fake_premium_ok"],
        )

    def tearDown(self):
        settings.AI_MODE = self._original_mode
        settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL = self._original_gate
        ROUTING_POLICY.pop(self.CAPABILITY, None)

    def test_local_and_free_exhausted_raises_premium_approval_required(self):
        gateway = _make_gateway(
            {"fake_local_down": _AlwaysUnavailableProviderClient(), "fake_free_unconfigured": _UnconfiguredProviderClient()}
        )
        request = GatewayRequest(capability=self.CAPABILITY)

        with self.assertRaises(PremiumApprovalRequiredError) as ctx:
            gateway.complete(request)

        self.assertEqual(ctx.exception.candidate_provider_key, "fake_premium_ok")

    def test_premium_approved_true_proceeds_to_premium_provider(self):
        gateway = _make_gateway(
            {
                "fake_local_down": _AlwaysUnavailableProviderClient(),
                "fake_free_unconfigured": _UnconfiguredProviderClient(),
                "fake_premium_ok": _OkPremiumProviderClient(),
            }
        )
        request = GatewayRequest(capability=self.CAPABILITY, premium_approved=True)

        response = gateway.complete(request)

        self.assertEqual(response.provider_key, "fake_premium_ok")

    def test_gate_disabled_auto_attempts_premium_without_approval(self):
        settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL = False
        gateway = _make_gateway(
            {
                "fake_local_down": _AlwaysUnavailableProviderClient(),
                "fake_free_unconfigured": _UnconfiguredProviderClient(),
                "fake_premium_ok": _OkPremiumProviderClient(),
            }
        )
        request = GatewayRequest(capability=self.CAPABILITY, premium_approved=False)

        response = gateway.complete(request)

        self.assertEqual(response.provider_key, "fake_premium_ok")

    def test_local_only_mode_never_reaches_premium_even_when_approved(self):
        settings.AI_MODE = "local_only"
        # local_only mode is resolved by ProviderRouter.select() reading
        # CAPABILITY_PROVIDER_PREFERENCE, not this test's ROUTING_POLICY
        # override (which bypasses tiering entirely by design - see
        # router.py's own docstring) - remove the override for this one
        # test so the real tier-aware resolution actually runs.
        ROUTING_POLICY.pop(self.CAPABILITY, None)
        gateway = _make_gateway({"local_ollama": _AlwaysUnavailableProviderClient()})
        request = GatewayRequest(capability=self.CAPABILITY, premium_approved=True)

        with self.assertRaises(Exception) as ctx:
            gateway.complete(request)
        self.assertNotIsInstance(ctx.exception, PremiumApprovalRequiredError)

    # -- M8.3 Step 7: injected PremiumApprovalResolver wiring -----------

    def test_injected_resolver_true_bypasses_gate_without_the_flag(self):
        resolver = _FakePremiumApprovalResolver(result=True)
        gateway = _make_gateway(
            {
                "fake_local_down": _AlwaysUnavailableProviderClient(),
                "fake_free_unconfigured": _UnconfiguredProviderClient(),
                "fake_premium_ok": _OkPremiumProviderClient(),
            },
            premium_approval_resolver=resolver,
        )
        # No company_profile_id here (defaults to None, same as every
        # OTHER test in this class) - CEO review fix (2026-07-29): a
        # syntactically-valid-but-nonexistent UUID here would still parse
        # cleanly in `_persist_ai_request_log()`'s own `_as_uuid()` and get
        # attempted as a real company_profiles.id FK on the successful
        # completion this test triggers below, producing a real (silently
        # swallowed, but noisy) ForeignKeyViolation on every run. None ->
        # `_as_uuid(None)` -> None -> no FK ever attempted, matching every
        # pre-existing test in this class's own established convention.
        request = GatewayRequest(capability=self.CAPABILITY, premium_approved=False)

        response = gateway.complete(request)

        self.assertEqual(response.provider_key, "fake_premium_ok")
        self.assertEqual(len(resolver.calls), 1)

    def test_injected_resolver_false_still_raises_premium_approval_required(self):
        resolver = _FakePremiumApprovalResolver(result=False)
        gateway = _make_gateway(
            {"fake_local_down": _AlwaysUnavailableProviderClient(), "fake_free_unconfigured": _UnconfiguredProviderClient()},
            premium_approval_resolver=resolver,
        )
        # No company_profile_id - see the identical CEO review fix comment
        # on test_injected_resolver_true_bypasses_gate_without_the_flag
        # above (this test also reaches log_ai_request(), via
        # _raise_premium_approval_required() this time).
        request = GatewayRequest(capability=self.CAPABILITY)

        with self.assertRaises(PremiumApprovalRequiredError):
            gateway.complete(request)
        self.assertEqual(len(resolver.calls), 1)

    def test_resolver_receives_the_requests_own_company_profile_id_and_capability(self):
        resolver = _FakePremiumApprovalResolver(result=False)
        gateway = _make_gateway(
            {"fake_local_down": _AlwaysUnavailableProviderClient(), "fake_free_unconfigured": _UnconfiguredProviderClient()},
            premium_approval_resolver=resolver,
        )
        # CEO review fix (2026-07-29): this test genuinely needs a non-None
        # value to prove pass-through, unlike the two tests above - but a
        # syntactically-valid `str(uuid.uuid4())` still triggers the same
        # real-but-swallowed ForeignKeyViolation noise those two now avoid
        # (this test also raises PremiumApprovalRequiredError, which also
        # calls log_ai_request()). A deliberately NON-UUID string sidesteps
        # that entirely: `_persist_ai_request_log()`'s own `_as_uuid()`
        # fails to parse it and substitutes None (no FK ever attempted),
        # while the FAKE resolver below - which never validates UUID-ness,
        # it only records whatever it's given - still receives and records
        # this exact string, so the pass-through assertion is just as
        # strong as a real-looking UUID would have been.
        company_id = "not-a-real-company-profile-id"
        request = GatewayRequest(capability=self.CAPABILITY, company_profile_id=company_id)

        with self.assertRaises(PremiumApprovalRequiredError):
            gateway.complete(request)

        self.assertEqual(resolver.calls, [(company_id, self.CAPABILITY)])

    def test_premium_approved_flag_short_circuits_before_resolver_is_consulted(self):
        # client.py's own comment on this check: "request.premium_approved
        # ... is checked first, unchanged - _is_premium_preauthorized() ...
        # is only ever consulted second" - the common already-approved
        # path must never pay for a resolver round trip it doesn't need.
        resolver = _FakePremiumApprovalResolver(result=False)
        gateway = _make_gateway(
            {
                "fake_local_down": _AlwaysUnavailableProviderClient(),
                "fake_free_unconfigured": _UnconfiguredProviderClient(),
                "fake_premium_ok": _OkPremiumProviderClient(),
            },
            premium_approval_resolver=resolver,
        )
        request = GatewayRequest(capability=self.CAPABILITY, premium_approved=True)

        response = gateway.complete(request)

        self.assertEqual(response.provider_key, "fake_premium_ok")
        self.assertEqual(resolver.calls, [])

    def test_preflight_reports_no_approval_needed_when_resolver_returns_true(self):
        # CEO review fix (2026-07-29): this originally used
        # _AlwaysUnavailableProviderClient (is_configured() -> True,
        # complete() raises) for "fake_local_down" - preflight() only ever
        # calls is_configured(), never complete() (see its own docstring),
        # so that fixture made chain_has_configured_candidate True and
        # preflight() returned approval_required=False BEFORE ever reaching
        # the resolver - the resolver.calls==1 assertion below was failing
        # for the wrong reason entirely (never consulted, not "consulted
        # and correctly returned False"). TestPreflight's own
        # test_nothing_configured_in_chain_reports_approval_required_with_estimate
        # (this same file, ~40 lines below) already documents this EXACT
        # fixture mistake from an earlier milestone - this test repeated
        # it. Fixed by using _UnconfiguredProviderClient (is_configured()
        # -> False) for BOTH chain entries, so chain_has_configured_candidate
        # is genuinely False and the resolver is actually reached - no
        # change to preflight() itself, which was already correctly wired
        # to `_is_premium_preauthorized()` (see client.py's own
        # docstring/code, unchanged by this fix).
        resolver = _FakePremiumApprovalResolver(result=True)
        gateway = _make_gateway(
            {"fake_local_down": _UnconfiguredProviderClient(), "fake_free_unconfigured": _UnconfiguredProviderClient()},
            premium_approval_resolver=resolver,
        )
        request = GatewayRequest(capability=self.CAPABILITY)

        result = gateway.preflight(request)

        self.assertFalse(result.approval_required)
        self.assertEqual(len(resolver.calls), 1)

    def test_preflight_still_reports_approval_needed_when_resolver_returns_false(self):
        # Same fixture fix as test_preflight_reports_no_approval_needed_when_resolver_returns_true
        # immediately above - see that test's own comment for the full
        # root-cause explanation (CEO review, 2026-07-29).
        resolver = _FakePremiumApprovalResolver(result=False)
        gateway = _make_gateway(
            {"fake_local_down": _UnconfiguredProviderClient(), "fake_free_unconfigured": _UnconfiguredProviderClient()},
            premium_approval_resolver=resolver,
        )
        request = GatewayRequest(capability=self.CAPABILITY)

        result = gateway.preflight(request)

        self.assertTrue(result.approval_required)
        self.assertEqual(result.candidate_provider_key, "fake_premium_ok")
        self.assertEqual(len(resolver.calls), 1)


class TestCapabilityAwareRouting(unittest.TestCase):
    """M-AIGW-1. Real registry, real default CAPABILITY_PROVIDER_PREFERENCE,
    real per-provider _CAPABILITIES declarations - nothing about this test
    class fakes routing policy or capability data.

    Expectations below are DERIVED from that real data (see the two helper
    methods), not hardcoded provider-name lists - see this file's module
    docstring for why (M8.2 regression-sweep: a hardcoded list here already
    went stale once, silently, when M-AIGW-3 added "gemini_ai_studio" to
    the default preference list)."""

    CAPABILITY = "test_m_aigw_1_capability"

    def setUp(self):
        self._original_mode = settings.AI_MODE
        settings.AI_MODE = "hybrid_recommended"

    def tearDown(self):
        settings.AI_MODE = self._original_mode
        ROUTING_POLICY.pop(self.CAPABILITY, None)

    @staticmethod
    def _default_preference() -> list[str]:
        """The real, live "default" preference list this capability
        actually falls back to (self.CAPABILITY has no specific entry) -
        read fresh each time so an added/removed/reordered provider is
        picked up automatically rather than needing this test updated too."""
        return list(CAPABILITY_PROVIDER_PREFERENCE["default"])

    @staticmethod
    def _reasoning_capable(provider_key: str) -> bool:
        """Real declared reasoning_support for provider_key, read straight
        off PROVIDER_CLIENT_REGISTRY - never assumed/hardcoded per name."""
        return PROVIDER_CLIENT_REGISTRY[provider_key].capabilities.reasoning_support

    def test_requires_deep_reasoning_excludes_non_reasoning_providers(self):
        request = GatewayRequest(capability=self.CAPABILITY, requires_deep_reasoning=True)
        decision = ProviderRouter.select(request)

        preference = self._default_preference()
        local, free, premium = partition(preference)
        chain_candidates = [*local, *free]  # hybrid_recommended folds local+free
        expected_chain = [key for key in chain_candidates if self._reasoning_capable(key)]
        expected_premium = [key for key in premium if self._reasoning_capable(key)]
        expected_excluded = {key for key in preference if not self._reasoning_capable(key)}

        self.assertEqual(decision.chain(), expected_chain)
        self.assertEqual(decision.premium, expected_premium)
        self.assertEqual(set(decision.capability_excluded), expected_excluded)

    def test_no_special_requirements_is_unaffected_by_capability_filtering(self):
        request = GatewayRequest(capability=self.CAPABILITY)
        decision = ProviderRouter.select(request)

        preference = self._default_preference()
        local, free, premium = partition(preference)

        self.assertEqual(decision.chain(), [*local, *free])
        self.assertEqual(decision.premium, premium)
        self.assertEqual(decision.capability_excluded, [])

    def test_no_capable_provider_at_all_raises_no_capable_provider_error(self):
        # local_only mode + requires_deep_reasoning=True: local_ollama is
        # the only chain candidate, and it lacks reasoning_support - chain
        # AND premium both end up empty specifically because of capability
        # exclusion (not because nothing was configured), which is exactly
        # the case NoCapableProviderError exists to distinguish from the
        # ordinary "no provider chain resolved" GatewayError.
        settings.AI_MODE = "local_only"
        gateway = AIGateway(provider_lookup=lambda key: (_ for _ in ()).throw(AssertionError("must never be resolved")))
        request = GatewayRequest(capability=self.CAPABILITY, requires_deep_reasoning=True)

        with self.assertRaises(NoCapableProviderError) as ctx:
            gateway.complete(request)
        self.assertIn("local_ollama", ctx.exception.excluded_provider_keys)


class TestPreflight(unittest.TestCase):
    """M-AIGW-1. AIGateway.preflight() - the same fake provider_lookup DI
    seam as TestPremiumApprovalGate above (preflight() only ever calls
    is_configured(), never complete(), so no real SDK call risk either
    way)."""

    CAPABILITY = "test_m_aigw_1_preflight_capability"

    def setUp(self):
        self._original_mode = settings.AI_MODE
        self._original_gate = settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL
        settings.AI_MODE = "hybrid_recommended"
        settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL = True
        ROUTING_POLICY[self.CAPABILITY] = RoutingDecision(
            primary="fake_local_down", fallbacks=["fake_free_unconfigured"], premium=["fake_premium_ok"]
        )

    def tearDown(self):
        settings.AI_MODE = self._original_mode
        settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL = self._original_gate
        ROUTING_POLICY.pop(self.CAPABILITY, None)

    def test_configured_candidate_in_chain_means_no_approval_needed(self):
        gateway = _make_gateway({"fake_local_down": _OkPremiumProviderClient()})
        # _OkPremiumProviderClient.is_configured() -> True, so this counts
        # as "chain has a configured candidate" even though its key isn't
        # semantically "local" - preflight() only checks is_configured(),
        # exactly like the in-flight walk does.
        result = gateway.preflight(GatewayRequest(capability=self.CAPABILITY))
        self.assertFalse(result.approval_required)

    def test_nothing_configured_in_chain_reports_approval_required_with_estimate(self):
        # Fixture fix (M8.2 regression sweep): this test's premise is
        # "nothing in the chain is configured." preflight() only ever
        # calls is_configured() - never complete() - so the fixture must
        # represent that with is_configured() -> False on BOTH chain
        # entries. _AlwaysUnavailableProviderClient (is_configured() ->
        # True, complete() raises) simulates a DIFFERENT scenario -
        # "configured, attempted, fails at call time" - correct for
        # TestPremiumApprovalGate's complete()-driven tests above, but it
        # silently satisfied chain_has_configured_candidate here, making
        # this test pass for the wrong reason (True == True) until it was
        # ever actually run - see this file's module docstring. Both
        # entries are now _UnconfiguredProviderClient so the fixture
        # genuinely matches "nothing configured," with no change to
        # preflight()/approval logic and no change to this test's own
        # assertions.
        gateway = _make_gateway(
            {"fake_local_down": _UnconfiguredProviderClient(), "fake_free_unconfigured": _UnconfiguredProviderClient()}
        )
        result = gateway.preflight(GatewayRequest(capability=self.CAPABILITY), prompt_char_length=5_000)
        self.assertTrue(result.approval_required)
        self.assertEqual(result.candidate_provider_key, "fake_premium_ok")

    def test_gate_disabled_means_no_approval_needed(self):
        settings.AI_GATEWAY_REQUIRE_PREMIUM_APPROVAL = False
        gateway = _make_gateway(
            {"fake_local_down": _AlwaysUnavailableProviderClient(), "fake_free_unconfigured": _UnconfiguredProviderClient()}
        )
        result = gateway.preflight(GatewayRequest(capability=self.CAPABILITY))
        self.assertFalse(result.approval_required)


if __name__ == "__main__":
    unittest.main()
