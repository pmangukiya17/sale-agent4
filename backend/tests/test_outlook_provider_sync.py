"""
OutlookProvider.fetch_messages_incremental() tests against MOCKED
Microsoft Graph HTTP responses - no live Graph credentials, no network
call, no Docker/Postgres required. This is the Outlook-adapter-specific
counterpart to tests/test_sync_worker_cursor_contract.py (which tests
sync_worker's own orchestration against a stub provider and never touches
OutlookProvider at all) - this module is the one place that actually
proves OutlookProvider's Graph delta-query parsing does what
docs/architecture/m6-reply-intelligence-plan.md's "Synchronization Cursor
Contract - as built" section documents, at the HTTP-response-shape level.

Every `httpx.get` call OutlookProvider.fetch_messages_incremental would
make is intercepted via unittest.mock.patch - `_FakeResponse` stands in
for `httpx.Response`. Runnable anywhere a plain Python interpreter with
this project's dependencies (httpx) is available.

Run standalone with:
    python -m unittest tests.test_outlook_provider_sync
"""
import unittest
from unittest.mock import patch

from app.delivery.providers.base import ProviderAuthError, ProviderSyncError
from app.delivery.providers.outlook_provider import OutlookProvider

_CREDENTIAL = {"access_token": "fake-access-token"}


class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json_body = json_body or {}
        self.text = text or str(json_body)

    def json(self):
        return self._json_body


def _graph_message(
    *,
    message_id: str,
    internet_message_id: str,
    in_reply_to: str | None = None,
    references: str | None = None,
    has_attachments: bool = False,
) -> dict:
    headers = []
    if in_reply_to:
        headers.append({"name": "In-Reply-To", "value": in_reply_to})
    if references:
        headers.append({"name": "References", "value": references})
    return {
        "id": message_id,
        "conversationId": "conv-1",
        "internetMessageId": internet_message_id,
        "internetMessageHeaders": headers,
        "from": {"emailAddress": {"address": "buyer@example.com", "name": "Buyer Co"}},
        "subject": "Re: Quote request",
        "body": {"contentType": "html", "content": "<p>Thanks for the quote.</p>"},
        "receivedDateTime": "2026-07-18T10:15:00Z",
        "sentDateTime": "2026-07-18T10:14:30Z",
        "hasAttachments": has_attachments,
    }


