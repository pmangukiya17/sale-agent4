import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { inputClass } from "../components/FormSection";
import { Breadcrumbs } from "../components/Breadcrumbs";

interface PersonalizationTemplate {
  id: string;
  name: string;
  description: string | null;
  is_system_default: boolean;
}

interface PersonalizationRequest {
  id: string;
  status: string;
  personalization_template: PersonalizationTemplate;
  created_at: string;
}

interface PersonalizationEvidence {
  id: string;
  signal_id: string | null;
  recommendation_id: string | null;
  intelligence_snapshot_id: string | null;
  excerpt: string | null;
}

interface PersonalizationStrategy {
  id: string;
  strategy_rank: "primary" | "secondary" | "fallback";
  title: string;
  narrative: string;
  confidence: number | null;
  reasoning: string | null;
  evidence: PersonalizationEvidence[];
}

interface CommunicationStrategy {
  formality: string;
  directness: string;
  warmth: string;
  technical_depth: string;
  authority: string;
  consultative_level: string;
  urgency: string;
  message_length: string;
  rationale: string | null;
}

interface PersonalizationSnapshot {
  id: string;
  version: number;
  buyer_persona: Record<string, unknown> | null;
  buyer_readiness: string;
  buyer_readiness_reasoning: string | null;
  relationship_stage_at_generation: string;
  personalization_variables: Record<string, unknown> | null;
  communication_strategy: CommunicationStrategy | null;
  strategies: PersonalizationStrategy[];
}

const RANK_ORDER: Record<string, number> = { primary: 0, secondary: 1, fallback: 2 };
const RANK_COLORS: Record<string, string> = {
  primary: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300",
  secondary: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  fallback: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
};
const READINESS_COLORS: Record<string, string> = {
  unknown: "bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400",
  low: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
  medium: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  high: "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300",
  ready_to_engage: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300",
};

