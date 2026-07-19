import { useState, type ReactNode } from "react";
import { cn } from "./cn";

/**
 * Tabs — new M8.3-polish primitive, added specifically to satisfy the
 * "single-screen Command Center" constraint (progressive disclosure
 * instead of stacking every widget vertically). Generic on purpose - the
 * Command Center's Zone 3 (Attention Deck) is the first caller, but this
 * is a plain tier-1 design-system component like Button/Card, meant to be
 * reused anywhere a page needs "several regions, one visible at a time"
 * (e.g. a future Research page's Overview/Financials/Products tabs per
 * Design Bible Section 9's page template).
 */
export interface TabItem {
  id: string;
  label: string;
  content: ReactNode;
}

export function Tabs({ items, defaultTabId, className }: { items: TabItem[]; defaultTabId?: string; className?: string }) {
  const [activeId, setActiveId] = useState(defaultTabId ?? items[0]?.id);
  const active = items.find((t) => t.id === activeId) ?? items[0];

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div role="tablist" className="flex shrink-0 gap-1 border-b border-border-hairline">
        {items.map((item) => (
          <button
            key={item.id}
            role="tab"
            aria-selected={item.id === active?.id}
            onClick={() => setActiveId(item.id)}
            className={cn(
              "border-b-2 px-3 py-2 text-xs font-medium transition-colors",
              item.id === active?.id
                ? "border-accent-primary text-slate-100"
                : "border-transparent text-slate-500 hover:text-slate-300"
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 pt-3">{active?.content}</div>
    </div>
  );
}
