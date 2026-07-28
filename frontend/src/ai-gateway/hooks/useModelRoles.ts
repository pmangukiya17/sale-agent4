import { useCallback, useEffect, useState } from "react";
import { useGatewayDataProvider } from "../providers/GatewayDataProviderContext";
import type { ModelRole, ModelRoleWrite } from "../types";

/**
 * useModelRoles — M8.3 Step 3 (AI Gateway Management & Control, Model Role
 * Management). Same shape/contract convention `useProviderConfig.ts`
 * already established: a provider-abstraction-backed { data, isLoading,
 * error, refresh } read, plus `save()`/`remove()` actions since this is a
 * write surface. Unlike `useProviderConfig` (a single provider_key's one
 * row), this hook manages the WHOLE LIST at once - Model Role Management's
 * editor UI is a list with inline add/edit/delete, not a per-role detail
 * page, since role names are open-ended (see `ModelRole`'s own docstring
 * in ../types.ts for why there's no fixed universe of rows to page
 * between).
 *
 * `save()`/`remove()` both call `refresh()` afterward (unlike
 * `useProviderConfig.save()`, which updates local state directly from the
 * PUT response) - deleting/creating a role changes the SHAPE of the list
 * itself (not just one row's fields), so re-fetching the full list is the
 * simplest way to keep ordering/membership correct without hand-rolling
 * list-splice logic here.
 */
export function useModelRoles() {
  const provider = useGatewayDataProvider();
  const [data, setData] = useState<ModelRole[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const refresh = useCallback(() => {
    setIsLoading(true);
    setError(null);
    provider
      .listModelRoles()
      .then(setData)
      .catch(() => setError("Could not load model roles."))
      .finally(() => setIsLoading(false));
  }, [provider]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const save = useCallback(
    async (roleName: string, patch: ModelRoleWrite): Promise<ModelRole> => {
      setIsSaving(true);
      try {
        const updated = await provider.saveModelRole(roleName, patch);
        await provider.listModelRoles().then(setData);
        return updated;
      } finally {
        setIsSaving(false);
      }
    },
    [provider]
  );

  const remove = useCallback(
    async (roleName: string): Promise<void> => {
      setIsSaving(true);
      try {
        await provider.deleteModelRole(roleName);
        await provider.listModelRoles().then(setData);
      } finally {
        setIsSaving(false);
      }
    },
    [provider]
  );

  return { data, isLoading, error, isSaving, refresh, save, remove };
}
