import { Card, PlaceholderNotice } from "../design-system";
import { useMailboxBrief } from "./useMailboxBrief";

/**
 * Mailbox Brief summary — Zone 3. Track C5 (dashboard-capabilities-
 * architecture-plan.md, Section 6): wired to a real, persisted,
 * on-demand executive summary - the final placeholder this project's
 * six-capability dashboard review set out to resolve.
 *
 * Per the CEO's explicit persistence model: this card never generates a
 * brief on page load - it only ever reads whatever was last saved
 * (useMailboxBrief.ts's own `refresh`, a plain GET). A brief is only
 * ever created by the "Generate New Brief" button below, which calls
 * the dedicated POST .../mailbox-brief/generate action - the same
 * "real cost, explicit user click, never a silent background fetch"
 * privacy posture `future-milestones.md` note 9 originally specified for
 * this exact capability.
 *
 * The brief itself is a pure PROJECTION over Conversation/Recommendation/
 * Opportunity data this project already had (see
 * app/mailbox_brief/context.py) - no raw email content is ever stored
 * or displayed here, only the AI's generated summary text and the
 * numeric context it was computed from (`statistics`).
 *
 * Track B1 UI refinement (superseded by this track for `active`, kept
 * for `accent`): `accent="orange"` ambient identity glow. `active` now
 * fires on a real brief existing (the same "never fabricate liveliness"
 * rule already applied elsewhere), not on an honest placeholder.
 */
export function MailboxBrief() {
  const { brief, isLoading, isGenerating, error, generate } = useMailboxBrief();

  return (
    <Card padding="compact" accent="orange" active={!isLoading && Boolean(brief)} className="flex h-full flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold text-slate-100">Mailbox Brief</h3>
        <button
          onClick={generate}
          disabled={isGenerating}
          className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium text-accent-primary hover:bg-surface-2 disabled:opacity-50"
        >
          {isGenerating ? "Generating…" : brief ? "Regenerate" : "Generate Brief"}
        </button>
      </div>
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : error ? (
        <PlaceholderNotice kind="no-data" reason={error} />
      ) : !brief ? (
        <PlaceholderNotice kind="no-data" reason="No brief has been generated yet - click Generate Brief to create the first one." />
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-hidden">
          <p className="text-[10px] text-slate-500">
            Generated {new Date(brief.generated_at).toLocaleString()} · {brief.ai_provider}/{brief.ai_model}
          </p>
          <p className="line-clamp-3 text-xs text-slate-300">{brief.summary}</p>
          {brief.recommendations.length > 0 && (
            <ul className="space-y-1 overflow-y-auto">
              {brief.recommendations.slice(0, 3).map((rec, i) => (
                <li key={i} className="truncate rounded px-1.5 py-1 text-[11px] text-slate-300 bg-surface-2/50">
                  {rec.title}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}
