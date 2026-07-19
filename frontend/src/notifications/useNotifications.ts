import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "../api/client";
import { useCompanies } from "../companies/CompanyContext";
import { useInterval } from "../hooks/useInterval";
import { useEventStream } from "../realtime/useEventStream";

/**
 * Notification — the M8.5 Notification Center's domain contract from the
 * backend (GET /company-profiles/{id}/notifications). Mirrors
 * app/schemas/notification.py's NotificationRead field-for-field, the
 * same "frontend type mirrors the backend read schema exactly" discipline
 * useAgentActivities.ts already established for AI Workforce.
 */
export type NotificationPriority = "low" | "medium" | "high" | "urgent";

export interface Notification {
  id: string;
  company_profile_id: string;
  event_id: string;
  user_id: string | null;
  title: string;
  message: string;
  priority: string;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

const POLL_INTERVAL_MS = 30_000;
// M8.6: how long to wait after the Event stream nudges us before
// actually re-fetching - a burst of several Events landing within the
// same second (common - one domain write often reports more than one
// Event) should trigger exactly one GET /notifications, not one per
// Event.
const STREAM_REFRESH_DEBOUNCE_MS = 500;

/**
 * Polls on a 30s cadence as a SAFETY NET, and - per the approved M8.6
 * architecture - also subscribes to the platform's live Event stream
 * (useEventStream) purely as a low-latency "something happened, go
 * check" nudge that triggers the same `refresh()` sooner. This
 * deliberately does NOT try to inspect the incoming Event's event_type/
 * category to decide "is this a notification" - that decision is made
 * exactly once, entirely server-side, by app/notifications/rules.py via
 * the Notification worker. Duplicating that logic here would be a
 * second, parallel decision engine, exactly what M8.5's approved
 * architecture (and M8.6's Decision 7) rules out. GET /notifications
 * stays the one and only authoritative source of what to display; the
 * stream only ever shortens how long it takes to notice something
 * changed there.
 */
export function useNotifications() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!activeCompanyId) {
      setNotifications([]);
      setIsLoading(false);
      return;
    }
    setError(null);
    apiClient
      .get<Notification[]>(`/company-profiles/${activeCompanyId}/notifications`, { params: { limit: 20 } })
      .then((res) => setNotifications(res.data))
      .catch(() => setError("Could not load notifications."))
      .finally(() => setIsLoading(false));
  }, [activeCompanyId]);

  useEffect(() => {
    if (companiesLoading) return;
    refresh();
  }, [companiesLoading, refresh]);

  useInterval(refresh, activeCompanyId ? POLL_INTERVAL_MS : null);

  // M8.6: the live nudge. Debounced (not called directly per-Event) so a
  // burst of several Events arriving together still produces one
  // request, not N.
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEventStream(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(refresh, STREAM_REFRESH_DEBOUNCE_MS);
  });
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  const markRead = useCallback(
    (notificationId: string) => {
      if (!activeCompanyId) return;
      // Optimistic - flips the local row immediately so the unread dot
      // updates without waiting on the round trip, then reconciles with
      // whatever the server actually persisted.
      setNotifications((prev) =>
        prev.map((n) => (n.id === notificationId ? { ...n, is_read: true, read_at: new Date().toISOString() } : n)),
      );
      apiClient
        .post<Notification>(`/company-profiles/${activeCompanyId}/notifications/${notificationId}/read`)
        .catch(() => refresh());
    },
    [activeCompanyId, refresh],
  );

  const markAllRead = useCallback(() => {
    if (!activeCompanyId) return;
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true, read_at: n.read_at ?? new Date().toISOString() })));
    apiClient
      .post<{ marked_count: number }>(`/company-profiles/${activeCompanyId}/notifications/mark-all-read`)
      .catch(() => refresh());
  }, [activeCompanyId, refresh]);

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return {
    notifications,
    unreadCount,
    isLoading: isLoading || companiesLoading,
    error,
    hasActiveCompany: Boolean(activeCompanyId),
    refresh,
    markRead,
    markAllRead,
  };
}
