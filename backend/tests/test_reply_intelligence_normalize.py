"""
Pure-logic tests for app/reply_intelligence/normalize.py and
sync_worker.has_read_scope - no DB, no network, no Docker required (same
"retroactively extract pure helpers with tests" precedent as M5 Layer 3's
scheduler/windows.py and credentials/payload_codec.py tests). Runnable
anywhere a plain Python interpreter with this project's dependencies is
available.

Run standalone with:
    python -m unittest tests.test_reply_intelligence_normalize
"""
import unittest
import uuid
from datetime import datetime, timezone
from typing import ClassVar

from app.delivery.providers.base import IncrementalSyncCapable, RawAttachment, RawEmailMessage
from app.models.enums import MessageDirection
from app.reply_intelligence.normalize import raw_attachment_to_kwargs, raw_message_to_email_message_kwargs
from app.reply_intelligence.sync_worker import has_read_scope


def _raw_message(**overrides) -> RawEmailMessage:
    kwargs = dict(
        provider_message_id="msg-1",
        provider_thread_id="thread-1",
        internet_message_id="<abc@example.com>",
        in_reply_to=None,
        references=None,
        from_email="sender@example.com",
        from_name="Sender Name",
        subject="Re: Quote request",
        body_text=None,
        body_html="<p>hello</p>",
        sent_at=datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc),
        received_at=datetime(2026, 7, 18, 10, 1, tzinfo=timezone.utc),
        has_attachments=False,
        attachments=[],
    )
    kwargs.update(overrides)
    return RawEmailMessage(**kwargs)


class TestNormalizeRawEmailMessage(unittest.TestCase):
    def test_conversation_id_always_none(self):
        # The entire point of the M6.2 lifecycle design: sync-produced
        # messages never carry a conversation_id - see
        # email_message.py's docstring.
        kwargs = raw_message_to_email_message_kwargs(
            _raw_message(),
            company_profile_id=uuid.uuid4(),
            provider_connection_id=uuid.uuid4(),
            provider_key="outlook",
            synced_at=datetime.now(timezone.utc),
        )
        self.assertIsNone(kwargs["conversation_id"])

    def test_direction_always_inbound(self):
        kwargs = raw_message_to_email_message_kwargs(
            _raw_message(),
            company_profile_id=uuid.uuid4(),
            provider_connection_id=uuid.uuid4(),
            provider_key="outlook",
            synced_at=datetime.now(timezone.utc),
        )
        self.assertEqual(kwargs["direction"], MessageDirection.INBOUND)

    def test_field_mapping_is_1to1(self):
        company_profile_id = uuid.uuid4()
        provider_connection_id = uuid.uuid4()
        synced_at = datetime.now(timezone.utc)
        raw = _raw_message(in_reply_to="<parent@example.com>", references="<parent@example.com>")

        kwargs = raw_message_to_email_message_kwargs(
            raw,
            company_profile_id=company_profile_id,
            provider_connection_id=provider_connection_id,
            provider_key="outlook",
            synced_at=synced_at,
        )

        self.assertEqual(kwargs["company_profile_id"], company_profile_id)
        self.assertEqual(kwargs["provider_connection_id"], provider_connection_id)
        self.assertEqual(kwargs["provider"], "outlook")
        self.assertEqual(kwargs["provider_message_id"], raw.provider_message_id)
        self.assertEqual(kwargs["provider_thread_id"], raw.provider_thread_id)
        self.assertEqual(kwargs["internet_message_id"], raw.internet_message_id)
        self.assertEqual(kwargs["in_reply_to"], "<parent@example.com>")
        self.assertEqual(kwargs["references"], "<parent@example.com>")
        self.assertEqual(kwargs["from_email"], raw.from_email)
        self.assertEqual(kwargs["from_name"], raw.from_name)
        self.assertEqual(kwargs["subject"], raw.subject)
        self.assertEqual(kwargs["body_html"], raw.body_html)
        self.assertIsNone(kwargs["body_text"])
        self.assertEqual(kwargs["sent_at"], raw.sent_at)
        self.assertEqual(kwargs["received_at"], raw.received_at)
        self.assertEqual(kwargs["synced_at"], synced_at)
        self.assertEqual(kwargs["has_attachments"], raw.has_attachments)


class TestNormalizeRawAttachment(unittest.TestCase):
    def test_field_mapping_excludes_email_message_id(self):
        raw = RawAttachment(
            provider_attachment_id="att-1", filename="quote.pdf", content_type="application/pdf", size_bytes=1024
        )
        kwargs = raw_attachment_to_kwargs(raw)
        self.assertEqual(
            kwargs, {"filename": "quote.pdf", "content_type": "application/pdf", "size_bytes": 1024, "provider_attachment_id": "att-1"}
        )
        self.assertNotIn("email_message_id", kwargs)


# --- has_read_scope: pure isinstance + set-subset logic, no DB needed ------


class _FakeConnectionNoScopes:
    scopes_granted = None


class _FakeConnectionSendOnly:
    scopes_granted = ["https://graph.microsoft.com/Mail.Send", "offline_access"]


class _FakeConnectionWithReadScope:
    scopes_granted = [
        "https://graph.microsoft.com/Mail.Send",
        "https://graph.microsoft.com/Mail.Read",
        "offline_access",
    ]


class _SendOnlyProvider:
    """Does not implement IncrementalSyncCapable at all."""

    key = "fake_send_only"


class _SyncCapableProvider(IncrementalSyncCapable):
    key = "fake_sync_capable"
    read_scopes: ClassVar[list[str]] = ["https://graph.microsoft.com/Mail.Read"]

    def fetch_messages_incremental(self, credential_payload, cursor, max_results):  # pragma: no cover - not exercised here
        raise NotImplementedError


class TestHasReadScope(unittest.TestCase):
    def test_provider_without_incremental_sync_capable_is_never_eligible(self):
        self.assertFalse(has_read_scope(_FakeConnectionWithReadScope(), _SendOnlyProvider()))

    def test_scope_capable_provider_but_scope_not_granted_is_ineligible(self):
        self.assertFalse(has_read_scope(_FakeConnectionSendOnly(), _SyncCapableProvider()))

    def test_no_scopes_at_all_is_ineligible(self):
        self.assertFalse(has_read_scope(_FakeConnectionNoScopes(), _SyncCapableProvider()))

    def test_scope_capable_provider_with_scope_granted_is_eligible(self):
        self.assertTrue(has_read_scope(_FakeConnectionWithReadScope(), _SyncCapableProvider()))


if __name__ == "__main__":
    unittest.main()
