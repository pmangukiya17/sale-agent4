import { useCallback, useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { useCompanies } from "../companies/CompanyContext";

/**
 * useConversations — M6.5 (Conversations UI). Same "fetch the list,
 * fetch a selected row's detail on demand" pattern already established
 * by useOutreachHistory.ts (M8.9)/Reports.tsx's expand pattern, over the
 * new, real GET /conversations list+detail endpoints (M6.5 backend) -
 * themselves read-only projections of data M6.1-M6.4 already write
 * (Conversation/EmailMessage/ConversationParticipant, reply_status/
 * needs_human_review/last_reply_at/last_reply_from).
 *
 * Deliberately no "Recommended Actions" / Task data anywhere in this
 * hook - no Task table exists yet (the CRM-updates milestone - relationship_stage
 * state machine + Task writes - is explicitly deferred). This hook only
 * ever surfaces fields that are real today.
 */

export type ReplyStatus = "positive" | "negative" | "neutral" | "out_of_office";

export interface ConversationProspectSummary {
  id: string;
  name: string;
}

export interface ConversationListItem {
  id: string;
  company_profile_id: string;
  prospect_id: string | null;
  prospect: ConversationProspectSummary | null;
  subject: string | null;
  status: "open" | "closed";
  last_message_at: string | null;
  reply_status: ReplyStatus | null;
  last_reply_at: string | null;
  last_reply_from: string | null;
  needs_human_review: boolean;
  created_at: string;
}

export interface ConversationParticipant {
  id: string;
  email: string;
  name: string | null;
  role: "to" | "cc" | "from";
  prospect_contact_id: string | null;
}

export interface EmailMessage {
  id: string;
  provider: string;
  direction: "outbound" | "inbound";
  from_email: string | null;
  from_name: string | null;
  subject: string | null;
  body_text: string | null;
  body_html: string | null;
  sent_at: string | null;
  received_at: string | null;
  has_attachments: boolean;
}

export interface ConversationDetail extends ConversationListItem {
  participants: ConversationParticipant[];
  messages: EmailMessage[];
}

export type TaskPriority = "low" | "normal" | "high";
export type TaskStatus = "pending" | "completed" | "dismissed";

export interface Task {
  id: string;
  company_profile_id: string;
  prospect_id: string;
  prospect_contact_id: string | null;
  conversation_id: string | null;
  assigned_user_id: string | null;
  suggested_action: string;
  source_event_type: string;
  priority: TaskPriority;
  status: TaskStatus;
  resolved_at: string | null;
  created_at: string;
}

export function useConversations() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!activeCompanyId) {
      setConversations([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    apiClient
      .get<ConversationListItem[]>(`/company-profiles/${activeCompanyId}/conversations`)
      .then((res) => setConversations(res.data))
      .catch(() => setError("Could not load conversations."))
      .finally(() => setIsLoading(false));
  }, [activeCompanyId]);

  useEffect(() => {
    if (companiesLoading) return;
    refresh();
  }, [companiesLoading, refresh]);

  return {
    conversations,
    isLoading: isLoading || companiesLoading,
    error,
    hasActiveCompany: Boolean(activeCompanyId),
    activeCompanyId,
    refresh,
  };
}

export function useConversationDetail(companyId: string | undefined, conversationId: string | null) {
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!companyId || !conversationId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    apiClient
      .get<ConversationDetail>(`/company-profiles/${companyId}/conversations/${conversationId}`)
      .then((res) => {
        if (!cancelled) setDetail(res.data);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load this conversation.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [companyId, conversationId]);

  return { detail, isLoading, error };
}

/**
 * useProspectTasks — M6.6 (CRM Automation). Fetches real, persisted Task
 * (Recommended Action) rows for one prospect from the read-only
 * GET /tasks endpoint - never computes or fabricates a suggestion
 * itself (see Conversations.tsx's own docstring for that boundary).
 * Scoped by prospect_id rather than conversation_id: a Task can be
 * account-level (e.g. a relationship_stage advance with no single
 * message behind it), so this intentionally surfaces every open
 * Recommended Action for the prospect a conversation belongs to, not
 * only ones tied to this exact thread.
 */
export function useProspectTasks(companyId: string | undefined, prospectId: string | null | undefined) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!companyId || !prospectId) {
      setTasks([]);
      return;
    }
    setIsLoading(true);
    setError(null);
    apiClient
      .get<Task[]>(`/company-profiles/${companyId}/tasks`, { params: { prospect_id: prospectId } })
      .then((res) => setTasks(res.data))
      .catch(() => setError("Could not load recommended actions."))
      .finally(() => setIsLoading(false));
  }, [companyId, prospectId]);

  useEffect(refresh, [refresh]);

  const completeTask = useCallback(
    async (taskId: string) => {
      if (!companyId) return;
      await apiClient.post(`/company-profiles/${companyId}/tasks/${taskId}/complete`);
      refresh();
    },
    [companyId, refresh]
  );

  const dismissTask = useCallback(
    async (taskId: string) => {
      if (!companyId) return;
      await apiClient.post(`/company-profiles/${companyId}/tasks/${taskId}/dismiss`);
      refresh();
    },
    [companyId, refresh]
  );

  return { tasks, isLoading, error, completeTask, dismissTask };
}

/**
 * useCompanyTasks — Executive Daily Brief UX follow-up (Track C5, post-
 * approval). Same read-only GET /company-profiles/{id}/tasks endpoint
 * useProspectTasks already calls, just without a `prospect_id` filter -
 * this is an EXISTING, already-shipped, already-tenant-scoped backend
 * route (app/api/routes/tasks.py's `list_tasks`, which has always
 * accepted an optional `prospect_id`, never required one); this hook
 * adds no new backend surface, it only exercises a query-param
 * combination the frontend never called before. Backs the Executive
 * Daily Brief's "Follow-ups Due" section - every PENDING Recommended
 * Action across the whole business, not just one prospect's - since a
 * morning briefing is a portfolio-wide view by definition, the same
 * reasoning useRecommendationsPortfolio.ts (Track C2) already gave for
 * needing its own cross-portfolio fetch instead of one call per
 * prospect.
 */
export function useCompanyTasks() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!activeCompanyId) {
      setTasks([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    apiClient
      .get<Task[]>(`/company-profiles/${activeCompanyId}/tasks`, { params: { status: "pending" } })
      .then((res) => setTasks(res.data))
      .catch(() => setError("Could not load recommended actions."))
      .finally(() => setIsLoading(false));
  }, [activeCompanyId]);

  useEffect(() => {
    if (companiesLoading) return;
    refresh();
  }, [companiesLoading, refresh]);

  return {
    tasks,
    isLoading: isLoading || companiesLoading,
    error,
    hasActiveCompany: Boolean(activeCompanyId),
    refresh,
  };
}
