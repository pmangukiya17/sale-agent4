import type { ReactNode } from "react";
import { Sidebar } from "../components/Sidebar";
import { TopCommandStrip } from "../components/TopCommandStrip";

/**
 * DashboardLayout — M8.2. The one shared shell every authenticated route
 * renders inside (see App.tsx - every <Route> still wraps its page
 * exactly the same way it did before this milestone; only what's INSIDE
 * this component changed).
 *
 * Known, deliberate transitional state, not a bug: this milestone flips
 * the shell's own canvas to the M8 dark surface tokens, but does NOT
 * restyle the 20 existing pages this wraps (Contacts, Pipeline, Settings,
 * etc.) - those still use their pre-M8 light-mode classNames internally,
 * so until each page's own milestone (M8.5–M8.10) lands, they render as
 * light content areas inside a dark shell. That's expected and disclosed
 * up front, per the M8.2 plan, not something to "fix" here - restyling
 * every page's internals is explicitly out of scope for a
 * shell-and-navigation milestone.
 */
export function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-surface-0">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopCommandStrip />
        <main className="flex-1 overflow-y-auto p-8">{children}</main>
      </div>
    </div>
  );
}
