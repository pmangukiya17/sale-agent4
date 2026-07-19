import { Card } from "../design-system";
import { PlaceholderNotice } from "./PlaceholderNotice";

/**
 * Mailbox Brief summary — Zone 3. M6 built Conversation/EmailMessage
 * backend models (ConversationStatus/MailboxSyncStatus/ReplyStatus all
 * exist in app/models/enums.py), but no `conversations` router is
 * registered in app/main.py - there is no REST API for this data at all
 * today. Real content lands with M8.7 once that API exists. Honest
 * placeholder, not a fabricated inbox summary.
 */
export function MailboxBrief() {
  return (
    <Card padding="compact" className="flex h-full flex-col gap-2">
      <h3 className="text-xs font-semibold text-slate-100">Mailbox Brief</h3>
      <PlaceholderNotice kind="not-implemented" reason="No conversations API exists yet - lands with M8.7." />
    </Card>
  );
}
