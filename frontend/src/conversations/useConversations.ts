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
