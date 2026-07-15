import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { inputClass } from "../components/FormSection";

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

const IMPORTANCE_COLORS: Record<string, string> = {
  low: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
  medium: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  high: "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300",
  critical: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
};

export default function ProspectResearch() {
  const { companyId, prospectId } = useParams();
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
      const documents = pastedText.trim()
        ? [{ document_type: "pasted_text", extracted_text: pastedText.trim() }]
        : [];
      await apiClient.post(`${base}/research-requests/${requestId}/run`, { documents });
      setPastedText("");
      loadAll();
    } catch {
      setActionError("This research run failed. Check the Research Jobs page for details.");
    } finally {
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
      <h2 className="mb-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">Research &amp; Intelligence</h2>
      <p className="mb-6 text-sm text-slate-500 dark:text-slate-400">
        Everything AI Research knows about this prospect - versioned, evidenced, never overwritten.
      </p>

      {actionError && <p className="mb-4 text-sm text-red-600">{actionError}</p>}

      <div className="mb-6 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
        <p className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-200">Start new research</p>
        <div className="flex flex-wrap items-center gap-2">
          <select className={inputClass} value={selectedTemplateId} onChange={(e) => setSelectedTemplateId(e.target.value)}>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>{t.name}{t.is_system_default ? " (system)" : ""}</option>
            ))}
          </select>
          <button
            onClick={createRequest}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 dark:bg-indigo-600 dark:hover:bg-indigo-500"
          >
            Create request
          </button>
        </div>
        <textarea
          className={`${inputClass} mt-3`}
          rows={4}
          placeholder="Paste any text this prospect has published (website copy, a news article, a catalog extract...) - Research runs synchronously on whatever you paste here."
          value={pastedText}
          onChange={(e) => setPastedText(e.target.value)}
        />
      </div>

      <div className="mb-6">
        <p className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-200">Research requests</p>
        <div className="space-y-2">
          {requests.length === 0 && <p className="text-sm text-slate-500">No research requested yet.</p>}
          {requests.map((r) => (
            <div key={r.id} className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-3 text-sm dark:border-slate-700 dark:bg-slate-900">
              <span>{r.research_template.name} — <span className="text-xs text-slate-500">{r.status}</span></span>
              <button
                onClick={() => runRequest(r.id)}
                disabled={runningRequestId === r.id}
                className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:text-slate-300"
              >
                {runningRequestId === r.id ? "Running…" : "Run"}
              </button>
            </div>
          ))}
        </div>
      </div>

      {snapshot && (
        <div className="mb-6 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
          <p className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-200">Intelligence Snapshot (v{snapshot.version})</p>
          <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <div>
              <p className="text-xs font-medium text-slate-500">Business model</p>
              <p className="text-slate-700 dark:text-slate-300">{snapshot.business_model ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Certifications</p>
              <p className="text-slate-700 dark:text-slate-300">{snapshot.certifications?.join(", ") || "—"}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Procurement structure</p>
              <p className="text-slate-700 dark:text-slate-300">{snapshot.procurement_structure ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Sustainability notes</p>
              <p className="text-slate-700 dark:text-slate-300">{snapshot.sustainability_notes ?? "—"}</p>
            </div>
          </div>
          {snapshot.signals_summary && (
            <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">{snapshot.signals_summary}</p>
          )}
        </div>
      )}
      {!snapshot && (
        <div className="mb-6 rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900">
          No intelligence snapshot yet - run a research request above.
        </div>
      )}

      <div className="mb-6">
        <p className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-200">Signals</p>
        <div className="space-y-2">
          {signals.length === 0 && <p className="text-sm text-slate-500">No signals detected yet.</p>}
          {signals.map((s) => (
            <div key={s.id} className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
              <div className="mb-1 flex items-center gap-2">
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${IMPORTANCE_COLORS[s.importance] ?? ""}`}>{s.importance}</span>
                <span className="text-xs text-slate-500">urgency: {s.urgency}</span>
                <span className="text-xs text-slate-400">· {s.status}</span>
              </div>
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{s.title}</p>
              {s.description && <p className="text-xs text-slate-500 dark:text-slate-400">{s.description}</p>}
              {s.status === "new" && (
                <div className="mt-2 flex gap-2">
                  <button onClick={() => updateSignal(s, "reviewed")} className="text-xs font-medium text-emerald-700 underline">Mark reviewed</button>
                  <button onClick={() => updateSignal(s, "dismissed")} className="text-xs font-medium text-slate-500 underline">Dismiss</button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="mb-6">
        <p className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-200">Recommendations</p>
        <div className="space-y-2">
          {recommendations.length === 0 && <p className="text-sm text-slate-500">No recommendations yet.</p>}
          {recommendations.map((r) => (
            <div key={r.id} className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
              <div className="mb-1 flex items-center gap-2">
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                  {r.recommendation_type.replace(/_/g, " ")}
                </span>
                <span className="text-xs text-slate-400">· {r.status}</span>
              </div>
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{r.title}</p>
              {r.rationale && <p className="text-xs text-slate-500 dark:text-slate-400">{r.rationale}</p>}
              {r.status === "new" && (
                <div className="mt-2 flex gap-2">
                  <button onClick={() => updateRecommendation(r, "accepted")} className="text-xs font-medium text-emerald-700 underline">Accept</button>
                  <button onClick={() => updateRecommendation(r, "dismissed")} className="text-xs font-medium text-slate-500 underline">Dismiss</button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-medium text-slate-700 dark:text-slate-200">Research Reports</p>
          <button
            onClick={generateReport}
            className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300"
          >
            Generate report
          </button>
        </div>
        <div className="space-y-2">
          {reports.length === 0 && <p className="text-sm text-slate-500">No reports generated yet.</p>}
          {reports.map((r) => (
            <div key={r.id} className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{r.title}</p>
              <p className="text-xs text-slate-500">{new Date(r.generated_at).toLocaleString()}</p>
              {r.summary && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{r.summary}</p>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
