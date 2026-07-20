import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../../api/client";
import { Breadcrumbs } from "../../components/Breadcrumbs";
import { useInterval } from "../../hooks/useInterval";
import { Badge, Button, PlaceholderNotice, Table, type TableColumn } from "../../design-system";
import type { BadgeTone } from "../../design-system";

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

/**
 * DeliveryCampaignDetail — M8.7 Phase E2 (AI Workforce zone). Migrated in
 * place per Design Bible Section 9.2: identical fetch/schedule/pause/
 * resume/cancel/retry calls and identical polling behavior, only the
 * markup moves onto design-system tokens/primitives - the queue-items
 * grid is a genuine Table use case (uniform rows of scalar cells), unlike
 * the expandable-row pages elsewhere in this phase.
 */
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

  const columns: TableColumn<DeliveryQueueItem>[] = [
    { key: "recipient_email", header: "Recipient", render: (i) => <span className="text-slate-200">{i.recipient_email}</span> },
    { key: "status", header: "Status", render: (i) => <Badge tone={ITEM_STATUS_TONE[i.status] ?? "neutral"}>{i.status}</Badge> },
    {
      key: "when",
      header: "Scheduled / Sent",
      render: (i) => (
        <span className="text-xs text-slate-500">
          {i.sent_at
            ? `Sent ${new Date(i.sent_at).toLocaleString()}`
            : i.scheduled_send_at
              ? new Date(i.scheduled_send_at).toLocaleString()
              : "—"}
        </span>
      ),
    },
    {
      key: "attempts",
      header: "Attempts",
      render: (i) => <span className="text-xs text-slate-500">{i.attempt_count} / {i.max_attempts}</span>,
    },
    {
      key: "last_error",
      header: "Last error",
      render: (i) => (
        <span className="block max-w-xs truncate text-xs text-status-danger" title={i.last_error ?? undefined}>
          {i.last_error ?? "—"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      render: (item) => (
        <div className="flex gap-2">
          {(item.status === "queued" || item.status === "scheduled" || item.status === "retry") && (
            <button
              disabled={busyItemId === item.id}
              onClick={() => cancelItem(item.id)}
              className="text-xs font-medium text-status-danger hover:underline disabled:opacity-50"
            >
              Cancel
            </button>
          )}
          {(item.status === "failed" || item.status === "retry") && (
            <button
              disabled={busyItemId === item.id}
              onClick={() => retryItem(item.id)}
              className="text-xs font-medium text-slate-200 hover:underline disabled:opacity-50"
            >
              Retry now
            </button>
          )}
        </div>
      ),
    },
  ];

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
            <h1 className="text-h1 font-semibold text-slate-100">{campaign.name}</h1>
            <Badge tone={CAMPAIGN_STATUS_TONE[campaign.status] ?? "neutral"}>{campaign.status}</Badge>
          </div>
          {campaign.description && <p className="text-sm text-slate-400">{campaign.description}</p>}
        </div>
        <div className="flex shrink-0 gap-2">
          {campaign.status === "draft" && (
            <Button disabled={busyAction} onClick={() => runAction("schedule")}>
              Schedule
            </Button>
          )}
          {campaign.status === "active" && (
            <Button variant="secondary" disabled={busyAction} onClick={() => runAction("pause")}>
              Pause
            </Button>
          )}
          {campaign.status === "paused" && (
            <Button disabled={busyAction} onClick={() => runAction("resume")}>
              Resume
            </Button>
          )}
          {(campaign.status === "draft" || campaign.status === "active" || campaign.status === "paused") && (
            <Button variant="destructive" disabled={busyAction} onClick={() => runAction("cancel")}>
              Cancel
            </Button>
          )}
        </div>
      </div>

      {actionError && <p className="mb-4 text-sm text-status-danger">{actionError}</p>}

      <div className="mb-6 flex flex-wrap gap-2">
        {Object.entries(summary).map(([status, count]) => (
          <span key={status} className="flex items-center gap-1.5 rounded-lg border border-border-hairline px-2.5 py-1 text-xs">
            <Badge tone={ITEM_STATUS_TONE[status] ?? "neutral"}>{status}</Badge>
            <span className="text-slate-400">{count}</span>
          </span>
        ))}
      </div>

      {items.length === 0 ? (
        <PlaceholderNotice kind="no-data" reason="No queue items." />
      ) : (
        <Table columns={columns} rows={items} rowKey={(i) => i.id} emptyMessage="No queue items." />
      )}
    </div>
  );
}
