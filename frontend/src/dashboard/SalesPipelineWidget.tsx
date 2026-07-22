import { Card, PlaceholderNotice } from "../design-system";

/**
 * Sales Pipeline widget — Zone 2, blue (accent-primary), Design Bible
 * Section 8. The concepts show a granular deal-stage funnel (Qualified
 * Lead → Meeting → Sample → Quotation → Negotiation → Purchase Order →
 * Customer). That exact vocabulary - and any real deal/opportunity model
 * with a stage or monetary-value field - does not exist anywhere in the
 * backend (confirmed by reading every model in app/models/ and every enum
 * in app/models/enums.py).
 *
 * M8.3's first version showed the legacy M0 Company.stage distribution
 * here instead, honestly labeled as "the CRM company list." Per review,
 * that was still the wrong call: Company.stage is a different, disused
 * model (its own page, Pipeline.tsx, says outright "Discovery, scoring,
 * and outreach are not wired up yet") - presenting it in the dashboard's
 * flagship Sales Pipeline slot implied a working opportunity pipeline that
 * doesn't exist, even with an honest caption attached. Corrected: this
 * widget now states plainly that Opportunity Management isn't built yet,
 * rather than filling the slot with real-but-unrelated legacy data.
 *
 * A true deal/opportunity model with stage + value tracking is a real,
 * separate backend milestone - not something to fake or approximate here.
 *
 * Track B1 UI refinement: `accent="blue"` ambient identity glow only -
 * no `active` state. This is an honest "not implemented" placeholder
 * (see PlaceholderNotice below); giving it a breathing glow would imply
 * live activity that doesn't exist, the same reasoning this card's own
 * docstring already applies to what data it's allowed to show.
 */
export function SalesPipelineWidget() {
  return (
    <Card padding="compact" accent="blue" className="flex h-full flex-col gap-2">
      <h3 className="text-xs font-semibold text-accent-primary">Sales Pipeline</h3>
      <PlaceholderNotice kind="not-implemented" reason="No opportunity/deal model exists in the backend yet." />
    </Card>
  );
}
