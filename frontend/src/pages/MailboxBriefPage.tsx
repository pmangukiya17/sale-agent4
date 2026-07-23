import type { ComponentType } from "react";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Clock, Mail, Sparkles, TrendingUp, Users } from "lucide-react";
import { Badge, Card, PlaceholderNotice } from "../design-system";
import type { BadgeTone } from "../design-system";
import { useCompanies } from "../companies/CompanyContext";
import { useMailboxBrief } from "../dashboard/useMailboxBrief";
import { useConversations, useCompanyTasks } from "../conversations/useConversations";
import type { ReplyStatus, Task, TaskPriority } from "../conversations/useConversations";
import { useRecommendationsPortfolio } from "../dashboard/useRecommendationsPortfolio";
import type { PortfolioRecommendation } from "../dashboard/useRecommendationsPortfolio";
import { useOpportunityFunnel } from "../dashboard/useOpportunityFunnel";
import { useOpportunityPipelineValue } from "../dashboard/useOpportunityPipelineValue";

/**
 * MailboxBriefPage — the Executive Daily Brief. Frontend/UI-only follow-up
 * requested after the CEO's Track C5 approval: Track C5 itself (backend,
 * schema, persistence, generate/regenerate API) is unchanged - this page
 * is a PRESENTATION redesign of the dedicated `/mailbox-brief` route,
 * which previously rendered `ComingSoon` (see that component's own
 * docstring - Mailbox Brief was the last placeholder route in the app).
 *
 * Explicit constraints honored here (per the CEO's own instructions):
 * no new backend route, no schema change, no new persistence, no
 * duplicate business logic. Every section below is either (a) the
 * existing Mailbox Brief API's own stored data (useMailboxBrief.ts,
 * unchanged - Executive Summary section), or (b) an ALREADY-SHIPPED,
 * ALREADY-TENANT-SCOPED read endpoint this project built in an earlier
 * track, called through its existing hook:
 *   - Urgent Replies       -> useConversations() (M6.5), filtered client-
 *                             side for needs_human_review - the exact
 *                             same field Conversations.tsx's own table
 *                             already surfaces, just re-sorted here.
 *   - Follow-ups Due       -> useCompanyTasks() (new hook, this follow-
 *                             up only - see its own docstring in
 *                             conversations/useConversations.ts: same
 *                             GET .../tasks endpoint useProspectTasks
 *                             already calls, just without the
 *                             prospect_id filter it always supported).
 *   - Potential Buyers /
 *     AI Recommendations   -> useRecommendationsPortfolio() (Track C2),
 *                             extended with an optional `status` param
 *                             that passes through to a query param the
 *                             backend route already accepted (see that
 *                             hook's own updated docstring) - one fetch,
 *                             rendered twice (bucketed by confidence for
 *                             Potential Buyers, flat by type for AI
 *                             Recommendations), not two separate calls.
 *   - Pipeline Snapshot    -> useOpportunityFunnel()/
 *                             useOpportunityPipelineValue() (Track C4) -
 *                             literally "reuse C4 output," unchanged.
 *
 * The persisted Mailbox Brief's own `recommendations` array (the frozen
 * snapshot Track C5 stores at generation time) is deliberately NOT
 * re-rendered a second time here - the live sections above already
 * supersede it with current data, and showing both side by side would
 * invite exactly the "why do these two lists disagree" confusion a
 * frozen snapshot next to a live view always risks. Executive Summary
 * below shows only the generated paragraph itself plus its own
 * generated_at/provider attribution, with a one-line note explaining
 * that it reflects the workspace at the moment it was generated, not
 * necessarily this instant - the same honesty this project has applied
 * to every other frozen-vs-live distinction (e.g. Track C4's revenue
 * pipeline commentary).
 *
 * Section markers: the CEO's own instructions used colored circle
 * emoji (🔴/🟡/🟢/📈/🤖/📬) to lay out the six sections. Rendered here as
 * colored Lucide icons + matching semantic color instead of literal
 * emoji glyphs - this codebase's own established icon vocabulary
 * (Sidebar nav, KPI cards, every section header on every other page) is
 * Lucide, never emoji, and Design Bible Section 12 already requires
 * "distinct on color AND icon AND text, never color alone." This is a
 * one-for-one translation of the CEO's own color-coded structure (red/
 * amber/green/blue/purple/cyan), not a deviation from the request - purple
 * for AI Recommendations also reinforces this project's own pre-existing
 * "AI-attributed = accent-ai/purple" rule (Design Bible Section 4.1)
 * rather than introducing a new meaning for that color.
 */

const REPLY_STATUS_TONE: Record<ReplyStatus, BadgeTone> = {
  positive: "success",
  negative: "danger",
  neutral: "neutral",
  out_of_office: "info",
};

