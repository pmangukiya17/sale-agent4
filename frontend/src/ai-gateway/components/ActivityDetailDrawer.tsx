import { Link } from "react-router-dom";
import { SlideOver, StatusIndicator } from "../../design-system";
import type { StatusKind } from "../../design-system";
import { ProviderChip } from "./ProviderChip";
import { CostPill } from "./CostPill";
import type { ActivityLogEntry } from "../types";

/**
 * ActivityDetailDrawer — the first real consumer of `SlideOver` (see that
 * component's own docstring for why a right-edge panel, not `Modal`, was
 * chosen). Not one of the 8 explicitly-named reusable components in the
 * approved scope, but built to give SlideOver an actual purpose in this
 * milestone rather than shipping an unused primitive - SlideOver's own
 * stated purpose ("right-side inspector") is exactly this use case.
 *
 * Read-only in this milestone: shows the same fields the Activity table
 * row already carries, plus a link back to the routing decision for the
 * same capability (best-effort - Routing's mock data only has one
 * decision per capability today, not a full one-per-request history) and
 * a link to the owning agent's AI Workforce trace (routes to the
 * existing /ai-workforce page, does not modify it).
 */
const STATUS_DISPLAY: Record<ActivityLogEntry["status"], { kind: StatusKind; label: string }> = {
  success: { kind: "success", label: "Success" },
  waiting: { kind: "waiting", label: "Waiting for approval" },
  failed: { kind: "failed", label: "Failed" },
};

export function ActivityDetailDrawer({ entry, onClose }: { entry: ActivityLogEntry | null; onClose: () => void }) {
  const status = entry ? STATUS_DISPLAY[entry.status] : null;

  return (
    <SlideOver open={Boolean(entry)} onClose={onClose} title={entry?.capability}>
      {entry && status && (
        <div className="flex flex-col gap-4 text-sm">
          <StatusIndicator kind={status.kind} label={status.label} />

          <dl className="grid grid-cols-2 gap-3 text-xs text-slate-500">
            <div>
              <dt className="text-[10px] uppercase tracking-wide">Feature</dt>
              <dd className="mt-0.5 text-slate-200">{entry.feature}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wide">Agent</dt>
              <dd className="mt-0.5 text-slate-200">{entry.agent}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wide">Provider</dt>
              <dd className="mt-0.5">{entry.providerKey ? <ProviderChip providerKey={entry.providerKey} /> : "—"}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wide">Model</dt>
              <dd className="mt-0.5 text-slate-200">{entry.model ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wide">Cost</dt>
              <dd className="mt-0.5">
                <CostPill usd={entry.costUsd} />
              </dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wide">Latency</dt>
              <dd className="mt-0.5 tabular-nums text-slate-200">{entry.latencyMs ? `${entry.latencyMs}ms` : "—"}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wide">Company</dt>
              <dd className="mt-0.5 text-slate-200">{entry.companyName ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wide">Time</dt>
              <dd className="mt-0.5 text-slate-200">{new Date(entry.timestamp).toLocaleString()}</dd>
            </div>
          </dl>

          <div>
            <p className="text-[10px] uppercase tracking-wide text-slate-500">Routing chain</p>
            <p className="mt-1 text-xs text-slate-300">{entry.chainSummary}</p>
          </div>

          {entry.errorMessage && (
            <div>
              <p className="text-[10px] uppercase tracking-wide text-status-danger">Error</p>
              <p className="mt-1 text-xs text-status-danger">{entry.errorMessage}</p>
            </div>
          )}

          <div className="flex flex-col gap-1 border-t border-border-hairline pt-3 text-xs">
            <Link to="/ai-gateway/routing" className="text-accent-primary hover:underline">
              View routing for this capability →
            </Link>
            <Link to="/ai-workforce" className="text-accent-primary hover:underline">
              View agent trace →
            </Link>
          </div>
        </div>
      )}
    </SlideOver>
  );
}
