import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { inputClass } from "../components/FormSection";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { Card, Badge, Button, Select } from "../design-system";
import type { BadgeTone } from "../design-system";
import { engineBadgeTone, engineLabel } from "../research/useResearchExecution";
import { PremiumApprovalDialog } from "../research/PremiumApprovalDialog";

// M9 (AI Provider Hierarchy). Shape of POST .../ai-preflight's response
// (app.schemas.research_request.AIPreflightResult) - checked BEFORE
// submitting a run so the premium-approval dialog can be shown at
// submission time rather than discovered mid-run (see
// app/research/ai_preflight.py's own docstring).
interface AIPreflightResult {
  applicable: boolean;
  approval_required: boolean;
  candidate_provider_key: string | null;
  estimated_cost_usd: number | null;
  reasons: string[];
}

interface ResearchTemplate {
  id: string;
  name: string;
  description: string | null;
  is_system_default: boolean;
}

interface ResearchRequest {
  id: string;
  status: string;
  research_template: ResearchTemplate;
  created_at: string;
}

interface Signal {
  id: string;
  signal_type: string;
  title: string;
  description: string | null;
  importance: string;
  urgency: string;
  status: string;
  confidence: number | null;
}

interface Recommendation {
  id: string;
  recommendation_type: string;
  title: string;
  rationale: string | null;
  status: string;
  confidence: number | null;
}

interface IntelligenceSnapshot {
  id: string;
  version: number;
  research_job_id: string | null;
  business_model: string | null;
  certifications: string[] | null;
  manufacturing_or_trading: string | null;
  sustainability_notes: string | null;
  import_export_activity: string[] | null;
  buyer_notes: string | null;
  procurement_structure: string | null;
  purchasing_process: string | null;
  signals_summary: string | null;
}

// Minimal shape - only what the engine badge needs (M2 Phase 3
// observability follow-up). Deliberately not the full ResearchJob shape
// ResearchJobs.tsx uses; this page only ever needs to know which engine
// produced the CURRENT snapshot's underlying analyses.
interface ResearchJobEngineInfo {
  id: string;
  analyses: { model_used: string }[];
}

interface ResearchReport {
  id: string;
  title: string;
  summary: string | null;
  generated_at: string;
}

const IMPORTANCE_TONES: Record<string, BadgeTone> = {
  low: "neutral",
  medium: "info",
  high: "warning",
  critical: "danger",
};

/**
 * ProspectResearch — M8.7 Phase E2 (AI Workforce zone). Migrated in place
 * per Design Bible Section 9.2: identical fetch/create/update/generate
 * calls, only the markup moves onto design-system tokens/primitives.
 */