const TASK_PRIORITY_TONE: Record<TaskPriority, BadgeTone> = {
  low: "neutral",
  normal: "info",
  high: "warning",
};

const FUNNEL_SEQUENCE = [
  "qualified_lead",
  "meeting",
  "sample",
  "quotation",
  "negotiation",
  "purchase_order",
] as const;

const STAGE_LABELS: Record<string, string> = {
  qualified_lead: "Qualified Lead",
  meeting: "Meeting",
  sample: "Sample",
  quotation: "Quotation",
  negotiation: "Negotiation",
  purchase_order: "Purchase Order",
  closed_won: "Won",
};

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "no activity yet";
  const diffMs = Date.now() - new Date(iso).getTime();
  if (diffMs < 0) return new Date(iso).toLocaleString();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function formatCurrencyValue(value: number, currency: string | null): string {
  if (!currency) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
  } catch {
    return `${value.toLocaleString(undefined, { maximumFractionDigits: 0 })} ${currency}`;
  }
}

function SectionHeader({
  icon: Icon,
  iconClassName,
  bgClassName,
  title,
  subtitle,
}: {
  icon: ComponentType<{ className?: string }>;
  iconClassName: string;
  bgClassName: string;
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="mb-3 flex items-center gap-2.5">
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${bgClassName}`}>
        <Icon className={`h-3.5 w-3.5 ${iconClassName}`} />
      </span>
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
        {subtitle && <p className="truncate text-xs text-slate-500">{subtitle}</p>}
      </div>
    </div>
  );
}

function UrgentRepliesSection() {
  const { conversations, isLoading, error } = useConversations();
  const urgent = useMemo(
    () =>
      conversations
        .filter((c) => c.needs_human_review)
        .sort((a, b) => (b.last_reply_at ?? "").localeCompare(a.last_reply_at ?? ""))
        .slice(0, 8),
    [conversations]
  );
  const navigate = useNavigate();

  return (
    <Card>
      <SectionHeader
        icon={AlertTriangle}
        iconClassName="text-status-danger"
        bgClassName="bg-status-danger/10"
        title="Urgent Replies"
        subtitle="Conversations flagged for human review, most recent first"
      />
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : error ? (
        <PlaceholderNotice kind="no-data" reason={error} />
      ) : urgent.length === 0 ? (
        <PlaceholderNotice kind="no-data" reason="Nothing needs immediate attention right now - no conversations are flagged for human review." />
      ) : (
        <ul className="space-y-1.5">
          {urgent.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => navigate("/conversations")}
                className="flex w-full items-center justify-between gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-surface-2"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-slate-200">{c.prospect?.name ?? "Unresolved sender"}</span>
                  <span className="block truncate text-xs text-slate-500">{c.subject ?? "(no subject)"}</span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {c.reply_status && <Badge tone={REPLY_STATUS_TONE[c.reply_status]}>{c.reply_status.replace(/_/g, " ")}</Badge>}
                  <span className="text-xs text-slate-500">{formatRelativeTime(c.last_reply_at)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function FollowUpsDueSection() {
  const { tasks, isLoading, error } = useCompanyTasks();
  const navigate = useNavigate();
  const dueSoon = useMemo(() => {
    const priorityRank: Record<TaskPriority, number> = { high: 0, normal: 1, low: 2 };
    return [...tasks]
      .sort((a, b) => priorityRank[a.priority] - priorityRank[b.priority] || b.created_at.localeCompare(a.created_at))
      .slice(0, 8);
  }, [tasks]);

  return (
    <Card>
      <SectionHeader
        icon={Clock}
        iconClassName="text-status-warning"
        bgClassName="bg-status-warning/10"
        title="Follow-ups Due"
        subtitle="Pending Recommended Actions, highest priority first"
      />
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : error ? (
        <PlaceholderNotice kind="no-data" reason={error} />
      ) : dueSoon.length === 0 ? (
        <PlaceholderNotice kind="no-data" reason="No follow-ups pending - every Recommended Action has been completed or dismissed." />
      ) : (
        <ul className="space-y-1.5">
          {dueSoon.map((t: Task) => (
            <li key={t.id}>
              <button
                onClick={() => navigate("/conversations")}
                className="flex w-full items-start justify-between gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-surface-2"
              >
                <span className="min-w-0 flex-1 truncate text-sm text-slate-200">{t.suggested_action}</span>
                <span className="flex shrink-0 items-center gap-2">
                  <Badge tone={TASK_PRIORITY_TONE[t.priority]}>{t.priority}</Badge>
                  <span className="text-xs text-slate-500">requested {formatRelativeTime(t.created_at)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/**
 * Buckets the same NEW-status recommendation list Potential Buyers and
 * AI Recommendations both consume (one fetch, no duplicate network call
 * - see this page's own top-level docstring). `confidence` is a real
 * 0.0-1.0 field the Research Engine already writes (never fabricated
 * here) - high/medium thresholds are a presentational choice, not a new
 * business rule, and a recommendation with no confidence score yet
 * (`confidence === null`, a genuinely real, honest state - not every
 * recommendation gets scored) is grouped into "New opportunities" rather
 * than silently treated as zero.
 */
function bucketByConfidence(recs: PortfolioRecommendation[]) {
  const high = recs.filter((r) => r.confidence !== null && r.confidence >= 0.7);
  const medium = recs.filter((r) => r.confidence !== null && r.confidence >= 0.4 && r.confidence < 0.7);
  const newOpportunities = recs.filter((r) => r.confidence === null || r.confidence < 0.4);
  return { high, medium, newOpportunities };
}

function PotentialBuyersSection({ recommendations, isLoading, error }: { recommendations: PortfolioRecommendation[]; isLoading: boolean; error: string | null }) {
  const navigate = useNavigate();
  const { high, medium, newOpportunities } = useMemo(() => bucketByConfidence(recommendations), [recommendations]);

  const tiers: { label: string; tone: BadgeTone; rows: PortfolioRecommendation[] }[] = [
    { label: "High priority", tone: "success", rows: high },
    { label: "Medium priority", tone: "warning", rows: medium },
    { label: "New opportunities", tone: "neutral", rows: newOpportunities },
  ];

  return (
    <Card>
      <SectionHeader
        icon={Users}
        iconClassName="text-status-success"
        bgClassName="bg-status-success/10"
        title="Potential Buyers"
        subtitle="Prospects with an open, not-yet-actioned AI recommendation"
      />
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : error ? (
        <PlaceholderNotice kind="no-data" reason={error} />
      ) : recommendations.length === 0 ? (
        <PlaceholderNotice kind="no-data" reason="No open recommendations yet - the AI Analysis Engine hasn't flagged any prospects for this business." />
      ) : (
        <div className="space-y-3">
          {tiers.map(
            (tier) =>
              tier.rows.length > 0 && (
                <div key={tier.label}>
                  <div className="mb-1 flex items-center gap-1.5">
                    <Badge tone={tier.tone}>{tier.label}</Badge>
                    <span className="text-xs text-slate-500">{tier.rows.length}</span>
                  </div>
                  <ul className="space-y-1">
                    {tier.rows.slice(0, 5).map((rec) => (
                      <li key={rec.id}>
                        <button
                          onClick={() => navigate("/businesses/" + rec.prospect.id + "/discovery/prospects")}
                          className="flex w-full items-center justify-between gap-3 rounded-lg px-2 py-1 text-left hover:bg-surface-2"
                        >
                          <span className="min-w-0 flex-1 truncate text-sm text-slate-200">{rec.prospect.name}</span>
                          {rec.confidence !== null && (
                            <span className="shrink-0 text-xs text-slate-500">{Math.round(rec.confidence * 100)}%</span>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )
          )}
        </div>
      )}
    </Card>
  );
}

function PipelineSnapshotSection() {
  const { funnel, isLoading: funnelLoading, error: funnelError } = useOpportunityFunnel();
  const { breakdown, isLoading: pvLoading, error: pvError } = useOpportunityPipelineValue();
  const isLoading = funnelLoading || pvLoading;
  const error = funnelError ?? pvError;

  const byStage = Object.fromEntries(funnel.map((row) => [row.stage, row]));
  const activeCount = FUNNEL_SEQUENCE.reduce((sum, stage) => sum + (byStage[stage]?.count ?? 0), 0);
  const wonCount = byStage["closed_won"]?.count ?? 0;
  const lostCount = byStage["closed_lost"]?.count ?? 0;
  const hasAnyOpportunity = activeCount + wonCount + lostCount > 0;

  return (
    <Card>
      <SectionHeader
        icon={TrendingUp}
        iconClassName="text-accent-primary"
        bgClassName="bg-accent-primary/10"
        title="Pipeline Snapshot"
        subtitle="Reusing the same funnel and per-currency revenue data as the Command Center"
      />
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : error ? (
        <PlaceholderNotice kind="no-data" reason={error} />
      ) : !hasAnyOpportunity ? (
        <PlaceholderNotice kind="no-data" reason="No opportunities yet - the pipeline is real, there's just nothing in it." />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <p className="text-xs text-slate-500">Active opportunities</p>
            <p className="text-2xl font-semibold text-slate-100">{activeCount}</p>
            <p className="mt-1 text-xs text-slate-500">
              {wonCount} won · {lostCount} lost
            </p>
          </div>
          <div>
            <p className="mb-1 text-xs text-slate-500">Revenue by currency (open pipeline)</p>
            {breakdown.length === 0 ? (
              <p className="text-xs text-slate-500">No revenue recorded yet.</p>
            ) : (
              <ul className="space-y-0.5">
                {breakdown.map((row) => (
                  <li key={row.currency ?? "none"} className="text-sm text-slate-200">
                    {formatCurrencyValue(row.open_pipeline_value, row.currency)}
                    {row.currency === null && <span className="ml-1 text-xs text-slate-500">(no currency set)</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <p className="mb-1 text-xs text-slate-500">Funnel</p>
            <ul className="space-y-0.5">
              {FUNNEL_SEQUENCE.map((stage) => (
                <li key={stage} className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">{STAGE_LABELS[stage]}</span>
                  <span className="flex items-center gap-1.5">
                    {byStage[stage]?.conversion_rate_from_previous != null && (
                      <span className="text-slate-600">{byStage[stage].conversion_rate_from_previous}%</span>
                    )}
                    <span className="font-medium text-slate-200">{byStage[stage]?.count ?? 0}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Card>
  );
}

function AiRecommendationsSection({ recommendations, isLoading, error }: { recommendations: PortfolioRecommendation[]; isLoading: boolean; error: string | null }) {
  const navigate = useNavigate();
  return (
    <Card>
      <SectionHeader
        icon={Sparkles}
        iconClassName="text-accent-ai-soft"
        bgClassName="bg-accent-ai/10"
        title="AI Recommendations"
        subtitle="Existing recommendation engine output, most recent first"
      />
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : error ? (
        <PlaceholderNotice kind="no-data" reason={error} />
      ) : recommendations.length === 0 ? (
        <PlaceholderNotice kind="no-data" reason="No recommendations yet - the AI Analysis Engine hasn't generated any for this business." />
      ) : (
        <ul className="space-y-1.5">
          {recommendations.slice(0, 8).map((rec) => (
            <li key={rec.id}>
              <button
                onClick={() => navigate("/businesses/" + rec.prospect.id + "/discovery/prospects")}
                className="flex w-full items-center justify-between gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-surface-2"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-slate-200">{rec.title}</span>
                  <span className="block truncate text-xs text-slate-500">{rec.prospect.name}</span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {rec.confidence !== null && <span className="text-xs text-slate-500">{Math.round(rec.confidence * 100)}%</span>}
                  <Badge tone="ai">{rec.recommendation_type.replace(/_/g, " ")}</Badge>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function ExecutiveSummarySection() {
  const { brief, isLoading, isGenerating, error, generate } = useMailboxBrief();

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between gap-3">
        <SectionHeader
          icon={Mail}
          iconClassName="text-accent-secondary"
          bgClassName="bg-accent-secondary/10"
          title="Executive Summary"
        />
        <button
          onClick={generate}
          disabled={isGenerating}
          className="shrink-0 rounded-lg bg-accent-primary px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-primary/90 disabled:opacity-50"
        >
          {isGenerating ? "Generating…" : brief ? "Regenerate Brief" : "Generate Brief"}
        </button>
      </div>
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : error ? (
        <PlaceholderNotice kind="no-data" reason={error} />
      ) : !brief ? (
        <PlaceholderNotice kind="no-data" reason="No brief has been generated yet - click Generate Brief above to create the first one." />
      ) : (
        <>
          <p className="text-sm leading-relaxed text-slate-200">{brief.summary}</p>
          <p className="mt-3 text-xs text-slate-500">
            Generated {new Date(brief.generated_at).toLocaleString()} · {brief.ai_provider}/{brief.ai_model} · reflects the
            workspace as of that moment, not necessarily this instant - the sections above are always live.
          </p>
        </>
      )}
    </Card>
  );
}

export default function MailboxBriefPage() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const navigate = useNavigate();
  const { recommendations, isLoading: recsLoading, error: recsError } = useRecommendationsPortfolio(20, "new");

  if (!companiesLoading && !activeCompanyId) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="max-w-md text-center">
          <h1 className="text-lg font-semibold text-slate-100">Select a business</h1>
          <p className="mt-2 text-sm text-slate-400">The Executive Daily Brief is scoped to one business at a time.</p>
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
    <div>
      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Executive Daily Brief</h1>
      <p className="mb-6 text-body text-slate-400">
        Your AI Sales Manager's morning briefing - urgent items, buyers to watch, and pipeline health, all reusing data
        this project's own dashboard already computes. Nothing here is estimated or simulated.
      </p>

      <div className="space-y-4">
        <UrgentRepliesSection />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <FollowUpsDueSection />
          <PotentialBuyersSection recommendations={recommendations} isLoading={recsLoading} error={recsError} />
        </div>
        <PipelineSnapshotSection />
        <AiRecommendationsSection recommendations={recommendations} isLoading={recsLoading} error={recsError} />
        <ExecutiveSummarySection />
      </div>
    </div>
  );
}
