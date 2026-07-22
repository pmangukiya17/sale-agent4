import { useState } from "react";
import { useNavigate } from "react-router-dom";
import DOMPurify from "dompurify";
import { Badge, Card, PlaceholderNotice, Table } from "../design-system";
import type { BadgeTone, TableColumn } from "../design-system";
import { useCompanies } from "../companies/CompanyContext";
import { useConversationDetail, useConversations } from "../conversations/useConversations";
import type { ConversationListItem, EmailMessage, ReplyStatus } from "../conversations/useConversations";

/**
 * Conversations — M6.5. Business-wide Conversation list + inline detail
 * (unified message timeline + AI insights), over the read-only
 * GET /conversations list+detail endpoints (M6.5 backend) - which
 * themselves only ever project data M6.1-M6.4 already write.
 *
 * Follows Reports.tsx's (M8.9) List -> Detail expand pattern rather than
 * introducing a new routed sub-page, and reuses the same
 * "select a business first" guard every Intelligence-zone page
 * (Analytics/Reports) already uses - Conversations sits in that same nav
 * zone, at the same global /conversations route, scoped internally via
 * the active company context rather than a URL company param (matching
 * Analytics.tsx/Reports.tsx's own established convention, not Discovery/
 * Research/Outreach/Delivery's URL-param convention).
 *
 * AI insights shown here are exactly the four M6.4 Reply Intelligence
 * fields (reply_status/last_reply_at/last_reply_from/needs_human_review)
 * - a rolling snapshot of the MOST RECENT reply only, per Conversation's
 * own docstring, never a per-message analysis history (no ReplyAnalysis
 * table exists - that was explicitly rejected at M6.4 approval).
 *
 * Deliberately NO Recommended Actions / Task panel - no Task table exists
 * yet (the CRM-updates milestone: relationship_stage state machine +
 * Task writes - is explicitly deferred, per this session's direction).
 * Showing an empty or fabricated "recommended action" here would violate
 * this project's "never fake state that doesn't exist yet" principle.
 */

const REPLY_STATUS_TONE: Record<ReplyStatus, BadgeTone> = {
  positive: "success",
  negative: "danger",
  neutral: "neutral",
  out_of_office: "info",
};

function ConversationsTable({
  conversations,
  isLoading,
  onSelect,
}: {
  conversations: ConversationListItem[];
  isLoading: boolean;
  onSelect: (id: string) => void;
}) {
  const columns: TableColumn<ConversationListItem>[] = [
    {
      key: "prospect",
      header: "Prospect",
      render: (c) => c.prospect?.name ?? "Unresolved sender",
      sortable: true,
      sortValue: (c) => c.prospect?.name ?? "",
    },
    {
      key: "subject",
      header: "Subject",
      render: (c) => c.subject ?? "—",
    },
    {
      key: "reply_status",
      header: "Latest reply",
      render: (c) =>
        c.reply_status ? (
          <Badge tone={REPLY_STATUS_TONE[c.reply_status]}>{c.reply_status.replace(/_/g, " ")}</Badge>
        ) : (
          <span className="text-xs text-slate-500">No reply yet</span>
        ),
      sortable: true,
      sortValue: (c) => c.reply_status ?? "",
    },
    {
      key: "needs_human_review",
      header: "Review",
      render: (c) => (c.needs_human_review ? <Badge tone="warning">Needs review</Badge> : null),
    },
    {
      key: "last_message_at",
      header: "Last activity",
      render: (c) => (c.last_message_at ? new Date(c.last_message_at).toLocaleString() : "—"),
      sortable: true,
      sortValue: (c) => c.last_message_at ?? "",
    },
  ];

  return (
    <Card>
      <h3 className="mb-1 font-semibold text-slate-100">Conversations</h3>
      <p className="mb-3 text-xs text-slate-500">
        Every threaded email conversation across this business's connected mailboxes.
      </p>
      {!isLoading && conversations.length === 0 ? (
        <PlaceholderNotice kind="no-data" reason="No conversations synced yet - connect a mailbox in Delivery to get started." />
      ) : (
        <Table
          columns={columns}
          rows={conversations}
          rowKey={(c) => c.id}
          isLoading={isLoading}
          onRowClick={(c) => onSelect(c.id)}
        />
      )}
    </Card>
  );
}

