import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { FormSection, Field, inputClass } from "../components/FormSection";
import { Toggle } from "../components/Toggle";

type SearchDepth = "quick" | "standard" | "deep";
type SearchFrequency = "manual" | "daily" | "weekly";

interface SearchTemplate {
  id: string;
  name: string;
  description: string | null;
  is_system_default: boolean;
}

interface IcpOption {
  id: string;
  name: string;
  version: number;
  is_active: boolean;
}

interface DiscoverySearch {
  id: string;
  name: string;
  search_template_id: string;
  icp_criteria_id: string | null;
  provider_keys: string[];
  search_depth: SearchDepth;
  search_frequency: SearchFrequency;
  is_active: boolean;
  search_template: SearchTemplate;
}

interface DiscoveryJobProviderRun {
  provider_key: string;
  status: string;
  duration_ms: number | null;
  request_count: number;
  api_cost: number | null;
  token_usage: number | null;
  error_message: string | null;
}

interface DiscoveryJob {
  id: string;
  status: string;
  raw_result_count: number;
  prospect_created_count: number;
  prospect_matched_count: number;
  error_message: string | null;
  provider_runs: DiscoveryJobProviderRun[];
}

const AVAILABLE_PROVIDERS = [{ key: "manual_csv", label: "Manual / CSV Import" }];

interface SearchForm {
  name: string;
  search_template_id: string;
  icp_criteria_id: string;
  provider_keys: string[];
  search_depth: SearchDepth;
  search_frequency: SearchFrequency;
  is_active: boolean;
}

const EMPTY_FORM: SearchForm = {
  name: "",
  search_template_id: "",
  icp_criteria_id: "",
  provider_keys: ["manual_csv"],
  search_depth: "standard",
  search_frequency: "manual",
  is_active: true,
};