export default function ProspectResearch() {
  const { companyId, prospectId } = useParams();
  const navigate = useNavigate();
  const base = `/company-profiles/${companyId}/prospects/${prospectId}`;

  const [templates, setTemplates] = useState<ResearchTemplate[]>([]);
  const [requests, setRequests] = useState<ResearchRequest[]>([]);
  const [snapshot, setSnapshot] = useState<IntelligenceSnapshot | null>(null);
  const [researchJobs, setResearchJobs] = useState<ResearchJobEngineInfo[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [reports, setReports] = useState<ResearchReport[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [pastedText, setPastedText] = useState("");
  const [runningRequestId, setRunningRequestId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  // M9 (AI Provider Hierarchy) - non-null while the premium-approval
  // dialog is open, holding what's needed to either proceed
  // (premium_approved: true) or run without AI escalation on decline.
  const [pendingApproval, setPendingApproval] = useState<{
    requestId: string;
    documents: { document_type: string; extracted_text: string }[];
    preflight: AIPreflightResult;
  } | null>(null);
  const [isSubmittingApproval, setIsSubmittingApproval] = useState(false);

  const loadAll = () => {
    setIsLoading(true);
    Promise.all([
      apiClient.get(`/company-profiles/${companyId}/research-templates`),
      apiClient.get(`${base}/research-requests`),
      apiClient.get(`${base}/intelligence-snapshots/current`).catch(() => ({ data: null })),
      apiClient.get(`${base}/signals`),
      apiClient.get(`${base}/recommendations`),
      apiClient.get(`${base}/research-reports`),
      // M2 Phase 3 observability follow-up: which engine (deterministic
      // vs. a real model) actually produced the current snapshot's
      // analyses - read-only, sourced from each job's own stored
      // AIAnalysis.model_used, never from live config. Reuses the
      // existing GET /research-jobs?prospect_id= route (already used by
      // ResearchJobs.tsx) rather than adding a new endpoint.
      apiClient.get(`/company-profiles/${companyId}/research-jobs`, { params: { prospect_id: prospectId } }),
    ]).then(([templatesRes, requestsRes, snapshotRes, signalsRes, recommendationsRes, reportsRes, researchJobsRes]) => {
      setTemplates(templatesRes.data);
      if (!selectedTemplateId && templatesRes.data.length > 0) setSelectedTemplateId(templatesRes.data[0].id);
      setRequests(requestsRes.data);
      setSnapshot(snapshotRes.data);
      setSignals(signalsRes.data);
      setRecommendations(recommendationsRes.data);
      setReports(reportsRes.data);
      setResearchJobs(researchJobsRes.data);
      setIsLoading(false);
    });
  };

  useEffect(loadAll, [companyId, prospectId]);

  const createRequest = async () => {
    if (!selectedTemplateId) return;
    setActionError(null);
    try {
      await apiClient.post(`${base}/research-requests`, { research_template_id: selectedTemplateId });
      loadAll();
    } catch {
      setActionError("Could not create a research request.");
    }
  };

  const submitRun = async (
    requestId: string,
    documents: { document_type: string; extracted_text: string }[],
    premiumApproved: boolean
  ) => {
    // M8.13: /run no longer returns a finished ResearchJob synchronously -
    // it publishes a trigger event and responds "queued" (see
    // app/api/routes/research_requests.py's own docstring). Navigate to
    // the Live Workflow Progress screen, which finds and watches the
    // resulting job as the Workflow Engine actually produces it.
    await apiClient.post(`${base}/research-requests/${requestId}/run`, {
      documents,
      // M9 (AI Provider Hierarchy) - only meaningful when the ai-preflight
      // check found local/free unavailable and a premium provider needs
      // approval; harmless (ignored) otherwise - see
      // ResearchRequestRunBody.premium_approved's own docstring.
      premium_approved: premiumApproved,
    });
    setPastedText("");
    navigate(`/businesses/${companyId}/prospects/${prospectId}/research/${requestId}/run`);
  };

  const runRequest = async (requestId: string) => {
    setActionError(null);
    setRunningRequestId(requestId);
    const documents = pastedText.trim()
      ? [{ document_type: "pasted_text", extracted_text: pastedText.trim() }]
      : [];
    try {
      // M9 (AI Provider Hierarchy): check BEFORE submitting whether this
      // run would need premium-provider approval, so the Yes/No dialog
      // can be shown at submission time - see
      // app/research/ai_preflight.py's own docstring for why this is a
      // pre-flight check, not a mid-run interrupt.
      const preflightRes = await apiClient.post<AIPreflightResult>(
        `${base}/research-requests/${requestId}/ai-preflight`,
        { documents }
      );
      if (preflightRes.data.applicable && preflightRes.data.approval_required) {
        setPendingApproval({ requestId, documents, preflight: preflightRes.data });
        setRunningRequestId(null);
        return;
      }
      await submitRun(requestId, documents, false);
    } catch {
      setActionError("This research run could not be started.");
      setRunningRequestId(null);
    }
  };

  const approvePremiumAndRun = async () => {
    if (!pendingApproval) return;
    setIsSubmittingApproval(true);
    try {
      await submitRun(pendingApproval.requestId, pendingApproval.documents, true);
      setPendingApproval(null);
    } catch {
      setActionError("This research run could not be started.");
    } finally {
      setIsSubmittingApproval(false);
    }
  };

  const declinePremiumAndRun = async () => {
    if (!pendingApproval) return;
    setIsSubmittingApproval(true);
    try {
      // Runs anyway, without AI escalation - LLMAnalysisEngine will
      // degrade to its existing "AI analysis failed"-shaped outcome
      // (reasoning explains premium approval was needed and declined),
      // never a silent premium call. See llm_engine.py's
      // _premium_approval_outcomes().
      await submitRun(pendingApproval.requestId, pendingApproval.documents, false);
      setPendingApproval(null);
    } catch {
      setActionError("This research run could not be started.");
    } finally {
      setIsSubmittingApproval(false);
    }
  };

  const updateSignal = async (signal: Signal, newStatus: string) => {
    await apiClient.put(`${base}/signals/${signal.id}`, { status: newStatus });
    loadAll();
  };

  const updateRecommendation = async (rec: Recommendation, newStatus: string) => {
    await apiClient.put(`${base}/recommendations/${rec.id}`, { status: newStatus });
    loadAll();
  };

  const generateReport = async () => {
    setActionError(null);
    try {
      await apiClient.post(`${base}/research-reports/generate`, {});
      loadAll();
    } catch {
      setActionError("Could not generate a report - run research first so an intelligence snapshot exists.");
    }
  };

  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>;

  // The engine that produced the currently-displayed snapshot - looked
  // up by the snapshot's own research_job_id, then the first analysis
  // row with a model_used (all AIAnalysis rows from one research run
  // share the same model_used today, whichever engine ran). Undefined
  // (renders "Unknown engine") only if the snapshot's originating job
  // can no longer be found or has no analyses at all.
  const currentSnapshotModelUsed = snapshot
    ? researchJobs.find((j) => j.id === snapshot.research_job_id)?.analyses.find((a) => a.model_used)?.model_used
    : undefined;

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Businesses", to: "/businesses" },
          { label: "Prospects", to: `/businesses/${companyId}/discovery/prospects` },
          { label: "Research" },
        ]}
      />

      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Research &amp; Intelligence</h1>
      <p className="mb-6 text-body text-slate-400">
        Everything AI Research knows about this prospect - versioned, evidenced, never overwritten.
      </p>

      {actionError && <p className="mb-4 text-sm text-status-danger">{actionError}</p>}

      <Card className="mb-6">
        <p className="mb-2 text-sm font-medium text-slate-200">Start new research</p>
        <div className="flex flex-wrap items-center gap-2">
          <Select className="w-64" value={selectedTemplateId} onChange={(e) => setSelectedTemplateId(e.target.value)}>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>{t.name}{t.is_system_default ? " (system)" : ""}</option>
            ))}
          </Select>
          <Button size="sm" onClick={createRequest}>Create request</Button>
        </div>
        <textarea
          className={`${inputClass} mt-3`}
          rows={4}
          placeholder="Paste any text this prospect has published (website copy, a news article, a catalog extract...) - shown live on the Workflow Progress screen once you click Run."
          value={pastedText}
          onChange={(e) => setPastedText(e.target.value)}
        />
      </Card>

      <div className="mb-6">
        <p className="mb-2 text-sm font-medium text-slate-200">Research requests</p>
        <div className="space-y-2">
          {requests.length === 0 && <p className="text-sm text-slate-500">No research requested yet.</p>}
          {requests.map((r) => (
            <Card key={r.id} padding="compact" className="flex items-center justify-between text-sm">
              <span className="text-slate-200">{r.research_template.name} — <span className="text-xs text-slate-500">{r.status}</span></span>
              <Button size="sm" variant="secondary" onClick={() => runRequest(r.id)} isLoading={runningRequestId === r.id}>
                Run
              </Button>
            </Card>
          ))}
        </div>
      </div>

      {snapshot && (
        <Card className="mb-6">
          <div className="mb-2 flex items-center gap-2">
            <p className="text-sm font-medium text-slate-200">Intelligence Snapshot (v{snapshot.version})</p>
            {/* M2 Phase 3 observability follow-up: which engine produced
                THIS snapshot's analyses - read-only, from the stored
                model_used on the research job's own AIAnalysis rows, not
                from current config, so a historical snapshot always
                shows accurately even after the engine setting changes
                later. */}
            <Badge tone={engineBadgeTone(currentSnapshotModelUsed)}>{engineLabel(currentSnapshotModelUsed)}</Badge>
          </div>
          <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <div>
              <p className="text-xs font-medium text-slate-500">Business model</p>
              <p className="text-slate-300">{snapshot.business_model ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Certifications</p>
              <p className="text-slate-300">{snapshot.certifications?.join(", ") || "—"}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Procurement structure</p>
              <p className="text-slate-300">{snapshot.procurement_structure ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Sustainability notes</p>
              <p className="text-slate-300">{snapshot.sustainability_notes ?? "—"}</p>
            </div>
          </div>
          {snapshot.signals_summary && <p className="mt-3 text-sm text-slate-300">{snapshot.signals_summary}</p>}
        </Card>
      )}
      {!snapshot && (
        <div className="mb-6 rounded-lg border border-dashed border-border-hairline-strong bg-surface-2/50 p-6 text-center text-sm text-slate-500">
          No intelligence snapshot yet - run a research request above.
        </div>
      )}

      <div className="mb-6">
        <p className="mb-2 text-sm font-medium text-slate-200">Signals</p>
        <div className="space-y-2">
          {signals.length === 0 && <p className="text-sm text-slate-500">No signals detected yet.</p>}
          {signals.map((s) => (
            <Card key={s.id}>
              <div className="mb-1 flex items-center gap-2">
                <Badge tone={IMPORTANCE_TONES[s.importance] ?? "neutral"}>{s.importance}</Badge>
                <span className="text-xs text-slate-500">urgency: {s.urgency}</span>
                <span className="text-xs text-slate-500">· {s.status}</span>
              </div>
              <p className="text-sm font-medium text-slate-100">{s.title}</p>
              {s.description && <p className="text-xs text-slate-400">{s.description}</p>}
              {s.status === "new" && (
                <div className="mt-2 flex gap-2">
                  <button onClick={() => updateSignal(s, "reviewed")} className="text-xs font-medium text-status-success underline">
                    Mark reviewed
                  </button>
                  <button onClick={() => updateSignal(s, "dismissed")} className="text-xs font-medium text-slate-500 underline">
                    Dismiss
                  </button>
                </div>
              )}
            </Card>
          ))}
        </div>
      </div>

      <div className="mb-6">
        <p className="mb-2 text-sm font-medium text-slate-200">Recommendations</p>
        <div className="space-y-2">
          {recommendations.length === 0 && <p className="text-sm text-slate-500">No recommendations yet.</p>}
          {recommendations.map((r) => (
            <Card key={r.id}>
              <div className="mb-1 flex items-center gap-2">
                <Badge tone="neutral">{r.recommendation_type.replace(/_/g, " ")}</Badge>
                <span className="text-xs text-slate-500">· {r.status}</span>
              </div>
              <p className="text-sm font-medium text-slate-100">{r.title}</p>
              {r.rationale && <p className="text-xs text-slate-400">{r.rationale}</p>}
              {r.status === "new" && (
                <div className="mt-2 flex gap-2">
                  <button onClick={() => updateRecommendation(r, "accepted")} className="text-xs font-medium text-status-success underline">
                    Accept
                  </button>
                  <button onClick={() => updateRecommendation(r, "dismissed")} className="text-xs font-medium text-slate-500 underline">
                    Dismiss
                  </button>
                </div>
              )}
            </Card>
          ))}
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-medium text-slate-200">Research Reports</p>
          <Button size="sm" variant="secondary" onClick={generateReport}>
            Generate report
          </Button>
        </div>
        <div className="space-y-2">
          {reports.length === 0 && <p className="text-sm text-slate-500">No reports generated yet.</p>}
          {reports.map((r) => (
            <Card key={r.id}>
              <p className="text-sm font-medium text-slate-100">{r.title}</p>
              <p className="text-xs text-slate-500">{new Date(r.generated_at).toLocaleString()}</p>
              {r.summary && <p className="mt-1 text-xs text-slate-400">{r.summary}</p>}
            </Card>
          ))}
        </div>
      </div>

      <PremiumApprovalDialog
        open={pendingApproval != null}
        candidateProviderKey={pendingApproval?.preflight.candidate_provider_key ?? null}
        estimatedCostUsd={pendingApproval?.preflight.estimated_cost_usd ?? null}
        reasons={pendingApproval?.preflight.reasons ?? []}
        isSubmitting={isSubmittingApproval}
        onApprove={approvePremiumAndRun}
        onDecline={declinePremiumAndRun}
      />
    </div>
  );
}
