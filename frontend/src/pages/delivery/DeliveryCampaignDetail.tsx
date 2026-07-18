import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../../api/client";
import { Breadcrumbs } from "../../components/Breadcrumbs";
import { StatusBadge, type BadgeTone } from "../../components/StatusBadge";
import { useInterval } from "../../hooks/useInterval";

interface DeliveryCampaign {
  id: string;
  name: string;
  description: string | null;
  status: "draft" | "active" | "paused" | "completed" | "cancelled";
  daily_limit: number | null;
  hourly_limit: number | null;
  respect_recipient_timezone: boolean;
}

interface DeliveryEvent {
  id: string;
  event_type: string;
  occurred_at: string;
  detail: Record<string, unknown> | null;
}

interface DeliveryQueueItem {
  id: string;
  recipient_email: string;
  status: "queued" | "scheduled" | "sending" | "sent" | "failed" | "cancelled" | "retry";
  scheduled_send_at: string | null;
  sent_at: string | null;
  attempt_count: number;
  max_attempts: number;
  last_error: string | null;
  events: DeliveryEvent[];
}

const CAMPAIGN_STATUS_TONE: Record<string, BadgeTone> = {
  draft: "neutral",
  active: "info",
  paused: "warning",
  completed: "success",
  cancelled: "danger",
};

const ITEM_STATUS_TONE: Record<string, BadgeTone> = {
  queued: "neutral",
  scheduled: "info",
  sending: "info",
  sent: "success",
  failed: "danger",
  cancelled: "neutral",
  retry: "warning",
};

// Polling stops once the campaign is COMPLETED/CANCELLED - nothing left
// that can still change. See useInterval's docstring for why this is the
// first polling pattern in the app: unlike M1-M4, a queue item's status
// changes on the worker's own clock, not in response to any request this
// tab made.
const POLL_MS = 10_000;
const TERMINAL_CAMPAIGN_STATUSES = new Set(["completed", "cancelled"]);

