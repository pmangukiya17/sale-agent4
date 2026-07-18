"""
Microsoft 365 / Outlook provider - EmailConnectionProvider +
EmailSendCapable only (no MailboxReadCapable in M5 - see base.py's
docstring). Implemented against the raw Microsoft identity platform OAuth2
endpoints and Microsoft Graph REST API v1.0 via httpx, same reasoning as
GmailProvider for not using the msal SDK: fewer third-party API surfaces
to get right from memory with no way to execute-test them here.

KNOWN LIMITATION - provider_message_id is always None for Outlook sends.
Graph's plain POST /me/sendMail endpoint returns 202 Accepted with an
empty body; it does not hand back a message id, unlike Gmail's
users.messages.send. Getting a real provider_message_id from Graph
requires the create-draft-then-send pattern (POST /me/messages, then
POST /me/messages/{id}/send) instead of the single-call sendMail used
here. Accepted as-is for M5 by explicit product decision - not a defect
to silently work around by returning a fake id, and not worth
redesigning M5's send path now. Future enhancement path: if M6 (Reply
Intelligence & Conversation Management) needs real conversation
threading for Outlook, switch OutlookProvider.send() to the
draft-then-send pattern at that point, which yields a real message id
usable for threading - a localized change to this method's
implementation, not a change to EmailSendCapable's interface or to
anything upstream of it.

UNVERIFIED BY EXECUTION - same disclosure as gmail_provider.py: checked
only via py_compile and manual cross-reference against Microsoft's
published OAuth2 and Graph API docs, not run against a real Microsoft
365 tenant.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.delivery.providers.base import (
    ConnectionVerificationResult,
    DeliverySendOutcome,
    EmailConnectionProvider,
    EmailSendCapable,
    OAuthTokenPayload,
    ProviderAuthError,
    ProviderSendError,
)


class OutlookProvider(EmailConnectionProvider, EmailSendCapable):
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

        try:
            response = httpx.post(
                f"{self.GRAPH_BASE}/me/sendMail",
                headers=self._auth_header(context.credential_payload["access_token"]),
                json={"message": message, "saveToSentItems": True},
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise ProviderSendError(f"Network error sending via Microsoft Graph: {exc}", permanent=False) from exc

        if response.status_code == 401:
            raise ProviderAuthError("Microsoft Graph rejected the access token (401) - connection needs reconnecting.")
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderSendError(f"Graph send failed transiently: {response.status_code} {response.text[:200]}", permanent=False)
        if response.status_code >= 400:
            raise ProviderSendError(f"Graph rejected the send: {response.status_code} {response.text[:200]}", permanent=True)

        # 202 Accepted, empty body - known limitation, see this module's
        # docstring for the future enhancement path.
        return DeliverySendOutcome(provider_message_id=None, detail={"status_code": response.status_code})

    # --- internal helpers ---------------------------------------------------

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
