import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { Card, Badge, Button, Select } from "../design-system";
import type { BadgeTone } from "../design-system";

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
const RANK_TONES: Record<string, BadgeTone> = { primary: "success", secondary: "info", fallback: "neutral" };
const READINESS_TONES: Record<string, BadgeTone> = {
  unknown: "neutral",
  low: "neutral",
  medium: "info",
  high: "warning",
  ready_to_engage: "success",
};

/**
 * ProspectStrategy — M8.7 Phase E2 (AI Workforce zone). Migrated in place
 * per Design Bible Section 9.2: identical fetch/create/run calls, only the
 * markup moves onto design-system tokens/primitives.
 */
export default function ProspectStrategy() {
  const { companyId, prospectId } = useParams();
  const navigate = useNavigate();
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
      // M8.11: /run no longer returns a finished PersonalizationJob
      // synchronously - it publishes a trigger event and responds
      // "queued" (see app/api/routes/personalization_requests.py's own
      // docstring). Navigate to the Live Workflow Progress screen, which
      // finds and watches the resulting job as the Workflow Engine
      // actually produces it.
      await apiClient.post(`${base}/personalization-requests/${requestId}/run`, {});
      navigate(`/businesses/${companyId}/prospects/${prospectId}/strategy/${requestId}/run`);
    } catch {
      setActionError("Could not queue this strategy run.");
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

      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Sales Strategy</h1>
      <p className="mb-6 text-body text-slate-400">
        The best approach for this prospect, synthesized from Research's Intelligence Snapshot, Signals, and
        Recommendations - never re-derived, only read.
      </p>

      {actionError && <p className="mb-4 text-sm text-status-danger">{actionError}</p>}

      <Card className="mb-6">
        <p className="mb-2 text-sm font-medium text-slate-200">Generate a new strategy</p>
        <div className="flex flex-wrap items-center gap-2">
          <Select className="w-64" value={selectedTemplateId} onChange={(e) => setSelectedTemplateId(e.target.value)}>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>{t.name}{t.is_system_default ? " (system)" : ""}</option>
            ))}
          </Select>
          <Button size="sm" onClick={createRequest}>Create request</Button>
        </div>
      </Card>

      <div className="mb-6">
        <p className="mb-2 text-sm font-medium text-slate-200">Personalization requests</p>
        <div className="space-y-2">
          {requests.length === 0 && <p className="text-sm text-slate-500">No strategy requested yet.</p>}
          {requests.map((r) => (
            <Card key={r.id} padding="compact" className="flex items-center justify-between text-sm">
              <span className="text-slate-200">{r.personalization_template.name} — <span className="text-xs text-slate-500">{r.status}</span></span>
              <Button size="sm" variant="secondary" onClick={() => runRequest(r.id)} isLoading={runningRequestId === r.id}>
                Run
              </Button>
            </Card>
          ))}
        </div>
      </div>

      {snapshot && (
        <>
          <Card className="mb-6">
            <div className="mb-3 flex items-center gap-2">
              <p className="text-sm font-medium text-slate-200">Strategy Snapshot v{snapshot.version}</p>
              <Badge tone={READINESS_TONES[snapshot.buyer_readiness] ?? "neutral"}>
                readiness: {snapshot.buyer_readiness.replace(/_/g, " ")}
              </Badge>
              <span className="text-xs text-slate-500">relationship at generation: {snapshot.relationship_stage_at_generation}</span>
            </div>
            {snapshot.buyer_readiness_reasoning && <p className="mb-3 text-xs text-slate-400">{snapshot.buyer_readiness_reasoning}</p>}

            {snapshot.buyer_persona && (
              <div className="mb-3">
                <p className="mb-1 text-xs font-medium text-slate-500">Buyer persona</p>
                <p className="text-sm text-slate-300">{String(snapshot.buyer_persona.archetype ?? "")}</p>
                <p className="text-xs text-slate-400">{String(snapshot.buyer_persona.decision_style ?? "")}</p>
              </div>
            )}

            {snapshot.communication_strategy && (
              <div>
                <p className="mb-1 text-xs font-medium text-slate-500">Communication strategy</p>
                <div className="flex flex-wrap gap-1.5 text-xs">
                  {Object.entries(snapshot.communication_strategy)
                    .filter(([key]) => key !== "rationale")
                    .map(([key, value]) => (
                      <span key={key} className="rounded-pill bg-surface-2 px-2 py-0.5 text-slate-300">
                        {key.replace(/_/g, " ")}: {String(value)}
                      </span>
                    ))}
                </div>
                {snapshot.communication_strategy.rationale && (
                  <p className="mt-1 text-xs text-slate-500">{snapshot.communication_strategy.rationale}</p>
                )}
              </div>
            )}
          </Card>

          <div className="mb-6 space-y-3">
            <p className="text-sm font-medium text-slate-200">Ranked strategies</p>
            {sortedStrategies.map((s) => (
              <Card key={s.id}>
                <div className="mb-1 flex items-center gap-2">
                  <Badge tone={RANK_TONES[s.strategy_rank] ?? "neutral"}>{s.strategy_rank}</Badge>
                  {s.confidence != null && <span className="text-xs text-slate-500">{Math.round(s.confidence * 100)}% confidence</span>}
                </div>
                <p className="text-sm font-medium text-slate-100">{s.title}</p>
                <p className="mt-1 text-sm text-slate-300">{s.narrative}</p>
                {s.evidence.length > 0 && (
                  <p className="mt-2 text-xs text-slate-500">
                    Evidence: {s.evidence.map((e) => e.excerpt).filter(Boolean).join(" · ")}
                  </p>
                )}
              </Card>
            ))}
          </div>

          {snapshot.personalization_variables && (
            <div>
              <p className="mb-2 text-sm font-medium text-slate-200">Personalization variables (for M4)</p>
              <pre className="overflow-x-auto rounded-lg bg-surface-2 p-3 text-xs text-slate-300">
                {JSON.stringify(snapshot.personalization_variables, null, 2)}
              </pre>
            </div>
          )}
        </>
      )}
      {!snapshot && (
        <div className="rounded-lg border border-dashed border-border-hairline-strong bg-surface-2/50 p-6 text-center text-sm text-slate-500">
          No strategy generated yet - create and run a request above.
        </div>
      )}
    </div>
  );
}
