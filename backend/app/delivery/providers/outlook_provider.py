"""
Microsoft 365 / Outlook provider - EmailConnectionProvider +
EmailSendCapable only (no MailboxReadCapable in M5 - see base.py's
docstring). Implemented against the raw Microsoft identity platform OAuth2
endpoints and Microsoft Graph REST API v1.0 via httpx, same reasoning as
GmailProvider for not using the msal SDK: fewer third-party API surfaces
to get right from memory with no way to execute-test them here.

M6.3 UPDATE - the KNOWN LIMITATION below is now fixed. send() switched
from the single-call POST /me/sendMail to the create-draft-then-send
pattern (POST /me/messages, then POST /me/messages/{id}/send), exactly
the enhancement path this docstring originally flagged. This was not
primarily about obtaining provider_message_id (though it does) - the
real reason is that Graph's create-draft response hands back its own
server-generated internetMessageId and conversationId BEFORE the message
is sent, which is what M6.3's Thread Builder needs to reliably match a
reply's In-Reply-To back to this exact outbound send. Unlike
GmailProvider (which authors the raw MIME itself and can set a
Message-ID header with certainty), this codebase cannot safely assume
Graph would honor a client-supplied Message-ID on send - so rather than
guess, this reads back Graph's own true value instead. See
DeliverySendOutcome's docstring (app/delivery/providers/base.py) for how
these two fields are consumed by dispatch_service.

Original limitation, for historical record: Graph's plain POST
/me/sendMail endpoint returns 202 Accepted with an empty body - no
message id, no thread id, no internetMessageId. Accepted as-is for M5 by
explicit product decision at the time; M6.3 is the point this document
always said that decision would be revisited.

UNVERIFIED BY EXECUTION - same disclosure as gmail_provider.py: checked
only via py_compile and manual cross-reference against Microsoft's
published OAuth2 and Graph API docs, not run against a real Microsoft
365 tenant.

M6.2 ADDITION - IncrementalSyncCapable via Graph's delta query
(GET /me/mailFolders/inbox/messages/delta), Inbox-only, inbound-only (see
IncrementalSyncCapable's own docstring for why outbound is out of scope).
Same "UNVERIFIED BY EXECUTION" disclosure applies to this addition too.

A few Graph-specific simplifications, made deliberately and disclosed here
rather than silently:

- The cursor persisted in MailboxSyncState is the FULL @odata.nextLink or
  @odata.deltaLink URL Graph itself hands back, not a hand-extracted
  token - Graph's delta protocol is designed to be driven exactly this
  way (call the URL you were given), so there is no token-parsing logic
  here to get subtly wrong.
- Exactly one HTTP page is fetched per fetch_messages_incremental() call,
  even when Graph's response carries @odata.nextLink (meaning more pages
  are available right now). The result's has_more=True communicates this;
  the sync worker does not loop within one tick to drain every page - the
  next scheduled tick calls this method again with the saved nextLink
  cursor and fetches the following page. This trades "a very full inbox
  takes several ticks to fully backfill" for a much simpler worker loop
  with no internal retry/pagination state to get wrong; acceptable since
  M6.2's sync is a continuous background process, not a one-shot import.
- An initial sync (cursor=None) is scoped with a $filter on
  receivedDateTime to the last INITIAL_SYNC_WINDOW_DAYS days, not an
  unbounded backfill of the entire mailbox history - Graph's delta query
  supports combining an initial $filter with subsequent delta tracking
  (the filter becomes part of what the resulting deltaLink continues to
  track), so this is the documented way to bound an initial sync, not a
  workaround.
- internetMessageHeaders (needed for In-Reply-To/References, not returned
  by Graph's message resource by default) is requested via $select
  alongside the other fields sync needs.
- Attachment CONTENT is never fetched - only metadata (id/name/
  contentType/size) via a second, per-message call to
  /me/messages/{id}/attachments, and only when hasAttachments is true.
  This mirrors Attachment's own model docstring (metadata-only, no
  writer for file bytes yet).
- Deleted-item markers in a delta response (@removed) are skipped
  entirely, not translated into any kind of tombstone/delete operation on
  our own EmailMessage rows - M6.2 has no concept of retracting a
  message once synced; if this ever needs to change, it is new,
  deliberate scope for a later milestone, not an oversight here.
- body_text is left unpopulated (None) - Graph's default message
  resource gives HTML content (body.content) plus a truncated
  bodyPreview, not a full plain-text rendering; body_html is the
  authoritative field sync writes. Deriving a real plain-text body from
  HTML is deferred, not attempted with a naive/lossy strip here.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.delivery.providers.base import (
    ConnectionVerificationResult,
    DeliverySendOutcome,
    EmailConnectionProvider,
    EmailSendCapable,
    IncrementalSyncCapable,
    IncrementalSyncResult,
    OAuthTokenPayload,
    ProviderAuthError,
    ProviderSendError,
    ProviderSyncError,
    RawAttachment,
    RawEmailMessage,
    RawRecipient,
)


class OutlookProvider(EmailConnectionProvider, EmailSendCapable, IncrementalSyncCapable):
    key = "outlook"
    # Mail.Send for actually sending; offline_access is required to get a
    # refresh_token at all, not an elevated permission by itself. User.Read
    # added after M5 Layer 7 verification found _fetch_account_email/
    # verify() both call GET /v1.0/me to populate external_account_email -
    # Graph requires User.Read for that endpoint specifically, and it is
    # not implied by Mail.Send (unlike Gmail's users.getProfile, which
    # accepts several scopes including gmail.send - the two providers'
    # underlying APIs aren't symmetric here).
    send_scopes = ["https://graph.microsoft.com/Mail.Send", "https://graph.microsoft.com/User.Read", "offline_access"]
    # M6.2: requested only via Reconnect, only when a user actually
    # enables mailbox sync for this connection - see
    # IncrementalSyncCapable's docstring. NOT requested upfront by
    # send_scopes above.
    read_scopes: ClassVar[list[str]] = ["https://graph.microsoft.com/Mail.Read"]

    INITIAL_SYNC_WINDOW_DAYS: ClassVar[int] = 30
    MESSAGE_SELECT_FIELDS: ClassVar[str] = (
        "id,conversationId,internetMessageId,internetMessageHeaders,from,toRecipients,"
        "ccRecipients,subject,body,receivedDateTime,sentDateTime,hasAttachments"
    )

    GRAPH_BASE = "https://graph.microsoft.com/v1.0"

    @property
    def _authority(self) -> str:
        return f"https://login.microsoftonline.com/{settings.MICROSOFT_OAUTH_TENANT_ID}"

    def is_configured(self) -> bool:
        return bool(settings.MICROSOFT_OAUTH_CLIENT_ID and settings.MICROSOFT_OAUTH_CLIENT_SECRET)

    def get_authorize_url(self, state: str, scopes: list[str]) -> str:
        params = {
            "client_id": settings.MICROSOFT_OAUTH_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": settings.MICROSOFT_OAUTH_REDIRECT_URI,
            "response_mode": "query",
            "scope": " ".join(scopes),
            "state": state,
        }
        return f"{self._authority}/oauth2/v2.0/authorize?{urlencode(params)}"

    def exchange_code(self, code: str) -> OAuthTokenPayload:
        response = httpx.post(
            f"{self._authority}/oauth2/v2.0/token",
            data={
                "client_id": settings.MICROSOFT_OAUTH_CLIENT_ID,
                "client_secret": settings.MICROSOFT_OAUTH_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.MICROSOFT_OAUTH_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
        self._raise_for_auth_error(response, "code exchange")
        data = response.json()
        payload = self._token_payload_from_response(data, fallback_refresh_token=None)
        payload.external_account_email = self._fetch_account_email(payload.access_token)
        return payload

    def refresh_access_token(self, refresh_token: str) -> OAuthTokenPayload:
        response = httpx.post(
            f"{self._authority}/oauth2/v2.0/token",
            data={
                "client_id": settings.MICROSOFT_OAUTH_CLIENT_ID,
                "client_secret": settings.MICROSOFT_OAUTH_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        self._raise_for_auth_error(response, "token refresh")
        data = response.json()
        # Unlike Gmail, Microsoft DOES rotate the refresh_token on every
        # refresh call - the old one may already be invalid, so always
        # prefer whatever comes back over the fallback.
        return self._token_payload_from_response(data, fallback_refresh_token=refresh_token)

    def verify(self, credential_payload: dict) -> ConnectionVerificationResult:
        try:
            response = httpx.get(
                f"{self.GRAPH_BASE}/me", headers=self._auth_header(credential_payload["access_token"]), timeout=15
            )
        except httpx.HTTPError as exc:
            return ConnectionVerificationResult(success=False, detail=f"Network error contacting Microsoft Graph: {exc}")
        if response.status_code == 401:
            return ConnectionVerificationResult(success=False, detail="Microsoft Graph rejected the access token (401) - reconnect required.")
        if response.status_code >= 400:
            return ConnectionVerificationResult(success=False, detail=f"Graph verify failed: {response.status_code} {response.text[:200]}")
        data = response.json()
        return ConnectionVerificationResult(success=True, external_account_email=data.get("mail") or data.get("userPrincipalName"))

    def send(self, context: "DeliveryContext") -> DeliverySendOutcome:  # noqa: F821
        """M6.3: create-draft-then-send, replacing the single-call
        sendMail this method used through M5 - see module docstring for
        why. Two Graph calls instead of one; a failure on the SEND step
        (after the draft was already created) is still classified via the
        same status-code rules as before, so dispatch_service's retry/
        fail behavior is unchanged regardless of which of the two calls
        actually failed."""
        item = context.queue_item
        assembled = (item.frozen_content or {}).get("assembled", {})
        body = assembled.get("body", "")
        signature_html = assembled.get("signature_html")
        html_body = "<br>".join(line for line in body.splitlines()) if body else ""
        if signature_html:
            html_body = f"<div>{html_body}</div><div>{signature_html}</div>"

        message: dict = {
            "subject": assembled.get("subject", ""),
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": item.recipient_email}}],
        }
        if context.sending_profile.reply_to_email:
            message["replyTo"] = [{"emailAddress": {"address": context.sending_profile.reply_to_email}}]

        headers = self._auth_header(context.credential_payload["access_token"])

        # Step 1: create the draft - its response is a full message
        # resource, including Graph's own server-generated
        # internetMessageId and conversationId, both captured below
        # BEFORE the message is sent.
        try:
            draft_response = httpx.post(f"{self.GRAPH_BASE}/me/messages", headers=headers, json=message, timeout=30)
        except httpx.HTTPError as exc:
            raise ProviderSendError(f"Network error creating Microsoft Graph draft: {exc}", permanent=False) from exc

        if draft_response.status_code == 401:
            raise ProviderAuthError("Microsoft Graph rejected the access token (401) - connection needs reconnecting.")
        if draft_response.status_code == 429 or draft_response.status_code >= 500:
            raise ProviderSendError(
                f"Graph draft creation failed transiently: {draft_response.status_code} {draft_response.text[:200]}", permanent=False
            )
        if draft_response.status_code >= 400:
            raise ProviderSendError(
                f"Graph rejected the draft: {draft_response.status_code} {draft_response.text[:200]}", permanent=True
            )

        draft = draft_response.json()
        draft_id = draft.get("id")
        internet_message_id = draft.get("internetMessageId")
        provider_thread_id = draft.get("conversationId")

        if not draft_id:
            # A 2xx response with no id would be a genuinely unexpected
            # Graph response shape - not classified as permanent, since a
            # transient Graph-side inconsistency is more likely than a
            # real, reproducible rejection.
            raise ProviderSendError("Graph draft creation returned no message id - cannot proceed to send.", permanent=False)

        # Step 2: send the draft. 202 Accepted, empty body - same as
        # sendMail's own response shape, but we already have everything
        # we need from step 1 above.
        try:
            send_response = httpx.post(f"{self.GRAPH_BASE}/me/messages/{draft_id}/send", headers=headers, timeout=30)
        except httpx.HTTPError as exc:
            raise ProviderSendError(f"Network error sending Microsoft Graph draft: {exc}", permanent=False) from exc

        if send_response.status_code == 401:
            raise ProviderAuthError("Microsoft Graph rejected the access token (401) - connection needs reconnecting.")
        if send_response.status_code == 429 or send_response.status_code >= 500:
            raise ProviderSendError(
                f"Graph send-draft failed transiently: {send_response.status_code} {send_response.text[:200]}", permanent=False
            )
        if send_response.status_code >= 400:
            raise ProviderSendError(
                f"Graph rejected sending the draft: {send_response.status_code} {send_response.text[:200]}", permanent=True
            )

        return DeliverySendOutcome(
            provider_message_id=draft_id,
            detail={"status_code": send_response.status_code},
            internet_message_id=internet_message_id,
            provider_thread_id=provider_thread_id,
        )

    def fetch_messages_incremental(
        self, credential_payload: dict, cursor: str | None, max_results: int
    ) -> IncrementalSyncResult:
        if cursor:
            # A previously-saved @odata.nextLink or @odata.deltaLink -
            # already a complete, callable Graph URL (see module docstring).
            url = cursor
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.INITIAL_SYNC_WINDOW_DAYS)
            params = {
                "$filter": f"receivedDateTime ge {cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')}",
                "$select": self.MESSAGE_SELECT_FIELDS,
                "$top": str(max_results),
            }
            url = f"{self.GRAPH_BASE}/me/mailFolders/inbox/messages/delta?{urlencode(params)}"

        try:
            response = httpx.get(url, headers=self._auth_header(credential_payload["access_token"]), timeout=30)
        except httpx.HTTPError as exc:
            raise ProviderSyncError(f"Network error querying Microsoft Graph delta: {exc}") from exc

        if response.status_code == 401:
            raise ProviderAuthError("Microsoft Graph rejected the access token (401) during sync - reconnect required.")
        if response.status_code >= 400:
            raise ProviderSyncError(f"Graph delta query failed: {response.status_code} {response.text[:300]}")

        data = response.json()
        raw_messages = data.get("value", [])

        messages: list[RawEmailMessage] = []
        for raw in raw_messages:
            if "@removed" in raw:
                # A deletion marker, not a message - see module docstring
                # for why this is intentionally skipped, not translated
                # into any local delete/tombstone operation.
                continue
            messages.append(self._to_raw_email_message(raw, credential_payload))

        next_cursor = data.get("@odata.nextLink") or data.get("@odata.deltaLink") or cursor
        has_more = "@odata.nextLink" in data

        return IncrementalSyncResult(messages=messages, next_cursor=next_cursor, has_more=has_more)

    # --- internal helpers ---------------------------------------------------

    def _to_raw_email_message(self, raw: dict[str, Any], credential_payload: dict) -> RawEmailMessage:
        from_field = raw.get("from") or {}
        from_address = (from_field.get("emailAddress") or {}).get("address")
        from_name = (from_field.get("emailAddress") or {}).get("name")

        headers = {
            (h.get("name") or "").lower(): h.get("value")
            for h in (raw.get("internetMessageHeaders") or [])
        }
        in_reply_to = headers.get("in-reply-to")
        references = headers.get("references")

        body = raw.get("body") or {}
        body_html = body.get("content") if (body.get("contentType") or "").lower() == "html" else None

        has_attachments = bool(raw.get("hasAttachments"))
        attachments: list[RawAttachment] = []
        message_id = raw.get("id")
        if has_attachments and message_id:
            attachments = self._fetch_attachment_metadata(message_id, credential_payload)

        return RawEmailMessage(
            provider_message_id=message_id,
            provider_thread_id=raw.get("conversationId"),
            internet_message_id=raw.get("internetMessageId"),
            in_reply_to=in_reply_to,
            references=references,
            from_email=from_address,
            from_name=from_name,
            subject=raw.get("subject"),
            body_text=None,  # see module docstring - not derived here
            body_html=body_html,
            sent_at=self._parse_graph_datetime(raw.get("sentDateTime")),
            received_at=self._parse_graph_datetime(raw.get("receivedDateTime")),
            has_attachments=has_attachments,
            attachments=attachments,
            to_recipients=self._parse_graph_recipients(raw.get("toRecipients")),
            cc_recipients=self._parse_graph_recipients(raw.get("ccRecipients")),
        )

    @staticmethod
    def _parse_graph_recipients(raw_recipients: list[dict] | None) -> list[RawRecipient]:
        result = []
        for entry in raw_recipients or []:
            address = (entry.get("emailAddress") or {})
            result.append(RawRecipient(email=address.get("address"), name=address.get("name")))
        return result

    def _fetch_attachment_metadata(self, message_id: str, credential_payload: dict) -> list[RawAttachment]:
        """Metadata only (id/name/contentType/size) - never attachment
        content. A failure here must not abort the whole sync tick (one
        message's attachment listing failing shouldn't lose the message
        itself, which sync already has by this point) - logged as an
        empty list rather than raised."""
        try:
            response = httpx.get(
                f"{self.GRAPH_BASE}/me/messages/{message_id}/attachments",
                headers=self._auth_header(credential_payload["access_token"]),
                params={"$select": "id,name,contentType,size"},
                timeout=30,
            )
        except httpx.HTTPError:
            return []
        if response.status_code >= 400:
            return []
        items = response.json().get("value", [])
        return [
            RawAttachment(
                provider_attachment_id=item.get("id"),
                filename=item.get("name"),
                content_type=item.get("contentType"),
                size_bytes=item.get("size"),
            )
            for item in items
        ]

    @staticmethod
    def _parse_graph_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            # Graph returns e.g. "2026-07-18T10:15:00Z" - fromisoformat
            # needs "+00:00", not a bare "Z", pre-3.11.
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _auth_header(access_token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {access_token}"}

    def _raise_for_auth_error(self, response: httpx.Response, action: str) -> None:
        if response.status_code >= 400:
            raise ProviderAuthError(f"Microsoft OAuth {action} failed: {response.status_code} {response.text[:300]}")

    @staticmethod
    def _token_payload_from_response(data: dict, fallback_refresh_token: str | None) -> OAuthTokenPayload:
        expires_in = data.get("expires_in", 3600)
        return OAuthTokenPayload(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", fallback_refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            scopes=data.get("scope", "").split(),
        )

    def _fetch_account_email(self, access_token: str) -> str | None:
        try:
            response = httpx.get(f"{self.GRAPH_BASE}/me", headers=self._auth_header(access_token), timeout=15)
            if response.status_code < 400:
                data = response.json()
                return data.get("mail") or data.get("userPrincipalName")
        except httpx.HTTPError:
            pass
        return None
