import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../../api/client";
import { Card, Badge, Button, PlaceholderNotice } from "../../design-system";
import type { BadgeTone } from "../../design-system";

interface ConnectableProvider {
  provider_key: string;
  send_scopes: string[];
}

interface ProviderConnection {
  id: string;
  provider_key: string;
  external_account_email: string | null;
  scopes_granted: string[] | null;
  status: "connected" | "expired" | "revoked" | "error" | "disconnected";
  connected_at: string | null;
  last_verification_at: string | null;
  last_verified_at: string | null;
  last_verification_detail: string | null;
}

const STATUS_TONE: Record<string, BadgeTone> = {
  connected: "success",
  expired: "warning",
  revoked: "danger",
  error: "danger",
  disconnected: "neutral",
};

const PROVIDER_LABELS: Record<string, string> = {
  gmail: "Gmail",
  outlook: "Outlook / Microsoft 365",
};

/**
 * DeliveryConnections — M8.7 Phase E2 (AI Workforce zone). Migrated in
 * place per Design Bible Section 9.2: identical fetch/connect/reconnect/
 * verify/disconnect calls, only the markup moves onto design-system
 * tokens/primitives - including retiring the page-local StatusBadge in
 * favor of the one canonical Badge (Design Debt Budget, Section 10.1);
 * see StatusBadge.tsx's removal note in this same pass.
 */
export default function DeliveryConnections() {
  const { companyId } = useParams();
  const [connectableProviders, setConnectableProviders] = useState<ConnectableProvider[]>([]);
  const [connections, setConnections] = useState<ProviderConnection[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setIsLoading(true);
    Promise.all([
      apiClient.get<ConnectableProvider[]>("/delivery/providers"),
      apiClient.get<ProviderConnection[]>(`/company-profiles/${companyId}/provider-connections`),
    ])
      .then(([providersRes, connectionsRes]) => {
        setConnectableProviders(providersRes.data);
        setConnections(connectionsRes.data);
      })
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [companyId]);

  const handleConnect = async (providerKey: string) => {
    setError(null);
    try {
      const { data } = await apiClient.get<{ authorize_url: string }>(
        `/company-profiles/${companyId}/provider-connections/connect`,
        { params: { provider_key: providerKey } }
      );
      window.location.href = data.authorize_url;
    } catch {
      setError(`Could not start connecting ${PROVIDER_LABELS[providerKey] ?? providerKey}.`);
    }
  };

  const handleReconnect = async (connectionId: string) => {
    setError(null);
    setBusyId(connectionId);
    try {
      const { data } = await apiClient.get<{ authorize_url: string }>(
        `/company-profiles/${companyId}/provider-connections/${connectionId}/reconnect`
      );
      window.location.href = data.authorize_url;
    } catch {
      setError("Could not start reconnecting this mailbox.");
      setBusyId(null);
    }
  };

  const handleVerify = async (connectionId: string) => {
    setError(null);
    setBusyId(connectionId);
    try {
      await apiClient.post(`/company-profiles/${companyId}/provider-connections/${connectionId}/verify`);
      load();
    } catch {
      setError("Could not verify this connection.");
    } finally {
      setBusyId(null);
    }
  };

  const handleDisconnect = async (connectionId: string) => {
    if (!confirm("Disconnect this mailbox? Sending profiles using it will stop being able to send until reconnected.")) return;
    setError(null);
    setBusyId(connectionId);
    try {
      await apiClient.post(`/company-profiles/${companyId}/provider-connections/${connectionId}/disconnect`);
      load();
    } catch {
      setError("Could not disconnect this mailbox.");
    } finally {
      setBusyId(null);
    }
  };

  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>;

  return (
    <div>
      <Card className="mb-6">
        <h3 className="mb-1 text-base font-semibold text-slate-100">Connect a mailbox</h3>
        <p className="mb-4 text-sm text-slate-400">
          Grants send-only access - never continuous or automatic mailbox reading. One mailbox can back several sending
          identities.
        </p>
        {connectableProviders.length === 0 ? (
          <p className="text-sm text-slate-400">
            No providers are configured on this server yet. An admin needs to set the OAuth client id/secret for Gmail
            or Outlook before a mailbox can be connected.
          </p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {connectableProviders.map((p) => (
              <Button key={p.provider_key} onClick={() => handleConnect(p.provider_key)}>
                + Connect {PROVIDER_LABELS[p.provider_key] ?? p.provider_key}
              </Button>
            ))}
          </div>
        )}
      </Card>

      {error && <p className="mb-4 text-sm text-status-danger">{error}</p>}

      {connections.length === 0 ? (
        <PlaceholderNotice kind="no-data" reason="No mailboxes connected yet." />
      ) : (
        <div className="space-y-3">
          {connections.map((c) => (
            <Card key={c.id}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <span className="font-medium text-slate-100">{PROVIDER_LABELS[c.provider_key] ?? c.provider_key}</span>
                    <Badge tone={STATUS_TONE[c.status] ?? "neutral"}>{c.status}</Badge>
                  </div>
                  <p className="text-sm text-slate-300">{c.external_account_email ?? "—"}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {c.last_verified_at ? `Last verified ${new Date(c.last_verified_at).toLocaleString()}` : "Never verified"}
                  </p>
                  {c.last_verification_detail && <p className="mt-1 text-xs text-status-danger">{c.last_verification_detail}</p>}
                </div>
                <div className="flex shrink-0 gap-2 text-sm">
                  <button
                    disabled={busyId === c.id}
                    onClick={() => handleVerify(c.id)}
                    className="rounded-lg border border-border-hairline px-3 py-1.5 text-slate-200 hover:border-border-hairline-strong hover:bg-surface-2 disabled:opacity-50"
                  >
                    Verify
                  </button>
                  <button
                    disabled={busyId === c.id}
                    onClick={() => handleReconnect(c.id)}
                    className="rounded-lg border border-border-hairline px-3 py-1.5 text-slate-200 hover:border-border-hairline-strong hover:bg-surface-2 disabled:opacity-50"
                  >
                    Reconnect
                  </button>
                  <button
                    disabled={busyId === c.id}
                    onClick={() => handleDisconnect(c.id)}
                    className="rounded-lg border border-border-hairline px-3 py-1.5 text-status-danger hover:bg-status-danger/10 disabled:opacity-50"
                  >
                    Disconnect
                  </button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
