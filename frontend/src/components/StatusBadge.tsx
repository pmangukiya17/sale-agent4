/**
 * Generalizes the STATUS_COLORS-per-page pattern already used across
 * DiscoveryJobs.tsx/ProspectOutreach.tsx/CompanyProducts.tsx into one
 * shared component. M5 alone adds five new status vocabularies
 * (ProviderConnectionStatus, DeliveryCampaignStatus,
 * DeliveryQueueItemStatus, DeliveryEventType, plus the existing ones) -
 * a sixth copy-pasted color map per page was the wrong level of
 * duplication to keep.
 *
 * Deliberately only shares the "what do 5 severity levels look like"
 * concern (the tone classes), not "which status string means what" -
 * each page still owns its own STATUS_TONE map, because that vocabulary
 * genuinely differs per domain (a Toggle's "active" isn't the same kind
 * of state as a DeliveryQueueItem's "retry").
 */

export type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger";

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
  info: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  success: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300",
  warning: "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300",
  danger: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
};

export function StatusBadge({ label, tone = "neutral" }: { label: string; tone?: BadgeTone }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]}`}>
      {label}
    </span>
  );
}
