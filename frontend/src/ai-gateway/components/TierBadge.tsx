import { Badge } from "../../design-system";
import type { BadgeTone } from "../../design-system";
import type { ProviderTier } from "../types";

/**
 * TierBadge — thin wrapper over the existing `Badge` primitive, per the
 * approved AI Gateway UI architecture (Section 6.1). No new Badge tone is
 * introduced: LOCAL reuses `info`, FREE reuses `success`, PREMIUM reuses
 * `warning` - deliberately chosen because those tones already carry this
 * meaning elsewhere in the app (success = safe/no-cost-consequence,
 * warning = "pay attention, this has a consequence"), so a user who has
 * never opened the AI Gateway zone still reads "Premium = caution"
 * correctly on first sight.
 */
const TIER_LABEL: Record<ProviderTier, string> = {
  local: "Local",
  free: "Free",
  premium: "Premium",
};

const TIER_TONE: Record<ProviderTier, BadgeTone> = {
  local: "info",
  free: "success",
  premium: "warning",
};

export function TierBadge({ tier, className }: { tier: ProviderTier; className?: string }) {
  return (
    <Badge tone={TIER_TONE[tier]} className={className}>
      {TIER_LABEL[tier]}
    </Badge>
  );
}
