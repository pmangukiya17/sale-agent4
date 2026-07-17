import { useEffect, useState, type FormEvent } from "react";
import { apiClient } from "../api/client";
import { FormSection, Field, inputClass } from "../components/FormSection";
import { Breadcrumbs } from "../components/Breadcrumbs";

type DateFormat = "DD/MM/YYYY" | "MM/DD/YYYY" | "YYYY-MM-DD";
type TimeFormat = "12h" | "24h";

interface ReferenceOption {
  id: string;
  name: string;
}

interface WorkspaceSettingsForm {
  default_timezone: string;
  default_language_id: string;
  default_currency_id: string;
  date_format: DateFormat;
  time_format: TimeFormat;
}

const EMPTY_FORM: WorkspaceSettingsForm = {
  default_timezone: "",
  default_language_id: "",
  default_currency_id: "",
  date_format: "YYYY-MM-DD",
  time_format: "24h",
};

export default function WorkspaceSettingsPage() {
  const [form, setForm] = useState<WorkspaceSettingsForm>(EMPTY_FORM);
  const [languages, setLanguages] = useState<ReferenceOption[]>([]);
  const [currencies, setCurrencies] = useState<ReferenceOption[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiClient.get("/workspace-settings"),
      apiClient.get("/languages"),
      apiClient.get("/currencies"),
    ]).then(([settingsRes, langRes, currRes]) => {
      const data = settingsRes.data;
      setForm({
        default_timezone: data.default_timezone ?? "",
        default_language_id: data.default_language?.id ?? "",
        default_currency_id: data.default_currency?.id ?? "",
        date_format: data.date_format,
        time_format: data.time_format,
      });
      setLanguages(langRes.data);
      setCurrencies(currRes.data);
      setIsLoading(false);
    });
  }, []);

  const update = <K extends keyof WorkspaceSettingsForm>(key: K, value: WorkspaceSettingsForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setError(null);
    try {
      await apiClient.put("/workspace-settings", {
        default_timezone: form.default_timezone || null,
        default_language_id: form.default_language_id || null,
        default_currency_id: form.default_currency_id || null,
        date_format: form.date_format,
        time_format: form.time_format,
      });
      setSaved(true);
    } catch {
      setError("Could not save workspace settings.");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>;

  return (
    <div className="mx-auto max-w-2xl">
      <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Workspace Settings" }]} />

      <h2 className="mb-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">Workspace Settings</h2>
      <p className="mb-6 text-sm text-slate-500 dark:text-slate-400">
        Account-level defaults. Individual businesses can still override their own timezone.
      </p>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}
      {saved && <p className="mb-4 text-sm text-emerald-600">Saved.</p>}

      <form onSubmit={handleSubmit}>
        <FormSection title="Defaults">
          <Field label="Default timezone (IANA)">
            <input
              className={inputClass}
              value={form.default_timezone}
              onChange={(e) => update("default_timezone", e.target.value)}
              placeholder="e.g. Asia/Kolkata"
            />
          </Field>
          <Field label="Default language">
            <select
              className={inputClass}
              value={form.default_language_id}
              onChange={(e) => update("default_language_id", e.target.value)}
            >
              <option value="">—</option>
              {languages.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Default currency">
            <select
              className={inputClass}
              value={form.default_currency_id}
              onChange={(e) => update("default_currency_id", e.target.value)}
            >
              <option value="">—</option>
              {currencies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Date format">
            <select
              className={inputClass}
              value={form.date_format}
              onChange={(e) => update("date_format", e.target.value as DateFormat)}
            >
              <option value="YYYY-MM-DD">YYYY-MM-DD</option>
              <option value="DD/MM/YYYY">DD/MM/YYYY</option>
              <option value="MM/DD/YYYY">MM/DD/YYYY</option>
            </select>
          </Field>
          <Field label="Time format">
            <select
              className={inputClass}
              value={form.time_format}
              onChange={(e) => update("time_format", e.target.value as TimeFormat)}
            >
              <option value="24h">24-hour</option>
              <option value="12h">12-hour</option>
            </select>
          </Field>
        </FormSection>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={isSaving}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50 dark:bg-indigo-600 dark:hover:bg-indigo-500"
          >
            {isSaving ? "Saving…" : "Save settings"}
          </button>
        </div>
      </form>
    </div>
  );
}
