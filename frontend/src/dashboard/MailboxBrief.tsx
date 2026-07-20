import { Card } from "../design-system";
import { PlaceholderNotice } from "./PlaceholderNotice";

/**
 * Mailbox Brief summary — Zone 3. M6 built Conversation/EmailMessage
 * backend models (ConversationStatus/MailboxSyncStatus/ReplyStatus all
 * exist in app/models/enums.py), but no `conversations` router is
 * registered in app/main.py - there is no REST API for this data at all
 * today (re-confirmed during the M8.7 Phase C audit - still true).
 *
 * Note on the reason text below, corrected during that same audit: it
 * previously said real content "lands with M8.7," written speculatively
 * before M8.7's actual scope was defined. M8.7 (this milestone) is the
 * UI/UX design-system migration, not a new backend milestone - it does
 * not add a conversations API. A real conversations router remains
 * genuinely future, unscheduled work, not something to imply is already
 * arriving. Honest placeholder either way, not a fabricated inbox
 * summary.
 */
export function MailboxBrief() {
  return (
    <Card padding="compact" className="flex h-full flex-col gap-2">
      <h3 className="text-xs font-semibold text-slate-100">Mailbox Brief</h3>
      <PlaceholderNotice kind="not-implemented" reason="No conversations API route exists yet to summarize." />
    </Card>
  );
}
