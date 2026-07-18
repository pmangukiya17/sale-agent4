import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../../api/client";
import { FormSection, Field, inputClass } from "../../components/FormSection";
import { MultiSelect } from "../../components/MultiSelect";
import { Toggle } from "../../components/Toggle";
import { StatusBadge } from "../../components/StatusBadge";

interface ConnectableProvider {
  provider_key: string;
}

interface ProviderConnection {
  id: string;
  provider_key: string;
  external_account_email: string | null;
  status: string;
}

interface SendingProfile {
  id: string;
  provider_connection_id: string | null;
  provider_key: string;
  label: string;
  sender_name: string;
  sender_email: string;
  reply_to_email: string | null;
  is_active: boolean;
  daily_limit: number | null;
  hourly_limit: number | null;
  min_gap_seconds: number | null;
  max_gap_seconds: number | null;
  sending_window_start: string | null;
  sending_window_end: string | null;
  sending_timezone: string | null;
  sending_days: string[] | null;
}

interface ProfileForm {
  provider_key: string;
  provider_connection_id: string;
  label: string;
  sender_name: string;
  sender_email: string;
  reply_to_email: string;
  is_active: boolean;
  daily_limit: string;
  hourly_limit: string;
  min_gap_seconds: string;
  max_gap_seconds: string;
  sending_window_start: string;
  sending_window_end: string;
  sending_timezone: string;
  sending_days: string[];
}

const EMPTY_FORM: ProfileForm = {
  provider_key: "",
  provider_connection_id: "",
  label: "",
  sender_name: "",
  sender_email: "",
  reply_to_email: "",
  is_active: true,
  daily_limit: "",
  hourly_limit: "",
  min_gap_seconds: "",
  max_gap_seconds: "",
  sending_window_start: "",
  sending_window_end: "",
  sending_timezone: "",
  sending_days: [],
};

const WEEKDAY_OPTIONS = [
  { id: "mon", label: "Mon" },
  { id: "tue", label: "Tue" },
  { id: "wed", label: "Wed" },
  { id: "thu", label: "Thu" },
  { id: "fri", label: "Fri" },
  { id: "sat", label: "Sat" },
  { id: "sun", label: "Sun" },
];

const PROVIDER_LABELS: Record<string, string> = { gmail: "Gmail", outlook: "Outlook / Microsoft 365" };

function profileToForm(p: SendingProfile): ProfileForm {
  return {
    provider_key: p.provider_key,
    provider_connection_id: p.provider_connection_id ?? "",
    label: p.label,
    sender_name: p.sender_name,
    sender_email: p.sender_email,
    reply_to_email: p.reply_to_email ?? "",
    is_active: p.is_active,
    daily_limit: p.daily_limit?.toString() ?? "",
    hourly_limit: p.hourly_limit?.toString() ?? "",
    min_gap_seconds: p.min_gap_seconds?.toString() ?? "",
    max_gap_seconds: p.max_gap_seconds?.toString() ?? "",
    sending_window_start: p.sending_window_start ?? "",
    sending_window_end: p.sending_window_end ?? "",
    sending_timezone: p.sending_timezone ?? "",
    sending_days: p.sending_days ?? [],
  };
}

function toIntOrNull(v: string): number | null {
  if (v.trim() === "") return null;
  const n = parseInt(v, 10);
  return Number.isNaN(n) ? null : n;
}

