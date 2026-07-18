"""
Gmail provider - EmailConnectionProvider + EmailSendCapable only (no
MailboxReadCapable in M5 - see base.py's docstring and
docs/architecture/future-milestones.md note #9).

Deliberately implemented against the raw REST APIs (OAuth2 token
endpoint + Gmail API v1) via httpx rather than google-api-python-client/
google-auth-oauthlib. Two reasons: fewer third-party API surfaces to get
exactly right from memory with no way to execute-test them in this
environment (see the Layer 3 verification disclosure), and a raw HTTP
implementation is straightforward for a reviewer to audit directly
against Google's published API docs without also knowing a wrapper
library's specific object model.

UNVERIFIED BY EXECUTION: this file has not been run against the real
Gmail API - this sandbox has neither network access to install httpx nor
a real Google Cloud OAuth client to test against. Verified here only via
py_compile and manual cross-reference against Google's published OAuth2
and Gmail API v1 REST documentation. Needs a real run against a real
Google Cloud project's OAuth client before being trusted in production -
see the Layer 3 verification script.
"""
import base64
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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


class GmailProvider(EmailConnectionProvider, EmailSendCapable):
    key = "gmail"
    # Send-only for M5 - a future M6 Reconnect adds gmail.readonly
    # separately, via the same authorize-url builder with a different
    # scopes argument. Never requested upfront here.
    send_scopes = ["https://www.googleapis.com/auth/gmail.send"]

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    API_BASE = "https://gmail.googleapis.com/gmail/v1"

    def is_configured(self) -> bool:
        return bool(settings.GMAIL_OAUTH_CLIENT_ID and settings.GMAIL_OAUTH_CLIENT_SECRET)

    def get_authorize_url(self, state: str, scopes: list[str]) -> str:
        params = {
            "client_id": settings.GMAIL_OAUTH_CLIENT_ID,
            "redirect_uri": settings.GMAIL_OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(scopes),
            # offline + consent: Google only returns a refresh_token on
            # the FIRST consent for a given client/user/scope combo unless
            # prompt=consent forces the consent screen (and therefore a
            # fresh refresh_token) every time - needed because Reconnect
            # must reliably get a new refresh_token, not silently reuse
            # (or fail to get) an old one.
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> OAuthTokenPayload:
        response = httpx.post(
            self.TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GMAIL_OAUTH_CLIENT_ID,
                "client_secret": settings.GMAIL_OAUTH_CLIENT_SECRET,
                "redirect_uri": settings.GMAIL_OAUTH_REDIRECT_URI,
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
            self.TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.GMAIL_OAUTH_CLIENT_ID,
                "client_secret": settings.GMAIL_OAUTH_CLIENT_SECRET,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        self._raise_for_auth_error(response, "token refresh")
        data = response.json()
        # Google does not return a new refresh_token on a refresh call in
        # the common case - keep reusing the existing one.
        return self._token_payload_from_response(data, fallback_refresh_token=refresh_token)

    def verify(self, credential_payload: dict) -> ConnectionVerificationResult:
        try:
            response = httpx.get(
                f"{self.API_BASE}/users/me/profile",
                headers=self._auth_header(credential_payload["access_token"]),
                timeout=15,
            )
        except httpx.HTTPError as exc:
            return ConnectionVerificationResult(success=False, detail=f"Network error contacting Gmail: {exc}")
        if response.status_code == 401:
            return ConnectionVerificationResult(success=False, detail="Gmail rejected the access token (401) - reconnect required.")
        if response.status_code >= 400:
            return ConnectionVerificationResult(success=False, detail=f"Gmail verify failed: {response.status_code} {response.text[:200]}")
        data = response.json()
        return ConnectionVerificationResult(success=True, external_account_email=data.get("emailAddress"))

    def send(self, context: "DeliveryContext") -> DeliverySendOutcome:  # noqa: F821
        item = context.queue_item
        assembled = (item.frozen_content or {}).get("assembled", {})
        raw_message = self._build_mime_message(
            sender_email=context.sending_profile.sender_email,
            sender_name=context.sending_profile.sender_name,
            reply_to_email=context.sending_profile.reply_to_email,
            to_email=item.recipient_email,
            subject=assembled.get("subject", ""),
            body=assembled.get("body", ""),
            signature_html=assembled.get("signature_html"),
        )
        encoded = base64.urlsafe_b64encode(raw_message.as_bytes()).decode("utf-8")

        try:
            response = httpx.post(
                f"{self.API_BASE}/users/me/messages/send",
                headers=self._auth_header(context.credential_payload["access_token"]),
                json={"raw": encoded},
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise ProviderSendError(f"Network error sending via Gmail: {exc}", permanent=False) from exc

        if response.status_code == 401:
            raise ProviderAuthError("Gmail rejected the access token (401) - connection needs reconnecting.")
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderSendError(f"Gmail send failed transiently: {response.status_code} {response.text[:200]}", permanent=False)
        if response.status_code >= 400:
            raise ProviderSendError(f"Gmail rejected the send: {response.status_code} {response.text[:200]}", permanent=True)

        data = response.json()
        return DeliverySendOutcome(provider_message_id=data.get("id"), detail={"threadId": data.get("threadId")})

    # --- internal helpers ---------------------------------------------------

    @staticmethod
    def _auth_header(access_token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {access_token}"}

    def _raise_for_auth_error(self, response: httpx.Response, action: str) -> None:
        if response.status_code >= 400:
            raise ProviderAuthError(f"Gmail OAuth {action} failed: {response.status_code} {response.text[:300]}")

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
            response = httpx.get(
                f"{self.API_BASE}/users/me/profile", headers=self._auth_header(access_token), timeout=15
            )
            if response.status_code < 400:
                return response.json().get("emailAddress")
        except httpx.HTTPError:
            pass
        return None

    @staticmethod
    def _build_mime_message(
        *,
        sender_email: str,
        sender_name: str,
        reply_to_email: str | None,
        to_email: str,
        subject: str,
        body: str,
        signature_html: str | None,
    ) -> MIMEMultipart | MIMEText:
        if not signature_html:
            message = MIMEText(body, "plain", "utf-8")
        else:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(body, "plain", "utf-8"))
            body_html = "<br>".join(line for line in body.splitlines()) if body else ""
            html_part = f"<div>{body_html}</div><div>{signature_html}</div>"
            message.attach(MIMEText(html_part, "html", "utf-8"))

        message["Subject"] = subject
        message["From"] = f"{sender_name} <{sender_email}>" if sender_name else sender_email
        message["To"] = to_email
        if reply_to_email:
            message["Reply-To"] = reply_to_email
        return message
