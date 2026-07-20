import type { ReactNode } from "react";
import { Construction, Inbox } from "lucide-react";
import { cn } from "./cn";

/**
 * Shared honest empty-state primitive - the design system's one canonical
 * "empty/not-yet-available" treatment (Design Debt Budget, Section 10.1:
 * "one empty-state system"). Originally built under dashboard/ during
 * M8.3 (when it only had dashboard consumers); relocated here in M8.7
 * Phase E, before page migration began, once it was clear every migrated
 * CRM/Settings/AI-Workforce page needs the exact same primitive - Section
 * 9.1 says as much explicitly ("an empty Contacts list uses the same
 * branded-empty-state pattern as an empty Discovery results page").
 * Moved rather than left in dashboard/ for a second page to import
 * cross-folder, and moved rather than reimplemented a second time
 * elsewhere, per that same Design Debt Budget rule.
 *
 * "Empty" can mean two very different things, and per the M8.3 review
 * the UI must say which:
 *
 *  - "no-data": the capability/API is real, it's just genuinely empty
 *    right now (e.g. no prospects have been scored yet). Neutral tone,
 *    inbox icon - nothing is broken or missing, there's just nothing here.
 *  - "not-implemented": no backend capability exists for this yet (no
 *    router, no aggregate endpoint, no schema field). Amber/warning tone,
 *    construction icon - distinct on color AND icon AND text, never color
 *    alone, per Design Bible Section 12.
 *
 * Never used to dress up a fabricated number - the whole point of this
 * component is to say plainly which of the two is true instead of
 * guessing or hiding the distinction behind identical grey boxes.
 */
export type PlaceholderKind = "no-data" | "not-implemented";

const KIND_STYLES: Record<PlaceholderKind, { icon: typeof Inbox; border: string; bg: string; text: string; iconColor: string }> = {
  "no-data": {
    icon: Inbox,
    border: "border-border-hairline-strong",
    bg: "bg-surface-2/50",
    text: "text-slate-500",
    iconColor: "text-slate-500",
  },
  "not-implemented": {
    icon: Construction,
    border: "border-status-warning/30",
    bg: "bg-status-warning/5",
    text: "text-slate-400",
    iconColor: "text-status-warning",
  },
};

export function PlaceholderNotice({
  kind = "not-implemented",
  reason,
  children,
}: {
  kind?: PlaceholderKind;
  reason: string;
  children?: ReactNode;
}) {
  const style = KIND_STYLES[kind];
  const Icon = style.icon;
  return (
    <div className={cn("flex items-start gap-2 rounded-lg border border-dashed p-3 text-xs", style.border, style.bg, style.text)}>
      <Icon className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", style.iconColor)} aria-hidden="true" />
      <div>
        <p className="font-medium">{kind === "no-data" ? "No data yet" : "Capability not yet implemented"}</p>
        <p className="mt-0.5">{reason}</p>
        {children}
      </div>
    </div>
  );
}
