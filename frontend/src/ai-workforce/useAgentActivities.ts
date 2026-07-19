import { useCallback, useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { useCompanies } from "../companies/CompanyContext";

/**
 * AgentActivity — the AI Workforce domain contract from the backend's new
 * M8.4 addition (GET /company-profiles/{id}/ai-workforce/activities).
 * Deliberately mirrors app/schemas/ai_workforce.py's AgentActivityRead
 * field-for-field - this is the frontend half of the same storage/domain
 * boundary the backend mapper enforces. Nothing here reaches for
 * "workflow_instance" naming or WorkflowInstanceStatus values directly.
 */
export type AgentActivityState = "queued" | "running" | "waiting" | "paused" | "completed" | "failed" | "cancelled";

export interface AgentActivity {
  id: string;
  company_profile_id: string;
  workflow_key: string;
  state: AgentActivityState;
  current_step_id: string;
  current_action_key: string | null;
  subject_type: string | null;
  subject_id: string | null;
  started_at: string | null;
  updated_at: string;
  completed_at: string | null;
  created_at: string;
}

export function useAgentActivities() {
  const { activeCompanyId, isLoading: companiesLoading } = useCompanies();
  const [activities, setActivities] = useState<AgentActivity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!activeCompanyId) {
      setActivities([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    apiClient
      .get<AgentActivity[]>(`/company-profiles/${activeCompanyId}/ai-workforce/activities`, { params: { limit: 100 } })
      .then((res) => setActivities(res.data))
      .catch(() => setError("Could not load AI Workforce activity."))
      .finally(() => setIsLoading(false));
  }, [activeCompanyId]);

  useEffect(() => {
    if (companiesLoading) return;
    refresh();
  }, [companiesLoading, refresh]);

  return {
    activities,
    isLoading: isLoading || companiesLoading,
    error,
    hasActiveCompany: Boolean(activeCompanyId),
    refresh,
  };
}
