import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { inputClass } from "../components/FormSection";

type ProspectStatus =
  | "new" | "duplicate_review" | "scored" | "qualified" | "unqualified"
  | "in_review" | "approved" | "rejected" | "archived";

interface ScoreBreakdownEntry {
  factor: string;
  weight: number;
  matched: boolean | null;
  points: number;
  explanation: string;
}

interface ProspectContact {
  id: string;
  name: string | null;
  role: string | null;
  department: string | null;
  decision_maker_level: string;
  email: string | null;
  phone: string | null;
  confidence: number | null;
}

interface Prospect {
  id: string;
  name: string;
  website: string | null;
  country: string | null;
  company_size_range: string | null;
  description: string | null;
  status: ProspectStatus;
  total_score: number | null;
  score_breakdown: ScoreBreakdownEntry[] | null;
  ai_reasoning: string | null;
  potential_duplicate_of_prospect_id: string | null;
  duplicate_confidence: number | null;
  rejection_reason: string | null;
  contacts: ProspectContact[];
}

interface TimelineEvent {
  id: string;
  event_type: string;
  actor: string;
  created_at: string;
}

const STATUS_LABELS: Record<ProspectStatus, string> = {
  new: "New", duplicate_review: "Needs duplicate review", scored: "Scored",
  qualified: "Qualified", unqualified: "Unqualified", in_review: "In review",
  approved: "Approved", rejected: "Rejected", archived: "Archived",
};

const STATUS_COLORS: Record<ProspectStatus, string> = {
  new: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
  duplicate_review: "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300",
  scored: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
  qualified: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300",
  unqualified: "bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400",
  in_review: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  approved: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300",
  rejected: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
  archived: "bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400",
};

export default function Prospects() {
  const { companyId } = useParams();
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [minScore, setMinScore] = useState<string>("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = () => {
    setIsLoading(true);
    const params = new URLSearchParams();
    if (statusFilter) params.set("status", statusFilter);
    if (minScore) params.set("min_score", minScore);
    apiClient
      .get(`/company-profiles/${companyId}/prospects?${params.toString()}`)
      .then((res) => setProspects(res.data))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [companyId, statusFilter, minScore]);

  const toggleExpand = async (prospect: Prospect) => {
    if (expandedId === prospect.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(prospect.id);
    const res = await apiClient.get(`/company-profiles/${companyId}/prospects/${prospect.id}/timeline`);
    setTimeline(res.data);
  };

  const runAction = async (prospect: Prospect, action: "approve" | "reject" | "archive") => {
    setActionError(null);
    try {
      if (action === "reject") {
        const reason = window.prompt("Reason for rejecting this prospect?");
        if (!reason) return;
        await apiClient.post(`/company-profiles/${companyId}/prospects/${prospect.id}/reject`, { rejection_reason: reason });
      } else {
        await apiClient.post(`/company-profiles/${companyId}/prospects/${prospect.id}/${action}`);
      }
      load();
    } catch {
      setActionError(`Could not ${action} this prospect.`);
    }
  };

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">Prospects</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Review what Discovery found. Nothing reaches the CRM until you approve it here.
          </p>
        </div>
        <div className="flex gap-2">
          <select className={inputClass} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All statuses</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          <input
            className={inputClass}
            placeholder="Min score"
            type="number"
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
          />
        </div>
      </div>

      {actionError && <p className="mb-4 text-sm text-red-600">{actionError}</p>}
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {!isLoading && prospects.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900">
          No prospects match these filters yet.
        </div>
      )}

      <div className="space-y-3">
        {prospects.map((prospect) => {
          const isOpen = expandedId === prospect.id;
          return (
            <div key={prospect.id} className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
              <button className="flex w-full items-start justify-between text-left" onClick={() => toggleExpand(prospect)}>
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <h3 className="font-semibold text-slate-900 dark:text-slate-100">{prospect.name}</h3>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[prospect.status]}`}>
                      {STATUS_LABELS[prospect.status]}
                    </span>
                    {prospect.potential_duplicate_of_prospect_id && (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900 dark:text-amber-300">
                        possible duplicate ({Math.round((prospect.duplicate_confidence ?? 0) * 100)}%)
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500">
                    {[prospect.website, prospect.country, prospect.company_size_range].filter(Boolean).join(" · ")}
                  </p>
                </div>
                <span className="text-lg font-semibold text-slate-700 dark:text-slate-200">
                  {prospect.total_score != null ? Math.round(prospect.total_score) : "—"}
                </span>
              </button>

              {isOpen && (
                <div className="mt-4 space-y-4 border-t border-slate-100 pt-4 dark:border-slate-700">
                  {prospect.description && <p className="text-sm text-slate-600 dark:text-slate-300">{prospect.description}</p>}

                  {prospect.score_breakdown && prospect.score_breakdown.length > 0 && (
                    <div>
                      <p className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-200">Score breakdown</p>
                      <div className="space-y-2">
                        {prospect.score_breakdown.map((entry, i) => (
                          <div key={i}>
                            <div className="mb-0.5 flex justify-between text-xs text-slate-500">
                              <span>{entry.factor.replace(/_/g, " ")}</span>
                              <span>{entry.points} / {entry.weight}</span>
                            </div>
                            <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-slate-700">
                              <div
                                className="h-2 rounded-full bg-slate-900 dark:bg-indigo-500"
                                style={{ width: `${Math.min(100, (entry.points / entry.weight) * 100)}%` }}
                              />
                            </div>
                            <p className="mt-0.5 text-xs text-slate-400">{entry.explanation}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {prospect.ai_reasoning && (
                    <div>
                      <p className="mb-1 text-sm font-medium text-slate-700 dark:text-slate-200">AI reasoning</p>
                      <p className="text-sm text-slate-600 dark:text-slate-300">{prospect.ai_reasoning}</p>
                    </div>
                  )}

                  {prospect.rejection_reason && (
                    <p className="text-sm text-red-600">Rejected: {prospect.rejection_reason}</p>
                  )}

                  {prospect.contacts.length > 0 && (
                    <div>
                      <p className="mb-1 text-sm font-medium text-slate-700 dark:text-slate-200">Contacts</p>
                      <div className="space-y-1">
                        {prospect.contacts.map((c) => (
                          <p key={c.id} className="text-xs text-slate-500">
                            {[c.name, c.role, c.department, c.decision_maker_level, c.email, c.phone].filter(Boolean).join(" · ")}
                          </p>
                        ))}
                      </div>
                    </div>
                  )}

                  {timeline.length > 0 && (
                    <div>
                      <p className="mb-1 text-sm font-medium text-slate-700 dark:text-slate-200">Timeline</p>
                      <div className="space-y-1">
                        {timeline.map((event) => (
                          <p key={event.id} className="text-xs text-slate-500">
                            {new Date(event.created_at).toLocaleString()} — {event.event_type.replace(/_/g, " ")} ({event.actor})
                          </p>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex gap-2">
                    <Link
                      to={`/businesses/${companyId}/prospects/${prospect.id}/research`}
                      className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300"
                    >
                      Research
                    </Link>
                    <button
                      onClick={() => runAction(prospect, "approve")}
                      className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700"
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => runAction(prospect, "reject")}
                      className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
                    >
                      Reject
                    </button>
                    <button
                      onClick={() => runAction(prospect, "archive")}
                      className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300"
                    >
                      Archive
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
