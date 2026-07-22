import { useState } from "react";
import axios from "axios";
import { apiClient } from "../api/client";
import { useToast } from "../design-system";

/**
 * useDeleteResource — M8.17 (Global Delete System). The one shared
 * delete flow every entity-list page in this app uses: request delete
 * on a row -> ConfirmDialog opens -> confirm calls DELETE on the given
 * endpoint -> success/error toast -> caller's own list refreshes.
 *
 * Scope, matching the CEO-approved M8.17 boundaries exactly: this hook
 * (and the endpoints it's wired to) only ever targets user-owned
 * configuration/content that already has a real backend DELETE route -
 * Products, Knowledge Base entries, Research/Personalization/Search
 * templates, Outreach playbooks, ICP criteria, Discovery searches,
 * Sending profiles. Every one of those routes already centralizes
 * ownership validation via `get_owned_company_profile`
 * (backend/app/api/deps.py) - this hook does not re-implement that
 * check client-side, it only calls the endpoint and surfaces whatever
 * the backend decides (a 404 here means "not yours," not a bug).
 *
 * Explicitly NOT used for: reference data (countries/currencies/
 * languages/industries/buyer types - excluded entirely, no delete route
 * exists or should exist for them), execution history (Discovery/
 * Research/Personalization/Outreach jobs and runs - immutable, no
 * delete route exists), or Prospects (which already has a real archive
 * lifecycle - approve/reject/archive in Prospects.tsx - and should keep
 * using that instead of a new hard-delete path, per the approved scope).
 *
 * Deliberately per-page, not a single app-wide singleton: each page
 * instantiates its own `useDeleteResource` with its own `entityLabel`/
 * `buildUrl`/`onDeleted`, so a page's own list-refresh logic
 * (`load()`, `setItems(prev => ...)`, etc.) stays exactly as varied as
 * it already is per page - this hook only unifies the confirm/request/
 * toast plumbing around that, not each page's own data-fetching shape.
 */
export interface UseDeleteResourceOptions {
  /** Singular, capitalized - used in toast/dialog copy, e.g. "Product". */
  entityLabel: string;
  /** Builds the DELETE endpoint path for a given id. */
  buildUrl: (id: string) => string;
  /** Called after a successful delete - typically the page's own
   * `load()`/refetch, or a local `setItems` filter for an optimistic
   * update without a full reload. */
  onDeleted: (id: string) => void;
}

export function useDeleteResource({ entityLabel, buildUrl, onDeleted }: UseDeleteResourceOptions) {
  const { showToast } = useToast();
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const requestDelete = (id: string) => {
    if (!isDeleting) setPendingId(id);
  };

  const cancel = () => {
    if (!isDeleting) setPendingId(null);
  };

  const confirmDelete = async () => {
    if (!pendingId) return;
    setIsDeleting(true);
    try {
      await apiClient.delete(buildUrl(pendingId));
      showToast({ message: `${entityLabel} deleted.`, tone: "success" });
      onDeleted(pendingId);
      setPendingId(null);
    } catch (error) {
      const detail = axios.isAxiosError(error) ? (error.response?.data as { detail?: string } | undefined)?.detail : undefined;
      showToast({ message: detail ?? `Could not delete this ${entityLabel.toLowerCase()}.`, tone: "danger" });
    } finally {
      setIsDeleting(false);
    }
  };

  return { pendingId, isDeleting, requestDelete, cancel, confirmDelete };
}