function MessageBubble({ message }: { message: EmailMessage }) {
  const sanitizedHtml = message.body_html ? DOMPurify.sanitize(message.body_html) : null;
  const isOutbound = message.direction === "outbound";

  return (
    <div className={`rounded-lg border p-3 text-sm ${isOutbound ? "border-accent-primary/30 bg-accent-primary/5" : "border-border-hairline bg-surface-2"}`}>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <Badge tone={isOutbound ? "primary" : "neutral"}>{isOutbound ? "Sent" : "Received"}</Badge>
        <span>{message.from_name ?? message.from_email ?? "Unknown sender"}</span>
        <span className="text-slate-600">via {message.provider}</span>
        {message.sent_at && <span>{new Date(message.sent_at).toLocaleString()}</span>}
      </div>
      {message.subject && <p className="mb-1 text-xs font-medium text-slate-400">{message.subject}</p>}
      {sanitizedHtml ? (
        <div className="text-slate-200" dangerouslySetInnerHTML={{ __html: sanitizedHtml }} />
      ) : (
        <p className="whitespace-pre-wrap text-slate-200">{message.body_text ?? "(no content)"}</p>
      )}
    </div>
  );
}

function ConversationDetailPanel({ companyId, conversationId }: { companyId: string; conversationId: string }) {
  const { detail, isLoading, error } = useConversationDetail(companyId, conversationId);

  if (isLoading) return <Card><p className="text-sm text-slate-500">Loading…</p></Card>;
  if (error) return <Card><p className="text-sm text-status-danger">{error}</p></Card>;
  if (!detail) return null;

  return (
    <div className="space-y-4">
      <Card>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium text-slate-200">{detail.subject ?? "(no subject)"}</p>
          {detail.needs_human_review && <Badge tone="warning">Needs review</Badge>}
        </div>

        {/* AI insights - exactly the four real M6.4 fields, a snapshot of
            the most recent reply only, never a per-message history. */}
        <div className="mb-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
          <div>
            <p className="font-medium text-slate-500">Latest reply</p>
            <p className="text-slate-300">
              {detail.reply_status ? (
                <Badge tone={REPLY_STATUS_TONE[detail.reply_status]}>{detail.reply_status.replace(/_/g, " ")}</Badge>
              ) : (
                "No reply yet"
              )}
            </p>
          </div>
          <div>
            <p className="font-medium text-slate-500">Last reply at</p>
            <p className="text-slate-300">{detail.last_reply_at ? new Date(detail.last_reply_at).toLocaleString() : "—"}</p>
          </div>
          <div>
            <p className="font-medium text-slate-500">Last reply from</p>
            <p className="text-slate-300">{detail.last_reply_from ?? "—"}</p>
          </div>
          <div>
            <p className="font-medium text-slate-500">Participants</p>
            <p className="text-slate-300">{detail.participants.map((p) => p.name ?? p.email).join(", ") || "—"}</p>
          </div>
        </div>
      </Card>

      <div className="space-y-2">
        {detail.messages.length === 0 ? (
          <PlaceholderNotice kind="no-data" reason="No messages synced for this conversation yet." />
        ) : (
          detail.messages.map((m) => <MessageBubble key={m.id} message={m} />)
        )}
      </div>
    </div>
  );
}

export default function Conversations() {
  const { conversations, isLoading, error, hasActiveCompany, activeCompanyId } = useConversations();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const navigate = useNavigate();

  if (!isLoading && !hasActiveCompany) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="max-w-md text-center">
          <h1 className="text-lg font-semibold text-slate-100">Select a business</h1>
          <p className="mt-2 text-sm text-slate-400">Conversations is scoped to one business at a time.</p>
          <button
            onClick={() => navigate("/businesses/new")}
            className="mt-4 rounded-lg bg-accent-primary px-4 py-2 text-sm font-medium text-white hover:bg-accent-primary/90"
          >
            Add your business
          </button>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="mb-1 text-h1 font-semibold text-slate-100">Conversations</h1>
        <p className="text-body text-slate-400">
          Every reply-threaded email conversation, unified across every connected mailbox and provider.
        </p>
      </div>

      {error && <p className="text-sm text-status-danger">{error}</p>}

      <ConversationsTable conversations={conversations} isLoading={isLoading} onSelect={setSelectedId} />

      {selectedId && activeCompanyId && <ConversationDetailPanel companyId={activeCompanyId} conversationId={selectedId} />}
    </div>
  );
}
