import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { inputClass } from "../components/FormSection";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { Card, Badge, Button, Select } from "../design-system";
import type { BadgeTone } from "../design-system";

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
  const [signals, setSignals] = useState<Signal[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [reports, setReports] = useState<ResearchReport[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [pastedText, setPastedText] = useState("");
  const [runningRequestId, setRunningRequestId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadAll = () => {
    setIsLoading(true);
    Promise.all([
      apiClient.get(`/company-profiles/${companyId}/research-templates`),
      apiClient.get(`${base}/research-requests`),
      apiClient.get(`${base}/intelligence-snapshots/current`).catch(() => ({ data: null })),
      apiClient.get(`${base}/signals`),
      apiClient.get(`${base}/recommendations`),
      apiClient.get(`${base}/research-reports`),
    ]).then(([templatesRes, requestsRes, snapshotRes, signalsRes, recommendationsRes, reportsRes]) => {
      setTemplates(templatesRes.data);
      if (!selectedTemplateId && templatesRes.data.length > 0) setSelectedTemplateId(templatesRes.data[0].id);
      setRequests(requestsRes.data);
      setSnapshot(snapshotRes.data);
      setSignals(signalsRes.data);
      setRecommendations(recommendationsRes.data);
      setReports(reportsRes.data);
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

  const runRequest = async (requestId: string) => {
    setActionError(null);
    setRunningRequestId(requestId);
    try {
      // M8.13: /run no longer returns a finished ResearchJob synchronously
      // - it publishes a trigger event and responds "queued" (see
      // app/api/routes/research_requests.py's own docstring). Navigate to
      // the Live Workflow Progress screen, which finds and watches the
      // resulting job as the Workflow Engine actually produces it.
      const documents = pastedText.trim()
        ? [{ document_type: "pasted_text", extracted_text: pastedText.trim() }]
        : [];
      await apiClient.post(`${base}/research-requests/${requestId}/run`, { documents });
      setPastedText("");
      navigate(`/businesses/${companyId}/prospects/${prospectId}/research/${requestId}/run`);
    } catch {
      setActionError("This research run could not be started.");
      setRunningRequestId(null);
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
          <p className="mb-2 text-sm font-medium text-slate-200">Intelligence Snapshot (v{snapshot.version})</p>
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
    </div>
  );
}