class TestOutlookFetchMessagesIncremental(unittest.TestCase):
    def setUp(self):
        self.provider = OutlookProvider()

    # --- initial sync (cursor=None) ----------------------------------------
    def test_initial_sync_returns_parsed_messages_and_deltalink_cursor(self):
        response = _FakeResponse(
            200,
            {
                "value": [_graph_message(message_id="m1", internet_message_id="<m1@example.com>")],
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=abc123",
            },
        )
        with patch("app.delivery.providers.outlook_provider.httpx.get", return_value=response) as mock_get:
            result = self.provider.fetch_messages_incremental(_CREDENTIAL, cursor=None, max_results=50)

        self.assertEqual(mock_get.call_count, 1)
        called_url = mock_get.call_args.args[0]
        self.assertIn("/me/mailFolders/inbox/messages/delta", called_url)
        # urlencode() percent-encodes "$" to "%24" - either way, this
        # substring survives, proving the initial call is scoped by a
        # receivedDateTime filter (the bounded-initial-window design).
        self.assertIn("filter=receivedDateTime", called_url)

        self.assertEqual(len(result.messages), 1)
        message = result.messages[0]
        self.assertEqual(message.provider_message_id, "m1")
        self.assertEqual(message.provider_thread_id, "conv-1")
        self.assertEqual(message.internet_message_id, "<m1@example.com>")
        self.assertEqual(message.from_email, "buyer@example.com")
        self.assertEqual(message.from_name, "Buyer Co")
        self.assertEqual(message.subject, "Re: Quote request")
        self.assertEqual(message.body_html, "<p>Thanks for the quote.</p>")
        self.assertIsNone(message.body_text, "body_text is never derived from HTML - see module docstring")
        self.assertIsNotNone(message.sent_at)
        self.assertIsNotNone(message.received_at)

        self.assertEqual(result.next_cursor, "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=abc123")
        self.assertFalse(result.has_more, "a deltaLink response means fully caught up")

    # --- continuation call: the cursor is called AS-IS, no reconstruction -
    def test_continuation_call_uses_saved_cursor_verbatim_as_the_request_url(self):
        saved_cursor = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$skiptoken=xyz"
        response = _FakeResponse(200, {"value": [], "@odata.deltaLink": saved_cursor})

        with patch("app.delivery.providers.outlook_provider.httpx.get", return_value=response) as mock_get:
            self.provider.fetch_messages_incremental(_CREDENTIAL, cursor=saved_cursor, max_results=50)

        called_url = mock_get.call_args.args[0]
        self.assertEqual(called_url, saved_cursor, "a saved cursor must be called exactly as returned - no query params rebuilt")

    # --- pagination: nextLink means more pages are available now ----------
    def test_nextlink_response_sets_has_more_true_and_uses_nextlink_as_cursor(self):
        next_link = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$skiptoken=page2"
        response = _FakeResponse(
            200,
            {
                "value": [_graph_message(message_id="m1", internet_message_id="<m1@example.com>")],
                "@odata.nextLink": next_link,
            },
        )
        with patch("app.delivery.providers.outlook_provider.httpx.get", return_value=response):
            result = self.provider.fetch_messages_incremental(_CREDENTIAL, cursor=None, max_results=50)

        self.assertTrue(result.has_more)
        self.assertEqual(result.next_cursor, next_link)

    # --- deletion markers are skipped, not turned into messages ------------
    def test_removed_marker_entries_are_skipped(self):
        response = _FakeResponse(
            200,
            {
                "value": [
                    {"id": "deleted-1", "@removed": {"reason": "deleted"}},
                    _graph_message(message_id="m1", internet_message_id="<m1@example.com>"),
                ],
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?token=1",
            },
        )
        with patch("app.delivery.providers.outlook_provider.httpx.get", return_value=response):
            result = self.provider.fetch_messages_incremental(_CREDENTIAL, cursor=None, max_results=50)

        self.assertEqual(len(result.messages), 1)
        self.assertEqual(result.messages[0].provider_message_id, "m1")

    # --- In-Reply-To/References header extraction --------------------------
    def test_in_reply_to_and_references_headers_are_extracted(self):
        response = _FakeResponse(
            200,
            {
                "value": [
                    _graph_message(
                        message_id="m1",
                        internet_message_id="<m1@example.com>",
                        in_reply_to="<parent@example.com>",
                        references="<grandparent@example.com> <parent@example.com>",
                    )
                ],
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?token=1",
            },
        )
        with patch("app.delivery.providers.outlook_provider.httpx.get", return_value=response):
            result = self.provider.fetch_messages_incremental(_CREDENTIAL, cursor=None, max_results=50)

        message = result.messages[0]
        self.assertEqual(message.in_reply_to, "<parent@example.com>")
        self.assertEqual(message.references, "<grandparent@example.com> <parent@example.com>")

    # --- attachment metadata fetched only when hasAttachments is true -----
    def test_attachment_metadata_fetched_for_messages_with_attachments(self):
        message_page = _FakeResponse(
            200,
            {
                "value": [_graph_message(message_id="m1", internet_message_id="<m1@example.com>", has_attachments=True)],
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?token=1",
            },
        )
        attachments_page = _FakeResponse(
            200, {"value": [{"id": "att-1", "name": "quote.pdf", "contentType": "application/pdf", "size": 2048}]}
        )

        def _side_effect(url, *args, **kwargs):
            if "/attachments" in url:
                return attachments_page
            return message_page

        with patch("app.delivery.providers.outlook_provider.httpx.get", side_effect=_side_effect) as mock_get:
            result = self.provider.fetch_messages_incremental(_CREDENTIAL, cursor=None, max_results=50)

        self.assertEqual(mock_get.call_count, 2, "one call for the message page, one for that message's attachments")
        message = result.messages[0]
        self.assertTrue(message.has_attachments)
        self.assertEqual(len(message.attachments), 1)
        self.assertEqual(message.attachments[0].filename, "quote.pdf")
        self.assertEqual(message.attachments[0].provider_attachment_id, "att-1")
        self.assertEqual(message.attachments[0].size_bytes, 2048)

    # --- no attachment call when hasAttachments is false --------------------
    def test_no_attachment_call_when_message_has_no_attachments(self):
        response = _FakeResponse(
            200,
            {
                "value": [_graph_message(message_id="m1", internet_message_id="<m1@example.com>", has_attachments=False)],
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?token=1",
            },
        )
        with patch("app.delivery.providers.outlook_provider.httpx.get", return_value=response) as mock_get:
            result = self.provider.fetch_messages_incremental(_CREDENTIAL, cursor=None, max_results=50)

        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(result.messages[0].attachments, [])

    # --- error handling: 401 -> ProviderAuthError, not ProviderSyncError ---
    def test_401_raises_provider_auth_error(self):
        response = _FakeResponse(401, {}, text="Unauthorized")
        with patch("app.delivery.providers.outlook_provider.httpx.get", return_value=response):
            with self.assertRaises(ProviderAuthError):
                self.provider.fetch_messages_incremental(_CREDENTIAL, cursor=None, max_results=50)

    # --- error handling: 5xx -> ProviderSyncError ---------------------------
    def test_5xx_raises_provider_sync_error(self):
        response = _FakeResponse(503, {}, text="Service Unavailable")
        with patch("app.delivery.providers.outlook_provider.httpx.get", return_value=response):
            with self.assertRaises(ProviderSyncError):
                self.provider.fetch_messages_incremental(_CREDENTIAL, cursor=None, max_results=50)

    # --- error handling: network error -> ProviderSyncError, not a bare
    # httpx exception propagating out of the adapter boundary --------------
    def test_network_error_raises_provider_sync_error(self):
        import httpx

        with patch("app.delivery.providers.outlook_provider.httpx.get", side_effect=httpx.ConnectError("boom")):
            with self.assertRaises(ProviderSyncError):
                self.provider.fetch_messages_incremental(_CREDENTIAL, cursor=None, max_results=50)


if __name__ == "__main__":
    unittest.main()
