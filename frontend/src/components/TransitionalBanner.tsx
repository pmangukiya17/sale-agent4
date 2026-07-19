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
 * Rendered with plain Tailwind (amber-on-white), not the M8 dark design-
 * system tokens - Pipeline.tsx's surrounding page is still pre-M8 light
 * styling (that restyle is out of scope here, deferred to a future CRM
 * milestone), so this banner matches the page it actually sits inside
 * rather than looking like a stray dark-mode fragment on a light page.
 */
export function TransitionalBanner({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-6 flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
      <div>
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-amber-900">{title}</p>
          <Badge tone="warning">Legacy</Badge>
        </div>
        <p className="mt-1 text-sm text-amber-800">{children}</p>
      </div>
    </div>
  );
}