export default function DeliverySendingProfiles() {
  const { companyId } = useParams();
  const [profiles, setProfiles] = useState<SendingProfile[]>([]);
  const [providers, setProviders] = useState<ConnectableProvider[]>([]);
  const [connections, setConnections] = useState<ProviderConnection[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<ProfileForm>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // load() intentionally re-fetches all three lists (profiles, providers,
  // connections) every time it's called, not just on mount. Root cause of
  // the "Mailbox connection: Not connected yet" bug traced live: this
  // component only ever fetched `connections` once, on first mount. If a
  // user had this page open (or reopened it via browser back/forward)
  // before finishing a Connect+OAuth round trip on the Connections tab -
  // e.g. in a second browser tab - `connections` stayed frozen at
  // whatever existed before the mailbox was connected, even though the
  // database already had the new row. Nothing was ever wrong with the
  // backend query or the provider_key filter below; the fix is making
  // sure this page can never show data older than "the moment the form
  // was opened" - see startCreate/startEdit below, which now call load()
  // instead of trusting whatever was fetched on mount.
  const load = () => {
    setIsLoading(true);
    setLoadError(null);
    Promise.all([
      apiClient.get<SendingProfile[]>(`/company-profiles/${companyId}/sending-profiles`),
      apiClient.get<ConnectableProvider[]>("/delivery/providers"),
      apiClient.get<ProviderConnection[]>(`/company-profiles/${companyId}/provider-connections`),
    ])
      .then(([profilesRes, providersRes, connectionsRes]) => {
        setProfiles(profilesRes.data);
        setProviders(providersRes.data);
        setConnections(connectionsRes.data);
      })
      .catch(() => {
        // Previously silent: if any of the three requests failed,
        // Promise.all rejected, none of the three setters ran, and the
        // page rendered as if everything were empty with no indication
        // anything went wrong - indistinguishable from "you genuinely
        // have no connections yet." Surface it instead.
        setLoadError("Could not load sending profiles, providers, or mailbox connections. Try refreshing the page.");
      })
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [companyId]);

  const update = <K extends keyof ProfileForm>(key: K, value: ProfileForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const startCreate = () => {
    load();
    setEditingId(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
  };

  const startEdit = (p: SendingProfile) => {
    load();
    setEditingId(p.id);
    setForm(profileToForm(p));
    setShowForm(true);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const basePayload = {
      label: form.label,
      sender_name: form.sender_name,
      sender_email: form.sender_email,
      reply_to_email: form.reply_to_email || null,
      is_active: form.is_active,
      provider_connection_id: form.provider_connection_id || null,
      daily_limit: toIntOrNull(form.daily_limit),
      hourly_limit: toIntOrNull(form.hourly_limit),
      min_gap_seconds: toIntOrNull(form.min_gap_seconds),
      max_gap_seconds: toIntOrNull(form.max_gap_seconds),
      sending_window_start: form.sending_window_start || null,
      sending_window_end: form.sending_window_end || null,
      sending_timezone: form.sending_timezone || null,
      sending_days: form.sending_days.length > 0 ? form.sending_days : null,
    };
    try {
      if (editingId) {
        // provider_key is deliberately omitted here - SendingProfileUpdate
        // doesn't accept it (changing provider type is a Reconnect-level
        // decision, not a plain field edit - see the schema's docstring).
        await apiClient.put(`/company-profiles/${companyId}/sending-profiles/${editingId}`, basePayload);
      } else {
        await apiClient.post(`/company-profiles/${companyId}/sending-profiles`, {
          ...basePayload,
          provider_key: form.provider_key,
        });
      }
      setShowForm(false);
      load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Could not save this sending profile.");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this sending profile?")) return;
    try {
      await apiClient.delete(`/company-profiles/${companyId}/sending-profiles/${id}`);
      load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Could not delete this sending profile.");
    }
  };

  // Only offer connections whose provider_key matches what's selected -
  // attaching a Gmail connection to an Outlook-typed profile is rejected
  // server-side (see sending_profiles.py's _validate_provider_connection),
  // so the form shouldn't offer it in the first place.
  const matchingConnections = connections.filter((c) => c.provider_key === form.provider_key);

  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>;

  return (
    <div>
      {loadError && (
        <div className="mb-4 rounded-md border border-red-300 bg-red-50 px-4 py-2.5 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
          {loadError}
        </div>
      )}
      <div className="mb-6 flex items-center justify-between">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Named sending identities - "CEO", "Sales", "Support" - each backed by a connected mailbox.
        </p>
        <button
          onClick={startCreate}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:bg-indigo-600 dark:hover:bg-indigo-500"
        >
          + Add sending profile
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="mb-6">
          <FormSection title={editingId ? "Edit sending profile" : "New sending profile"}>
            <Field label="Label">
              <input required className={inputClass} value={form.label} onChange={(e) => update("label", e.target.value)} placeholder="e.g. CEO" />
            </Field>
            <Field label="Provider">
              <select
                required
                disabled={!!editingId}
                className={inputClass}
                value={form.provider_key}
                onChange={(e) => update("provider_key", e.target.value)}
              >
                <option value="" disabled>
                  Select a provider…
                </option>
                {providers.map((p) => (
                  <option key={p.provider_key} value={p.provider_key}>
                    {PROVIDER_LABELS[p.provider_key] ?? p.provider_key}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Sender name">
              <input required className={inputClass} value={form.sender_name} onChange={(e) => update("sender_name", e.target.value)} />
            </Field>
            <Field label="Sender email">
              <input required type="email" className={inputClass} value={form.sender_email} onChange={(e) => update("sender_email", e.target.value)} />
            </Field>
            <Field label="Reply-to email">
              <input type="email" className={inputClass} value={form.reply_to_email} onChange={(e) => update("reply_to_email", e.target.value)} />
            </Field>
            <Field label="Mailbox connection">
              <select className={inputClass} value={form.provider_connection_id} onChange={(e) => update("provider_connection_id", e.target.value)}>
                <option value="">Not connected yet</option>
                {matchingConnections.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.external_account_email ?? c.id} ({c.status})
                  </option>
                ))}
              </select>
              {form.provider_key && matchingConnections.length === 0 && (
                <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                  No {PROVIDER_LABELS[form.provider_key] ?? form.provider_key} mailbox is connected for this business
                  yet - connect one under Connections first, then reopen this form.
                </p>
              )}
            </Field>
            <Field label="Active">
              <Toggle checked={form.is_active} onChange={(v) => update("is_active", v)} />
            </Field>
          </FormSection>

          <FormSection
            title="Scheduling defaults"
            description="Optional - a campaign using this profile can override any of these. Leave blank to use the system default."
          >
            <Field label="Daily limit">
              <input type="number" min={0} className={inputClass} value={form.daily_limit} onChange={(e) => update("daily_limit", e.target.value)} />
            </Field>
            <Field label="Hourly limit">
              <input type="number" min={0} className={inputClass} value={form.hourly_limit} onChange={(e) => update("hourly_limit", e.target.value)} />
            </Field>
            <Field label="Min gap (seconds)">
              <input type="number" min={0} className={inputClass} value={form.min_gap_seconds} onChange={(e) => update("min_gap_seconds", e.target.value)} />
            </Field>
            <Field label="Max gap (seconds)">
              <input type="number" min={0} className={inputClass} value={form.max_gap_seconds} onChange={(e) => update("max_gap_seconds", e.target.value)} />
            </Field>
            <Field label="Sending window start">
              <input type="time" className={inputClass} value={form.sending_window_start} onChange={(e) => update("sending_window_start", e.target.value)} />
            </Field>
            <Field label="Sending window end">
              <input type="time" className={inputClass} value={form.sending_window_end} onChange={(e) => update("sending_window_end", e.target.value)} />
            </Field>
            <Field label="Sending timezone">
              <input
                className={inputClass}
                placeholder="e.g. Europe/Berlin"
                value={form.sending_timezone}
                onChange={(e) => update("sending_timezone", e.target.value)}
              />
            </Field>
            <Field label="Sending days" full>
              <MultiSelect options={WEEKDAY_OPTIONS} selected={form.sending_days} onChange={(v) => update("sending_days", v)} />
            </Field>
          </FormSection>

          {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:bg-indigo-600 dark:hover:bg-indigo-500"
            >
              Save sending profile
            </button>
          </div>
        </form>
      )}

      {!isLoading && profiles.length === 0 && !showForm && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900">
          No sending profiles yet.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {profiles.map((p) => (
          <div key={p.id} className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
            <div className="mb-2 flex items-start justify-between">
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">{p.label}</h3>
              <StatusBadge label={p.is_active ? "active" : "inactive"} tone={p.is_active ? "success" : "neutral"} />
            </div>
            <p className="mb-1 text-xs text-slate-500">{PROVIDER_LABELS[p.provider_key] ?? p.provider_key}</p>
            <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
              {p.sender_name} &lt;{p.sender_email}&gt;
            </p>
            {!p.provider_connection_id && (
              <p className="mb-3 text-xs text-amber-600 dark:text-amber-400">No mailbox connected - can't send yet.</p>
            )}
            <div className="flex gap-2 text-sm">
              <button
                onClick={() => startEdit(p)}
                className="rounded-md border border-slate-200 px-3 py-1.5 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Edit
              </button>
              <button
                onClick={() => handleDelete(p.id)}
                className="rounded-md border border-slate-200 px-3 py-1.5 text-red-600 hover:bg-red-50 dark:border-slate-700"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
