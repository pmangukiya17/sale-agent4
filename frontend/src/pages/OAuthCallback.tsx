import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { Card } from "../design-system";

/**
 * Top-level landing page for Google/Microsoft's OAuth redirect - NOT
 * nested under /businesses/:companyId/... like every other business-
 * scoped page, because the browser arrives here fresh with only
 * ?code&state in the URL, no route params carrying which business this
 * is for. See GMAIL_OAUTH_REDIRECT_URI/MICROSOFT_OAUTH_REDIRECT_URI in
 * the backend's core/config.py and connection_service.py's docstring
 * for why the redirect lands on the frontend at all (a Layer 5 decision:
 * an authenticated completion call, paired with a signed/time-bounded
 * `state`, is what actually closes the cross-tenant CSRF gap a plain
 * backend-hosted callback couldn't).
 *
 * The base64 decode of `state` below is COSMETIC ONLY - it lets this
 * page show "Connecting Gmail…" instead of a blank spinner while the
 * real call is in flight. It is not, and must never be treated as, a
 * trust boundary: this page cannot verify state's HMAC signature (it has
 * no access to SECRET_KEY), so if the decode fails or looks wrong, the
 * UI still simply calls the backend and reports whatever answer comes
 * back - the backend remains the sole authority.
 */

function decodeStateForDisplay(state: string | null): { companyProfileId: string | null; providerKey: string | null } {
  if (!state) return { companyProfileId: null, providerKey: null };
  try {
    const envelope = JSON.parse(atob(state.replace(/-/g, "+").replace(/_/g, "/")));
    const payload = envelope?.payload ?? {};
    return {
      companyProfileId: typeof payload.company_profile_id === "string" ? payload.company_profile_id : null,
      providerKey: typeof payload.provider_key === "string" ? payload.provider_key : null,
    };
  } catch {
    return { companyProfileId: null, providerKey: null };
  }
}

const PROVIDER_LABELS: Record<string, string> = { gmail: "Gmail", outlook: "Outlook / Microsoft 365" };

type CallbackStatus = "pending" | "success" | "error";

export default function OAuthCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<CallbackStatus>("pending");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  // StrictMode/effect-dependency re-runs must not double-submit the same
  // code (the backend would reject the second exchange anyway, since an
  // OAuth authorization code is single-use, but failing fast locally
  // avoids a confusing extra error message).
  const hasSubmitted = useRef(false);

  const code = searchParams.get("code");
  const state = searchParams.get("state");
  // Google/Microsoft append these directly to the redirect_uri (this page)
  // instead of `code` whenever they reject the authorize request itself -
  // a redirect_uri that's registered but otherwise mismatched, a tenant
  // issue, a scope needing admin consent, or the user cancelling consent.
  // That's a real, provider-reported reason, not the same case as a
  // malformed/incomplete link - surfacing it here means the actual
  // AADSTS/Google error reaches the browser instead of only backend logs.
  const oauthError = searchParams.get("error");
  const oauthErrorDescription = searchParams.get("error_description");
  const { companyProfileId, providerKey } = decodeStateForDisplay(state);

  useEffect(() => {
    if (hasSubmitted.current) return;
    if (oauthError) {
      setStatus("error");
      setErrorMessage(oauthErrorDescription || `The provider rejected this connection attempt (${oauthError}).`);
      return;
    }
    if (!code || !state || !companyProfileId) {
      setStatus("error");
      setErrorMessage("This connection link is missing required information. Please try connecting again.");
      return;
    }
    hasSubmitted.current = true;

    apiClient
      .post(`/company-profiles/${companyProfileId}/provider-connections/callback`, { code, state })
      .then(() => {
        setStatus("success");
        setTimeout(() => navigate(`/businesses/${companyProfileId}/delivery/connections`, { replace: true }), 1200);
      })
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setStatus("error");
        setErrorMessage(detail ?? "Could not complete the connection. Please try again.");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const providerLabel = providerKey ? PROVIDER_LABELS[providerKey] ?? providerKey : "your mailbox";

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 px-4">
      <Card elevated className="w-full max-w-md text-center">
        {status === "pending" && (
          <>
            <p className="text-sm font-medium text-slate-100">Connecting {providerLabel}…</p>
            <p className="mt-2 text-sm text-slate-400">This will only take a moment.</p>
          </>
        )}
        {status === "success" && (
          <>
            <p className="text-sm font-medium text-status-success">{providerLabel} connected successfully.</p>
            <p className="mt-2 text-sm text-slate-400">Redirecting…</p>
          </>
        )}
        {status === "error" && (
          <>
            <p className="text-sm font-medium text-status-danger">Could not connect {providerLabel}.</p>
            <p className="mt-2 text-sm text-slate-400">{errorMessage}</p>
            {companyProfileId ? (
              <Link
                to={`/businesses/${companyProfileId}/delivery/connections`}
                className="mt-4 inline-block rounded-lg bg-accent-primary px-4 py-2 text-sm font-medium text-white hover:brightness-110"
              >
                Back to Connections
              </Link>
            ) : (
              <Link
                to="/businesses"
                className="mt-4 inline-block rounded-lg bg-accent-primary px-4 py-2 text-sm font-medium text-white hover:brightness-110"
              >
                Back to Businesses
              </Link>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
