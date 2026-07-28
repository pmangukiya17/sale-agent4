import { useState } from "react";
import { Button, Card, Input, PlaceholderNotice, useToast } from "../../design-system";
import { useAuth } from "../../auth/AuthContext";
import { useModelRoles } from "../hooks/useModelRoles";

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

/**
 * ModelRoleManagementPanel — M8.3 Step 3 (AI Gateway Management &
 * Control, Model Role Management). Renders inside AIGatewaySettings.tsx,
 * below the existing (M8.2) read-only "Local Model Roles" card - THAT
 * card keeps showing the CODE-level `LOCAL_MODEL_ROLES`/
 * `CAPABILITY_LOCAL_MODEL_ROLE` tables exactly as before (unaffected by
 * this step); THIS card is the new DB-backed override layer sitting in
 * front of it (see `app.ai_gateway.local_model_policy.resolve_local_model()`'s
 * own docstring for the full resolution order).
 *
 * Per CEO decision #2 (local-tier only): every role saved here ONLY ever
 * changes which model `LocalOllamaProviderClient` asks a local server
 * for on a matching capability - it can never change which PROVIDER
 * (local/free/premium) a capability routes to, and it never touches any
 * cloud ProviderClient (Claude/OpenAI/Gemini/Groq). Adding a brand-new
 * role name here (e.g. "coding", "vision", "reasoning", "embeddings") is
 * literally how a new semantic role gets added - no settings key, no
 * code deploy required (see `AIModelRole`'s own docstring for the "future
 * models addable without business-logic changes" requirement this
 * satisfies).
 *
 * Write access (add/edit/delete) is gated on the CALLER's own role
 * client-side (`useAuth().user?.role`) - purely a UX courtesy, same
 * precedent `ProviderConfigPanel.tsx` already established; the backend's
 * GET/PUT/DELETE `/ai-gateway/model-roles*` routes are independently
 * admin-gated (`get_current_active_admin`) regardless of what this
 * component renders. A non-admin sees the current roles read-only.
 */
export function ModelRoleManagementPanel() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const { data: roles, isLoading, error, isSaving, save, remove } = useModelRoles();
  const { showToast } = useToast();

  const [editingRole, setEditingRole] = useState<string | null>(null);
  const [modelInput, setModelInput] = useState("");
  const [enabledInput, setEnabledInput] = useState(true);

  const [isAddingNew, setIsAddingNew] = useState(false);
  const [newRoleName, setNewRoleName] = useState("");
  const [newModelInput, setNewModelInput] = useState("");

  function startEdit(roleName: string, currentModel: string, currentEnabled: boolean) {
    setEditingRole(roleName);
    setModelInput(currentModel);
    setEnabledInput(currentEnabled);
  }

  function cancelEdit() {
    setEditingRole(null);
    setModelInput("");
  }

  async function handleSaveEdit(roleName: string) {
    try {
      await save(roleName, { model: modelInput.trim() || undefined, enabled: enabledInput });
      showToast({ message: `Role "${roleName}" saved.`, tone: "success" });
      cancelEdit();
    } catch {
      showToast({ message: `Could not save role "${roleName}".`, tone: "danger" });
    }
  }

  async function handleDelete(roleName: string) {
    try {
      await remove(roleName);
      showToast({ message: `Role "${roleName}" deleted.`, tone: "success" });
    } catch {
      showToast({ message: `Could not delete role "${roleName}".`, tone: "danger" });
    }
  }

  async function handleCreate() {
    const roleName = newRoleName.trim();
    if (!roleName || !newModelInput.trim()) {
      showToast({ message: "A role name and model are both required.", tone: "danger" });
      return;
    }
    try {
      await save(roleName, { model: newModelInput.trim(), enabled: true });
      showToast({ message: `Role "${roleName}" created.`, tone: "success" });
      setIsAddingNew(false);
      setNewRoleName("");
      setNewModelInput("");
    } catch {
      showToast({ message: `Could not create role "${roleName}".`, tone: "danger" });
    }
  }

  if (isLoading) {
    return <div className="h-32 animate-pulse rounded-card border border-border-hairline bg-surface-1" />;
  }
  if (error) {
    return <PlaceholderNotice kind="no-data" reason={error} />;
  }

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">Model Role Overrides</h3>
          <p className="mt-0.5 text-[11px] text-slate-500">
            DB-backed role → local model assignments. Overrides the code-level table above; a role with no override
            here falls back to it. Local-tier only — never affects which provider a capability routes to.
          </p>
        </div>
        {!isAdmin && <span className="whitespace-nowrap text-[11px] text-slate-500">Read-only (admin required to edit)</span>}
      </div>

      {roles.length === 0 && !isAddingNew ? (
        <p className="text-xs text-slate-500">No DB-backed role overrides saved yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {roles.map((role) => (
            <li key={role.roleName} className="rounded-lg border border-border-hairline bg-surface-2 p-3 text-xs">
              {editingRole === role.roleName ? (
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <span className="w-28 shrink-0 font-medium text-slate-200">{role.roleName}</span>
                  <Input
                    value={modelInput}
                    onChange={(e) => setModelInput(e.target.value)}
                    placeholder="e.g. qwen3:14b"
                    className="flex-1"
                  />
                  <label className="flex items-center gap-1.5 whitespace-nowrap text-slate-400">
                    <input
                      type="checkbox"
                      checked={enabledInput}
                      onChange={(e) => setEnabledInput(e.target.checked)}
                      className="h-3.5 w-3.5 rounded border-border-hairline bg-surface-2 accent-accent-primary"
                    />
                    Enabled
                  </label>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => handleSaveEdit(role.roleName)} isLoading={isSaving}>
                      Save
                    </Button>
                    <Button size="sm" variant="secondary" onClick={cancelEdit}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="w-28 shrink-0 font-medium text-slate-200">{role.roleName}</span>
                    <span className={role.enabled ? "text-slate-200" : "text-slate-500 line-through"}>{role.model}</span>
                    {!role.enabled && <span className="text-[10px] uppercase tracking-wide text-slate-500">Disabled</span>}
                  </div>
                  {isAdmin ? (
                    <div className="flex shrink-0 gap-2">
                      <Button size="sm" variant="secondary" onClick={() => startEdit(role.roleName, role.model, role.enabled)}>
                        Edit
                      </Button>
                      <Button size="sm" variant="destructive" onClick={() => handleDelete(role.roleName)} isLoading={isSaving}>
                        Delete
                      </Button>
                    </div>
                  ) : (
                    <span className="shrink-0 text-[11px] text-slate-500">
                      {formatDateTime(role.updatedAt)}
                      {role.updatedByUserEmail ? ` · ${role.updatedByUserEmail}` : ""}
                    </span>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {isAdmin && (
        <div className="border-t border-border-hairline pt-3">
          {isAddingNew ? (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Input
                value={newRoleName}
                onChange={(e) => setNewRoleName(e.target.value)}
                placeholder="Role name, e.g. coding"
                className="w-full sm:w-40"
              />
              <Input
                value={newModelInput}
                onChange={(e) => setNewModelInput(e.target.value)}
                placeholder="Model, e.g. codellama:13b"
                className="flex-1"
              />
              <div className="flex gap-2">
                <Button size="sm" onClick={handleCreate} isLoading={isSaving}>
                  Create
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setIsAddingNew(false);
                    setNewRoleName("");
                    setNewModelInput("");
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <Button size="sm" variant="secondary" onClick={() => setIsAddingNew(true)}>
              + Add role
            </Button>
          )}
        </div>
      )}
    </Card>
  );
}
