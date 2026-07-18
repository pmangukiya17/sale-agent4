import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../../api/client";
import { StatusBadge, type BadgeTone } from "../../components/StatusBadge";

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
      <div className="mb-6 rounded-lg border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-900">
        <h3 className="mb-1 text-base font-semibold text-slate-900 dark:text-slate-100">Connect a mailbox</h3>
        <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
          Grants send-only access - never continuous or automatic mailbox reading. One mailbox can back several sending
          identities.
        </p>
        {connectableProviders.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            No providers are configured on this server yet. An admin needs to set the OAuth client id/secret for Gmail
            or Outlook before a mailbox can be connected.
          </p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {connectableProviders.map((p) => (
              <button
                key={p.provider_key}
                onClick={() => handleConnect(p.provider_key)}
                className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:bg-indigo-600 dark:hover:bg-indigo-500"
              >
                + Connect {PROVIDER_LABELS[p.provider_key] ?? p.provider_key}
              </button>
            ))}
          </div>
        )}
      </div>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {connections.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900">
          No mailboxes connected yet.
        </div>
      ) : (
        <div className="space-y-3">
          {connections.map((c) => (
            <div key={c.id} className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
              <div className="flex items-start justify-between">
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <span className="font-medium text-slate-900 dark:text-slate-100">
                      {PROVIDER_LABELS[c.provider_key] ?? c.provider_key}
                    </span>
                    <StatusBadge label={c.status} tone={STATUS_TONE[c.status] ?? "neutral"} />
                  </div>
                  <p className="text-sm text-slate-600 dark:text-slate-300">{c.external_account_email ?? "—"}</p>
                  <p className="mt-1 text-xs text-slate-400">
                    {c.last_verified_at ? `Last verified ${new Date(c.last_verified_at).toLocaleString()}` : "Never verified"}
                  </p>
                  {c.last_verification_detail && <p className="mt-1 text-xs text-red-600">{c.last_verification_detail}</p>}
                </div>
                <div className="flex shrink-0 gap-2 text-sm">
                  <button
                    disabled={busyId === c.id}
                    onClick={() => handleVerify(c.id)}
                    className="rounded-md border border-slate-200 px-3 py-1.5 text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    Verify
                  </button>
                  <button
                    disabled={busyId === c.id}
                    onClick={() => handleReconnect(c.id)}
                    className="rounded-md border border-slate-200 px-3 py-1.5 text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    Reconnect
                  </button>
                  <button
                    disabled={busyId === c.id}
                    onClick={() => handleDisconnect(c.id)}
                    className="rounded-md border border-slate-200 px-3 py-1.5 text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-slate-700"
                  >
                    Disconnect
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
