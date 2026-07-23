"""
tests.test_scope_utils - Outlook Integration milestone.

Pure logic, zero fixtures, zero database - app/delivery/scope_utils.py
imports nothing beyond the stdlib, so this suite has no sqlalchemy
dependency at all and can be run to completion in an environment with no
Postgres/Docker access, the same "pure logic, actually executed in the
authoring sandbox" precedent tests/test_opportunity_state_machine.py
already set for Track C3.

This is also the FIRST test coverage build_reconnect_authorize_url's
scope logic has ever had - it previously had zero tests of any kind.
"""
import unittest

from app.delivery.scope_utils import top_up_scopes


class TestTopUpScopes(unittest.TestCase):
    def test_no_prior_grant_returns_baseline(self):
        self.assertEqual(top_up_scopes(None, ["Mail.Send", "User.Read"]), ["Mail.Send", "User.Read"])

    def test_empty_list_prior_grant_returns_baseline(self):
        self.assertEqual(top_up_scopes([], ["Mail.Send", "User.Read"]), ["Mail.Send", "User.Read"])

    def test_already_granted_scopes_are_kept_and_ordered_first(self):
        # This is the exact incident this function fixes: a connection
        # already has an OLDER, narrower grant on record; the current
        # baseline (post-fix) is wider. The result must contain BOTH -
        # the historical grant is not discarded, and the new baseline
        # requirement is not silently dropped either.
        result = top_up_scopes(
            ["https://graph.microsoft.com/Mail.Send", "https://graph.microsoft.com/User.Read", "offline_access"],
            [
                "https://graph.microsoft.com/Mail.Send",
                "https://graph.microsoft.com/Mail.ReadWrite",
                "https://graph.microsoft.com/User.Read",
                "offline_access",
            ],
        )
        self.assertEqual(
            result,
            [
                "https://graph.microsoft.com/Mail.Send",
                "https://graph.microsoft.com/User.Read",
                "offline_access",
                "https://graph.microsoft.com/Mail.ReadWrite",
            ],
        )
        self.assertIn("https://graph.microsoft.com/Mail.ReadWrite", result)

    def test_no_duplicates_when_baseline_fully_overlaps_prior_grant(self):
        granted = ["Mail.Send", "User.Read", "offline_access"]
        result = top_up_scopes(granted, ["Mail.Send", "User.Read", "offline_access"])
        self.assertEqual(result, granted)
        self.assertEqual(len(result), len(set(result)))

    def test_additional_scopes_unioned_only_when_provided(self):
        result = top_up_scopes(["Mail.Send"], ["Mail.Send"], additional=["Mail.Read"])
        self.assertEqual(result, ["Mail.Send", "Mail.Read"])

    def test_additional_none_never_adds_read_scopes(self):
        # The explicit-opt-in guarantee: a plain top-up (additional=None,
        # the default at every call site that isn't the read-access
        # Reconnect path) must never smuggle in mailbox-read scopes.
        result = top_up_scopes(["Mail.Send"], ["Mail.Send"], additional=None)
        self.assertNotIn("Mail.Read", result)

    def test_additional_scopes_not_duplicated_if_already_granted(self):
        result = top_up_scopes(["Mail.Send", "Mail.Read"], ["Mail.Send"], additional=["Mail.Read"])
        self.assertEqual(result, ["Mail.Send", "Mail.Read"])

    def test_realistic_outlook_send_and_read_upgrade(self):
        # The exact real-world scenario this milestone fixes end to end:
        # an existing connection granted only the old, narrow send_scopes
        # (no Mail.ReadWrite), reconnecting with include_read_scopes=True.
        already_granted = [
            "https://graph.microsoft.com/Mail.Send",
            "https://graph.microsoft.com/User.Read",
            "offline_access",
        ]
        current_send_scopes = [
            "https://graph.microsoft.com/Mail.Send",
            "https://graph.microsoft.com/Mail.ReadWrite",
            "https://graph.microsoft.com/User.Read",
            "offline_access",
        ]
        read_scopes = ["https://graph.microsoft.com/Mail.Read"]

        result = top_up_scopes(already_granted, current_send_scopes, additional=read_scopes)

        for scope in current_send_scopes + read_scopes:
            self.assertIn(scope, result)
        self.assertEqual(len(result), len(set(result)))


if __name__ == "__main__":
    unittest.main()