export default function ProspectStrategy() {
  const { companyId, prospectId } = useParams();
  const base = `/company-profiles/${companyId}/prospects/${prospectId}`;

  const [templates, setTemplates] = useState<PersonalizationTemplate[]>([]);
  const [requests, setRequests] = useState<PersonalizationRequest[]>([]);
  const [snapshot, setSnapshot] = useState<PersonalizationSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [runningRequestId, setRunningRequestId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadAll = () => {
    setIsLoading(true);
    Promise.all([
      apiClient.get(`/company-profiles/${companyId}/personalization-templates`),
      apiClient.get(`${base}/personalization-requests`),
      apiClient.get(`${base}/personalization-snapshots/current`).catch(() => ({ data: null })),
    ]).then(([templatesRes, requestsRes, snapshotRes]) => {
      setTemplates(templatesRes.data);
      if (!selectedTemplateId && templatesRes.data.length > 0) setSelectedTemplateId(templatesRes.data[0].id);
      setRequests(requestsRes.data);
      setSnapshot(snapshotRes.data);
      setIsLoading(false);
    });
  };

  useEffect(loadAll, [companyId, prospectId]);

  const createRequest = async () => {
    if (!selectedTemplateId) return;
    setActionError(null);
    try {
      await apiClient.post(`${base}/personalization-requests`, { personalization_template_id: selectedTemplateId });
      loadAll();
    } catch {
      setActionError("Could not create a personalization request.");
    }
  };

  const runRequest = async (requestId: string) => {
    setActionError(null);
    setRunningRequestId(requestId);
    try {
      await apiClient.post(`${base}/personalization-requests/${requestId}/run`, {});
      loadAll();
    } catch {
      setActionError("This strategy run failed. Check the Personalization Jobs page for details.");
    } finally {
      setRunningRequestId(null);
    }
  };

  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>;

  const sortedStrategies = snapshot ? [...snapshot.strategies].sort((a, b) => RANK_ORDER[a.strategy_rank] - RANK_ORDER[b.strategy_rank]) : [];

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Businesses", to: "/businesses" },
          { label: "Prospects", to: `/businesses/${companyId}/discovery/prospects` },
          { label: "Strategy" },
        ]}
      />

      <h2 className="mb-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">Sales Strategy</h2>
      <p className="mb-6 text-sm text-slate-500 dark:text-slate-400">
        The best approach for this prospect, synthesized from Research's Intelligence Snapshot, Signals, and
        Recommendations - never re-derived, only read.
      </p>

      {actionError && <p className="mb-4 text-sm text-red-600">{actionError}</p>}

      <div className="mb-6 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
        <p className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-200">Generate a new strategy</p>
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
      </div>

      <div className="mb-6">
        <p className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-200">Personalization requests</p>
        <div className="space-y-2">
          {requests.length === 0 && <p className="text-sm text-slate-500">No strategy requested yet.</p>}
          {requests.map((r) => (
            <div key={r.id} className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-3 text-sm dark:border-slate-700 dark:bg-slate-900">
              <span>{r.personalization_template.name} — <span className="text-xs text-slate-500">{r.status}</span></span>
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
        <>
          <div className="mb-6 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
            <div className="mb-3 flex items-center gap-2">
              <p className="text-sm font-medium text-slate-700 dark:text-slate-200">Strategy Snapshot v{snapshot.version}</p>
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${READINESS_COLORS[snapshot.buyer_readiness] ?? ""}`}>
                readiness: {snapshot.buyer_readiness.replace(/_/g, " ")}
              </span>
              <span className="text-xs text-slate-400">relationship at generation: {snapshot.relationship_stage_at_generation}</span>
            </div>
            {snapshot.buyer_readiness_reasoning && (
              <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">{snapshot.buyer_readiness_reasoning}</p>
            )}

            {snapshot.buyer_persona && (
              <div className="mb-3">
                <p className="mb-1 text-xs font-medium text-slate-500">Buyer persona</p>
                <p className="text-sm text-slate-700 dark:text-slate-300">{String(snapshot.buyer_persona.archetype ?? "")}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">{String(snapshot.buyer_persona.decision_style ?? "")}</p>
              </div>
            )}

            {snapshot.communication_strategy && (
              <div>
                <p className="mb-1 text-xs font-medium text-slate-500">Communication strategy</p>
                <div className="flex flex-wrap gap-1.5 text-xs">
                  {Object.entries(snapshot.communication_strategy)
                    .filter(([key]) => key !== "rationale")
                    .map(([key, value]) => (
                      <span key={key} className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                        {key.replace(/_/g, " ")}: {String(value)}
                      </span>
                    ))}
                </div>
                {snapshot.communication_strategy.rationale && (
                  <p className="mt-1 text-xs text-slate-400">{snapshot.communication_strategy.rationale}</p>
                )}
              </div>
            )}
          </div>

          <div className="mb-6 space-y-3">
            <p className="text-sm font-medium text-slate-700 dark:text-slate-200">Ranked strategies</p>
            {sortedStrategies.map((s) => (
              <div key={s.id} className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                <div className="mb-1 flex items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${RANK_COLORS[s.strategy_rank] ?? ""}`}>{s.strategy_rank}</span>
                  {s.confidence != null && <span className="text-xs text-slate-500">{Math.round(s.confidence * 100)}% confidence</span>}
                </div>
                <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{s.title}</p>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{s.narrative}</p>
                {s.evidence.length > 0 && (
                  <p className="mt-2 text-xs text-slate-400">
                    Evidence: {s.evidence.map((e) => e.excerpt).filter(Boolean).join(" · ")}
                  </p>
                )}
              </div>
            ))}
          </div>

          {snapshot.personalization_variables && (
            <div>
              <p className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-200">Personalization variables (for M4)</p>
              <pre className="overflow-x-auto rounded-md bg-slate-50 p-3 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                {JSON.stringify(snapshot.personalization_variables, null, 2)}
              </pre>
            </div>
          )}
        </>
      )}
      {!snapshot && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900">
          No strategy generated yet - create and run a request above.
        </div>
      )}
    </div>
  );
}
