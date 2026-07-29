import { AlertTriangle, CheckCircle2, Info, OctagonAlert, RefreshCw } from "lucide-react";
import { Badge, Button, Card, PlaceholderNotice } from "../../design-system";
import type { BadgeTone } from "../../design-system";
import { useAuth } from "../../auth/AuthContext";
import { useGatewayDiagnostics } from "../hooks/useGatewayDiagnostics";
import type { DiagnosticFinding, DiagnosticSeverity } from "../types";

const SEVERITY_ORDER: DiagnosticSeverity[] = ["error", "warning", "info"];

const SEVERITY_META: Record<DiagnosticSeverity, { label: string; tone: BadgeTone; icon: typeof OctagonAlert }> = {
  error: { label: "Errors", tone: "danger", icon: OctagonAlert },
  warning: { label: "Warnings", tone: "warning", icon: AlertTriangle },
  info: { label: "Info", tone: "info", icon: Info },
};

const CATEGORY_LABEL: Record<string, string> = {
  provider_health: "Provider health",
  configuration: "Configuration",
  routing: "Routing",
};

function FindingRow({ finding }: { finding: DiagnosticFinding }) {
  const meta = SEVERITY_META[finding.severity];
  return (
    <li className="rounded-lg border border-border-hairline bg-surface-2 p-3 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <meta.icon className={`h-3.5 w-3.5 ${finding.severity === "error" ? "text-status-danger" : finding.severity === "warning" ? "text-status-warning" : "text-status-info"}`} aria-hidden="true" />
          <span className="font-medium text-slate-200">{finding.title}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Badge tone="neutral">{CATEGORY_LABEL[finding.category] ?? finding.category}</Badge>
          <Badge tone={meta.tone}>{meta.label.replace(/s$/, "")}</Badge>
        </div>
      </div>
      <p className="mt-1.5 text-slate-400">{finding.detail}</p>
      <p className="mt-1.5 text-slate-500">
        <span className="font-medium text-slate-400">Recommended: </span>
        {finding.recommendation}
      </p>
    </li>
  );
}

/**
 * GatewayDiagnosticsPanel — M8.3 Step 6 (AI Gateway Management & Control,
 * Gateway Diagnostics). READ-ONLY: `useGatewayDiagnostics()` only ever
 * calls `GET /ai-gateway/diagnostics`, which never mutates anything and
 * has no action to take against a finding - there is deliberately no
 * "resolve"/"dismiss" button anywhere on this panel, same "nothing to
 * action against" shape the pre-existing Approvals view already
 * established for a read-only operational list.
 *
 * Findings are grouped into three clearly separate sections - Errors,
 * Warnings, Info (the CEO's own "clearly separate warnings from errors"
 * requirement) - each with its own icon/tone, never mixed into one
 * undifferentiated list. Admin-gated server-side (see
 * useGatewayDiagnostics.ts's own docstring) - a non-admin viewer sees the
 * same PlaceholderNotice any other failed read already shows.
 */
export function GatewayDiagnosticsPanel() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const { data, isLoading, error, refresh } = useGatewayDiagnostics();

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-slate-100">Gateway Diagnostics</h2>
          <p className="mt-0.5 text-[11px] text-slate-500">
            Built from existing provider health, live routing outcomes, and recent request telemetry - read-only,
            nothing here can be actioned directly.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <div className="flex items-center gap-1.5">
              {data.errorCount > 0 && <Badge tone="danger">{data.errorCount} error{data.errorCount === 1 ? "" : "s"}</Badge>}
              {data.warningCount > 0 && <Badge tone="warning">{data.warningCount} warning{data.warningCount === 1 ? "" : "s"}</Badge>}
              {data.infoCount > 0 && <Badge tone="info">{data.infoCount} info</Badge>}
            </div>
          )}
          <Button size="sm" variant="ghost" onClick={refresh} isLoading={isLoading} aria-label="Refresh diagnostics">
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
      </div>

      {!isAdmin && !isLoading && !error && (
        <p className="text-[11px] text-slate-500">Gateway Diagnostics requires an admin account.</p>
      )}

      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : error ? (
        <PlaceholderNotice kind="no-data" reason={error} />
      ) : data && data.findings.length === 0 ? (
        <div className="flex items-center gap-2 rounded-lg border border-border-hairline bg-surface-2 p-3 text-xs text-status-success">
          <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
          No issues detected - every provider, routing outcome, and recent request checked out clean.
        </div>
      ) : data ? (
        <div className="flex flex-col gap-4">
          {SEVERITY_ORDER.map((severity) => {
            const rows = data.findings.filter((f) => f.severity === severity);
            if (rows.length === 0) return null;
            const meta = SEVERITY_META[severity];
            return (
              <div key={severity}>
                <p className="mb-1.5 flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-slate-500">
                  <meta.icon className="h-3 w-3" aria-hidden="true" />
                  {meta.label} ({rows.length})
                </p>
                <ul className="flex flex-col gap-2">
                  {rows.map((finding, idx) => (
                    <FindingRow key={`${finding.category}-${finding.providerKey ?? ""}-${finding.capability ?? ""}-${idx}`} finding={finding} />
                  ))}
                </ul>
              </div>
            );
          })}
          <p className="text-[10px] text-slate-600">Snapshot generated {new Date(data.generatedAt).toLocaleString()}</p>
        </div>
      ) : null}
    </Card>
  );
}
