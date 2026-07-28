import { ArrowRight } from "lucide-react";
import { cn } from "../../design-system";
import type { RoutingNode } from "../types";

/**
 * RoutingChainVisualizer — (placeholder, per the approved M8.1 scope) a
 * first-pass, static rendering of how one Gateway request was actually
 * decided, replayed from real mock `RoutingDecision.nodes` data rather
 * than a fabricated generic diagram (the "honesty" principle from the
 * approved AI Gateway UI architecture doc, Section 0/4.4).
 *
 * Deliberately simplified relative to that doc's full spec for this
 * milestone: no one-shot connector pulse animation, no vertical-reflow-
 * on-mobile handling, no "replay a different capability" selector wired
 * to a live signal - those are explicitly deferred polish, not built
 * here, since "live updates" is out of scope and this component is
 * explicitly called out as a placeholder in the approved scope. What IS
 * real: each node's state (skipped / passed / terminal-*) is color-coded
 * using the same semantic vocabulary `StatusIndicator` uses elsewhere
 * (success/warning/danger/neutral), never color alone - every node also
 * carries a text label.
 */
const NODE_STYLES: Record<RoutingNode["state"], { border: string; bg: string; text: string }> = {
  skipped: { border: "border-border-hairline", bg: "bg-surface-2/40", text: "text-slate-600" },
  passed: { border: "border-border-hairline-strong", bg: "bg-surface-2", text: "text-slate-300" },
  "terminal-success": { border: "border-status-success/40", bg: "bg-status-success/10", text: "text-status-success" },
  "terminal-waiting": { border: "border-status-warning/40", bg: "bg-status-warning/10", text: "text-status-warning" },
  "terminal-failed": { border: "border-status-danger/40", bg: "bg-status-danger/10", text: "text-status-danger" },
};

export function RoutingChainVisualizer({ nodes }: { nodes: RoutingNode[] }) {
  return (
    <div className="flex flex-wrap items-stretch gap-2">
      {nodes.map((node, i) => {
        const style = NODE_STYLES[node.state];
        return (
          <div key={node.id} className="flex items-center gap-2">
            <div className={cn("min-w-[9rem] rounded-lg border p-2.5", style.border, style.bg)}>
              <p className={cn("text-xs font-medium", style.text)}>{node.label}</p>
              {node.detail && <p className="mt-0.5 text-[11px] text-slate-500">{node.detail}</p>}
            </div>
            {i < nodes.length - 1 && <ArrowRight className="h-3.5 w-3.5 shrink-0 text-slate-700" aria-hidden="true" />}
          </div>
        );
      })}
    </div>
  );
}
