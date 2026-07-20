import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Badge } from "../design-system";

/**
 * TransitionalBanner — shared notice for pages kept reachable during a
 * migration but no longer the product's intended path (first use: the
 * legacy Company/Pipeline.tsx page, "Legacy"-badged in the Sidebar per the
 * M8.3 review). Deliberately generic (title/children only) so any future
 * deprecated-but-still-linked page can reuse it instead of writing its own
 * one-off notice.
 *
 * Restyled to the dark design-system tokens in M8.7 Phase E1, alongside
 * Pipeline.tsx itself moving off pre-M8 light styling - this component's
 * own prior docstring explicitly deferred that restyle "to a future CRM
 * milestone" so it wouldn't look like a stray dark fragment on a light
 * page; that milestone is this one. Same amber/warning semantic as
 * PlaceholderNotice's "not-implemented" treatment (status-warning at low
 * opacity), not a new warning-banner pattern invented separately -
 * Design Debt Budget, Section 10.1.
 */
export function TransitionalBanner({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-6 flex items-start gap-3 rounded-card border border-status-warning/30 bg-status-warning/5 p-4">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-status-warning" aria-hidden="true" />
      <div>
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-slate-100">{title}</p>
          <Badge tone="warning">Legacy</Badge>
        </div>
        <p className="mt-1 text-sm text-slate-400">{children}</p>
      </div>
    </div>
  );
}
