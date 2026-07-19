import { useEffect, useState } from "react";
import { apiClient } from "../api/client";

export type AgentActivityTraceStatus = "pending" | "running" | "succeeded" | "failed" | "skipped";

export interface AgentActivityTraceEntry {
  id: string;
  agent_activity_id: string;
  step_id: string;
  action_key: string;
  attempt_number: number;
  status: AgentActivityTraceStatus;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

/**
 * Per-agent execution trace (Design Bible Section 9: "AI Agents ... grid
 * of agent cards + per-agent execution trace"), backed by GET
 * .../ai-workforce/activities/{id}/trace. Only fetched when an activity
 * card is selected/expanded, not for the whole roster at once.
 */
export function useActivityTrace(companyProfileId: string | null, activityId: string | null) {
  const [entries, setEntries] = useState<AgentActivityTraceEntry[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!companyProfileId || !activityId) {
      setEntries([]);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    apiClient
      .get<AgentActivityTraceEntry[]>(`/company-profiles/${companyProfileId}/ai-workforce/activities/${activityId}/trace`)
      .then((res) => {
        if (!cancelled) setEntries(res.data);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load execution trace.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [companyProfileId, activityId]);

  return { entries, isLoading, error };
}
