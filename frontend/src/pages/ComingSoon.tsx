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
 * "Analytics"/"Reports" point at M8.9, a real numbered milestone already
 * on the roadmap. "Mailbox Brief"/"Conversations" originally pointed at
 * "M8.7" too, back when M8.7 was assumed (at M8.2's time) to be the
 * milestone that built them - that assumption went stale the moment
 * M8.7 was later redefined, by explicit CEO review, as a pure UI/UX
 * Design Bible implementation milestone with no new backend feature
 * work. M8.7 has now shipped and did not build either page, so those two
 * call sites were corrected to "a future milestone" rather than left
 * pointing at a milestone that already came and went without them - the
 * same stale-claim class of bug already caught and fixed once in
 * KpiStrip.tsx/MailboxBrief.tsx's dashboard-widget placeholder text
 * during M8.7 Phase C, just missed here since this route lives in
 * App.tsx, outside that audit's scope.
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