export default function DeliveryCampaignDetail() {
  const { companyId, campaignId } = useParams();
  const base = `/company-profiles/${companyId}/delivery-campaigns/${campaignId}`;

  const [campaign, setCampaign] = useState<DeliveryCampaign | null>(null);
  const [items, setItems] = useState<DeliveryQueueItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState(false);
  const [busyItemId, setBusyItemId] = useState<string | null>(null);

  const load = useCallback((showLoadingScreen: boolean) => {
    if (showLoadingScreen) setIsLoading(true);
    return Promise.all([
      apiClient.get<DeliveryCampaign>(base),
      apiClient.get<DeliveryQueueItem[]>(`${base}/queue-items`),
    ])
      .then(([campaignRes, itemsRes]) => {
        setCampaign(campaignRes.data);
        setItems(itemsRes.data);
      })
      .finally(() => {
        if (showLoadingScreen) setIsLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base]);

  useEffect(() => {
    void load(true);
  }, [load]);

  // Silent background refresh - does not show the full-page loading
  // state, so the table doesn't flicker/unmount every 10s.
  useInterval(() => {
    void load(false);
  }, campaign && !TERMINAL_CAMPAIGN_STATUSES.has(campaign.status) ? POLL_MS : null);

  const runAction = async (action: "schedule" | "pause" | "resume" | "cancel") => {
    setActionError(null);
    setBusyAction(true);
    try {
      await apiClient.post(`${base}/${action}`);
      await load(false);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setActionError(detail ?? `Could not ${action} this campaign.`);
    } finally {
      setBusyAction(false);
    }
  };

  const cancelItem = async (itemId: string) => {
    setBusyItemId(itemId);
    try {
      await apiClient.post(`${base}/queue-items/${itemId}/cancel`);
      await load(false);
    } catch {
      setActionError("Could not cancel this item.");
    } finally {
      setBusyItemId(null);
    }
  };

  const retryItem = async (itemId: string) => {
    setBusyItemId(itemId);
    try {
      await apiClient.post(`${base}/queue-items/${itemId}/retry`);
      await load(false);
    } catch {
      setActionError("Could not retry this item.");
    } finally {
      setBusyItemId(null);
    }
  };

  if (isLoading || !campaign) return <p className="text-sm text-slate-500">Loading…</p>;

  const summary = items.reduce<Record<string, number>>((acc, i) => {
    acc[i.status] = (acc[i.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Businesses", to: "/businesses" },
          { label: "Delivery", to: `/businesses/${companyId}/delivery/campaigns` },
          { label: campaign.name },
        ]}
      />

      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <h2 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">{campaign.name}</h2>
            <StatusBadge label={campaign.status} tone={CAMPAIGN_STATUS_TONE[campaign.status] ?? "neutral"} />
          </div>
          {campaign.description && <p className="text-sm text-slate-500 dark:text-slate-400">{campaign.description}</p>}
        </div>
        <div className="flex shrink-0 gap-2 text-sm">
          {campaign.status === "draft" && (
            <button
              disabled={busyAction}
              onClick={() => runAction("schedule")}
              className="rounded-md bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-800 disabled:opacity-50 dark:bg-indigo-600 dark:hover:bg-indigo-500"
            >
              Schedule
            </button>
          )}
          {campaign.status === "active" && (
            <button
              disabled={busyAction}
              onClick={() => runAction("pause")}
              className="rounded-md border border-slate-200 px-4 py-2 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200"
            >
              Pause
            </button>
          )}
          {campaign.status === "paused" && (
            <button
              disabled={busyAction}
              onClick={() => runAction("resume")}
              className="rounded-md bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-800 disabled:opacity-50 dark:bg-indigo-600 dark:hover:bg-indigo-500"
            >
              Resume
            </button>
          )}
          {(campaign.status === "draft" || campaign.status === "active" || campaign.status === "paused") && (
            <button
              disabled={busyAction}
              onClick={() => runAction("cancel")}
              className="rounded-md border border-slate-200 px-4 py-2 font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-slate-700"
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {actionError && <p className="mb-4 text-sm text-red-600">{actionError}</p>}

      <div className="mb-6 flex flex-wrap gap-2">
        {Object.entries(summary).map(([status, count]) => (
          <span key={status} className="flex items-center gap-1.5 rounded-md border border-slate-200 px-2.5 py-1 text-xs dark:border-slate-700">
            <StatusBadge label={status} tone={ITEM_STATUS_TONE[status] ?? "neutral"} />
            <span className="text-slate-500 dark:text-slate-400">{count}</span>
          </span>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900">
          No queue items.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              <tr>
                <th className="px-4 py-2">Recipient</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Scheduled / Sent</th>
                <th className="px-4 py-2">Attempts</th>
                <th className="px-4 py-2">Last error</th>
                <th className="px-4 py-2">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {items.map((item) => (
                <tr key={item.id} className="bg-white dark:bg-slate-900">
                  <td className="px-4 py-2 text-slate-700 dark:text-slate-200">{item.recipient_email}</td>
                  <td className="px-4 py-2">
                    <StatusBadge label={item.status} tone={ITEM_STATUS_TONE[item.status] ?? "neutral"} />
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-500">
                    {item.sent_at
                      ? `Sent ${new Date(item.sent_at).toLocaleString()}`
                      : item.scheduled_send_at
                        ? new Date(item.scheduled_send_at).toLocaleString()
                        : "—"}
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-500">
                    {item.attempt_count} / {item.max_attempts}
                  </td>
                  <td className="max-w-xs truncate px-4 py-2 text-xs text-red-600" title={item.last_error ?? undefined}>
                    {item.last_error ?? "—"}
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex gap-2">
                      {(item.status === "queued" || item.status === "scheduled" || item.status === "retry") && (
                        <button
                          disabled={busyItemId === item.id}
                          onClick={() => cancelItem(item.id)}
                          className="text-xs font-medium text-red-600 hover:underline disabled:opacity-50"
                        >
                          Cancel
                        </button>
                      )}
                      {(item.status === "failed" || item.status === "retry") && (
                        <button
                          disabled={busyItemId === item.id}
                          onClick={() => retryItem(item.id)}
                          className="text-xs font-medium text-slate-700 hover:underline disabled:opacity-50 dark:text-slate-200"
                        >
                          Retry now
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