export default function DiscoverySearches() {
  const { companyId } = useParams();
  const [searches, setSearches] = useState<DiscoverySearch[]>([]);
  const [templates, setTemplates] = useState<SearchTemplate[]>([]);
  const [icps, setIcps] = useState<IcpOption[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<SearchForm>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [jobResults, setJobResults] = useState<Record<string, DiscoveryJob>>({});

  const load = () => {
    setIsLoading(true);
    Promise.all([
      apiClient.get(`/company-profiles/${companyId}/discovery-searches`),
      apiClient.get(`/company-profiles/${companyId}/search-templates`),
      apiClient.get(`/company-profiles/${companyId}/icp-criteria`),
    ]).then(([searchRes, templateRes, icpRes]) => {
      setSearches(searchRes.data);
      setTemplates(templateRes.data);
      setIcps(icpRes.data);
      setIsLoading(false);
    });
  };

  useEffect(load, [companyId]);

  const update = <K extends keyof SearchForm>(key: K, value: SearchForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!form.search_template_id) {
      setError("Choose a search template - every search must derive from one.");
      return;
    }
    try {
      await apiClient.post(`/company-profiles/${companyId}/discovery-searches`, {
        name: form.name,
        search_template_id: form.search_template_id,
        icp_criteria_id: form.icp_criteria_id || null,
        provider_keys: form.provider_keys,
        search_depth: form.search_depth,
        search_frequency: form.search_frequency,
        is_active: form.is_active,
        query_spec: {},
      });
      setShowForm(false);
      setForm(EMPTY_FORM);
      load();
    } catch {
      setError("Could not save this search.");
    }
  };

  const handleRun = async (searchId: string) => {
    setRunningId(searchId);
    setError(null);
    try {
      const res = await apiClient.post(`/company-profiles/${companyId}/discovery-searches/${searchId}/run`);
      setJobResults((prev) => ({ ...prev, [searchId]: res.data }));
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "This search could not be run.");
    } finally {
      setRunningId(null);
    }
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">Discovery Searches</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Every search runs manually and synchronously - click Run and the result comes back in the same request.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:bg-indigo-600 dark:hover:bg-indigo-500"
        >
          + New search
        </button>
      </div>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {showForm && (
        <form onSubmit={handleSubmit} className="mb-6">
          <FormSection title="New Discovery Search">
            <Field label="Name" full>
              <input required className={inputClass} value={form.name} onChange={(e) => update("name", e.target.value)} />
            </Field>
            <Field label="Search Template">
              <select
                required
                className={inputClass}
                value={form.search_template_id}
                onChange={(e) => update("search_template_id", e.target.value)}
              >
                <option value="">Select a template...</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}{t.is_system_default ? " (system)" : ""}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="ICP Criteria (blank = use active version)">
              <select className={inputClass} value={form.icp_criteria_id} onChange={(e) => update("icp_criteria_id", e.target.value)}>
                <option value="">Use active ICP at run time</option>
                {icps.map((icp) => (
                  <option key={icp.id} value={icp.id}>
                    {icp.name} (v{icp.version}){icp.is_active ? " - active" : ""}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Search depth">
              <select className={inputClass} value={form.search_depth} onChange={(e) => update("search_depth", e.target.value as SearchDepth)}>
                <option value="quick">Quick</option>
                <option value="standard">Standard</option>
                <option value="deep">Deep</option>
              </select>
            </Field>
            <Field label="Search frequency">
              <select className={inputClass} value={form.search_frequency} onChange={(e) => update("search_frequency", e.target.value as SearchFrequency)}>
                <option value="manual">Manual</option>
                <option value="daily">Daily (not yet automated)</option>
                <option value="weekly">Weekly (not yet automated)</option>
              </select>
            </Field>
            <Field label="Active">
              <Toggle checked={form.is_active} onChange={(v) => update("is_active", v)} />
            </Field>
            <Field label="Providers" full>
              <div className="flex flex-wrap gap-3">
                {AVAILABLE_PROVIDERS.map((p) => (
                  <label key={p.key} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                    <input
                      type="checkbox"
                      checked={form.provider_keys.includes(p.key)}
                      onChange={() =>
                        update(
                          "provider_keys",
                          form.provider_keys.includes(p.key)
                            ? form.provider_keys.filter((k) => k !== p.key)
                            : [...form.provider_keys, p.key]
                        )
                      }
                    />
                    {p.label}
                  </label>
                ))}
              </div>
            </Field>
          </FormSection>
          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300"
            >
              Cancel
            </button>
            <button type="submit" className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:bg-indigo-600 dark:hover:bg-indigo-500">
              Save search
            </button>
          </div>
        </form>
      )}

      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}

      {!isLoading && searches.length === 0 && !showForm && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900">
          No discovery searches yet. Create one from a search template to start finding prospects.
        </div>
      )}

      <div className="space-y-4">
        {searches.map((search) => {
          const job = jobResults[search.id];
          return (
            <div key={search.id} className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
              <div className="mb-2 flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-slate-900 dark:text-slate-100">{search.name}</h3>
                  <p className="text-xs text-slate-500">
                    Template: {search.search_template.name} · Depth: {search.search_depth} · Providers: {search.provider_keys.join(", ") || "none"}
                  </p>
                </div>
                <button
                  onClick={() => handleRun(search.id)}
                  disabled={runningId === search.id}
                  className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50 dark:bg-indigo-600 dark:hover:bg-indigo-500"
                >
                  {runningId === search.id ? "Running…" : "Run"}
                </button>
              </div>

              {job && (
                <div className="mt-3 rounded-md border border-slate-100 bg-slate-50 p-3 text-sm dark:border-slate-700 dark:bg-slate-800">
                  <p className="mb-2 font-medium text-slate-700 dark:text-slate-200">
                    Job {job.status} — {job.raw_result_count} raw results, {job.prospect_created_count} new prospects, {job.prospect_matched_count} re-seen
                  </p>
                  {job.error_message && <p className="mb-2 text-red-600">{job.error_message}</p>}
                  <div className="space-y-1">
                    {job.provider_runs.map((pr, i) => (
                      <div key={i} className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
                        <span>{pr.provider_key} — {pr.status}</span>
                        <span>
                          {pr.duration_ms != null ? `${pr.duration_ms}ms` : ""} · {pr.request_count} req
                          {pr.api_cost != null ? ` · $${pr.api_cost}` : ""}
                          {pr.token_usage != null ? ` · ${pr.token_usage} tok` : ""}
                          {pr.error_message ? ` · ${pr.error_message}` : ""}
                        </span>
                      </div>
                    ))}
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
