import { Sparkles } from "lucide-react";
import { Card } from "../design-system";

/**
 * Shared placeholder for IA nodes the M8 Design Bible defines but whose
 * real content hasn't been built yet.
 *
 * Exists so M8.2 can ship the COMPLETE, real target navigation structure
 * now - every sidebar item goes somewhere real, none are dead links or
 * disabled-for-no-reason - without fabricating page content ahead of the
 * milestone that actually builds it. This is deliberately honest rather
 * than a fake preview: it states plainly what's missing, the same
 * "never fabricate information" discipline the Design Bible applies to
 * progress bars and live data (Section 5) applied here to navigation
 * itself.
 *
 * Each usage site (App.tsx) passes its own `milestone`/`title` - this
 * component itself has no knowledge of the roadmap beyond what it's told.
 * "Analytics"/"Reports" used to point here too (labeled "M8.9") - M8.9
 * shipped real content for both (see Analytics.tsx/Reports.tsx) and
 * App.tsx's routes for them no longer use this component at all.
 * "Conversations" also used to point here (labeled "M6.6" - see below
 * for why that was already wrong even at the time) - M6.5 shipped real
 * content for it (see Conversations.tsx) and App.tsx's route no longer
 * uses this component either. Only "Mailbox Brief" remains on this
 * placeholder today.
 *
 * "Mailbox Brief"/"Conversations" originally pointed at "M8.7" too, back
 * when M8.7 was assumed (at M8.2's time) to be the milestone that built
 * them - that assumption went stale the moment M8.7 was later redefined,
 * by explicit CEO review, as a pure UI/UX Design Bible implementation
 * milestone with no new backend feature work. M8.7 has now shipped and
 * did not build either page - the same stale-claim class of bug already
 * caught and fixed once in KpiStrip.tsx/MailboxBrief.tsx's
 * dashboard-widget placeholder text during M8.7 Phase C, just missed
 * here since this route lives in App.tsx, outside that audit's scope.
 *
 * "Conversations" was then mislabeled a second time as "M6.6" (this
 * document's original Phased Implementation Plan draft, before the M6.5
 * rescoping) - already stale by the time it was written here, since
 * Conversation UI shipped as **M6.5**, not M6.6. M6.6 is now the
 * project's finalized number for the CRM Automation milestone (see
 * docs/architecture/m6-reply-intelligence-plan.md section 14) - a
 * different scope entirely, unrelated to this page's own history.
 *
 * Mailbox Brief -> **M6** generally (Reply Intelligence & Conversation
 * Management), per m8-ui-ux-design-bible.md line 363 ("M5 Delivery
 * (mailbox activity) + M6 Reply Intelligence") and future-milestones.md's
 * note 9, which explicitly places it under M6, not M5, even after its
 * manual-only design was superseded by M6's persistent Conversation
 * model. No M6 sub-milestone has built it yet.
 *
 * Update (Track C5 + its Executive Daily Brief UX follow-up): Mailbox
 * Brief now has real content too (see MailboxBriefPage.tsx) - App.tsx's
 * `/mailbox-brief` route no longer uses this component. This file is
 * kept, unused, rather than deleted: every IA node this component was
 * ever built for now has real content, but the component itself remains
 * the correct pattern to reach for the next time a nav item ships ahead
 * of its content.
 */
export function ComingSoon({ title, milestone }: { title: string; milestone: string }) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Card className="max-w-md text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-accent-ai/10">
          <Sparkles className="h-6 w-6 text-accent-ai-soft" aria-hidden="true" />
        </div>
        <h1 className="text-lg font-semibold text-slate-100">{title}</h1>
        <p className="mt-2 text-sm text-slate-400">
          This page is part of the approved M8 Design Bible and arrives in <span className="font-medium text-slate-200">{milestone}</span>.
          Navigation is real today; the content behind it is built incrementally, one reviewed milestone at a time.
        </p>
      </Card>
    </div>
  );
}
