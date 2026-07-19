import { useEffect, useRef } from "react";
import { apiClient, API_BASE_URL } from "../api/client";
import { useCompanies } from "../companies/CompanyContext";

/**
 * StreamedEvent - mirrors app/schemas/event.py's EventRead field-for-
 * field, same discipline as every other frontend type in this codebase
 * that mirrors a backend read schema (see useAgentActivities.ts's own
 * comment). This is the RAW platform Event, exactly as
 * GET /company-profiles/{id}/events already returns it - the stream is
 * just a live-push version of the same shape, not a different contract.
 */
export interface StreamedEvent {
  id: string;
  sequence_no: number;
  event_type: string;
  occurred_at: string;
  company_profile_id: string;
  subject_type: string | null;
  subject_id: string | null;
  payload: Record<string, unknown> | null;
  source: string;
  correlation_id: string | null;
  causation_id: string | null;
  actor_type: string | null;
  actor_id: string | null;
  severity: string | null;
  category: string | null;
  created_at: string;
}

type Subscriber = (event: StreamedEvent) => void;

const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 15000;

/**
 * One real connection to GET /company-profiles/{id}/event-stream, plus
 * every consumer currently interested in it. Deliberately NOT one
 * EventSource per calling component - CompanyStreamManager below hands
 * out the SAME instance to every caller for the same company_profile_id,
 * which is what "one shared Event stream, many consumers" (Command
 * Center, Notification Center, AI Workforce, future Analytics) actually
 * requires; a naive per-component `new EventSource(...)` in a plain hook
 * would open one physical connection per widget instead.
 *
 * Deliberately does NOT rely on EventSource's own native auto-reconnect.
 * Native reconnect retries the EXACT URL the EventSource was constructed
 * with - including the ticket query parameter baked into it at connect
 * time. Since stream tickets are short-lived by design (see
 * app/realtime/tickets.py's own docstring), a connection that drops
 * after the ticket has expired would have native auto-reconnect retrying
 * a now-permanently-rejected URL forever. Instead, `onerror` closes the
 * EventSource explicitly and schedules connect() again from scratch -
 * which mints a FRESH ticket first - with a capped exponential backoff.
 *
 * Reconnect is never a silent gap: connect() passes `since_sequence`
 * (the last sequence_no this connection has actually seen) on every
 * (re)connect, and the backend replays everything after it from `events`
 * before switching back to live tailing - see
 * app/api/routes/realtime.py's own `_stream_events()`.
 */
class CompanyStreamConnection {
  private eventSource: EventSource | null = null;
  private readonly subscribers = new Set<Subscriber>();
  private lastSequenceNo: number | null = null;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;

  constructor(private readonly companyProfileId: string) {
    void this.connect();
  }

  subscribe(callback: Subscriber): () => void {
    this.subscribers.add(callback);
    return () => {
      this.subscribers.delete(callback);
    };
  }

  private async connect(): Promise<void> {
    if (this.closed) return;
    try {
      const ticketRes = await apiClient.post<{ ticket: string }>(
        `/company-profiles/${this.companyProfileId}/event-stream/ticket`,
      );
      if (this.closed) return;

      const params = new URLSearchParams({ ticket: ticketRes.data.ticket });
      if (this.lastSequenceNo !== null) {
        params.set("since_sequence", String(this.lastSequenceNo));
      }
      const url = `${API_BASE_URL}/company-profiles/${this.companyProfileId}/event-stream?${params.toString()}`;

      const source = new EventSource(url);
      this.eventSource = source;

      source.onopen = () => {
        this.reconnectAttempt = 0;
      };

      source.onmessage = (message: MessageEvent<string>) => {
        try {
          const parsed = JSON.parse(message.data) as StreamedEvent;
          this.lastSequenceNo = parsed.sequence_no;
          this.subscribers.forEach((callback) => callback(parsed));
        } catch {
          // A malformed frame is dropped, not fatal - the connection
          // itself stays open and the next well-formed event continues
          // normally.
        }
      };

      source.onerror = () => {
        source.close();
        if (this.eventSource === source) this.eventSource = null;
        this.scheduleReconnect();
      };
    } catch {
      // Minting a ticket failed (e.g. briefly offline, or the access
      // token itself is momentarily stale) - back off and try again,
      // same as a dropped connection.
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (this.closed) return;
    const delay = Math.min(RECONNECT_BASE_DELAY_MS * 2 ** this.reconnectAttempt, RECONNECT_MAX_DELAY_MS);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => void this.connect(), delay);
  }

  close(): void {
    this.closed = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.eventSource?.close();
    this.eventSource = null;
  }
}

/**
 * One CompanyStreamConnection per company_profile_id, for the life of
 * the tab. Deliberately never torn down when a company profile's last
 * subscriber unmounts (switching between a couple of workspace tabs
 * shouldn't churn the connection) - a disclosed, accepted simplification
 * for this milestone, not an oversight: this project's realistic usage
 * (a handful of company profiles per user) is well within a browser's
 * per-origin concurrent-connection limit. Revisit only if a real user's
 * workflow ever actually exercises many distinct company profiles in one
 * session.
 */
const connections = new Map<string, CompanyStreamConnection>();

function getConnection(companyProfileId: string): CompanyStreamConnection {
  let connection = connections.get(companyProfileId);
  if (!connection) {
    connection = new CompanyStreamConnection(companyProfileId);
    connections.set(companyProfileId, connection);
  }
  return connection;
}

/**
 * Subscribes `onEvent` to the active company profile's live Event
 * stream, optionally pre-filtered by `filter`. Uses the same "saved
 * callback ref" shape as hooks/useInterval.ts (this codebase's own
 * existing polling-hook precedent) so callers can pass an inline
 * arrow function without resubscribing on every render.
 *
 * This is intentionally a thin, generic primitive - it delivers RAW
 * platform Events and nothing else. Per the approved M8.6 architecture,
 * it is each consumer's own job to decide what a given event_type/
 * category means to it (e.g. Notification Center does NOT use this to
 * detect "a Notification was created" - it uses this purely as a
 * low-latency nudge to re-fetch GET /notifications, the actual
 * authoritative source - see notifications/useNotifications.ts).
 */
export function useEventStream(onEvent: Subscriber, filter?: (event: StreamedEvent) => boolean): void {
  const { activeCompanyId } = useCompanies();
  const savedOnEvent = useRef(onEvent);
  const savedFilter = useRef(filter);

  useEffect(() => {
    savedOnEvent.current = onEvent;
    savedFilter.current = filter;
  }, [onEvent, filter]);

  useEffect(() => {
    if (!activeCompanyId) return;
    const connection = getConnection(activeCompanyId);
    const unsubscribe = connection.subscribe((event) => {
      if (!savedFilter.current || savedFilter.current(event)) {
        savedOnEvent.current(event);
      }
    });
    return unsubscribe;
  }, [activeCompanyId]);
}
