import { useEffect, useRef, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { FormSection, Field, inputClass } from "../components/FormSection";
import { TagInput } from "../components/TagInput";
import { MultiSelect, type MultiSelectOption } from "../components/MultiSelect";
import { Toggle } from "../components/Toggle";
import { Button, Input, Select } from "../design-system";

type SearchDepth = "quick" | "standard" | "deep";
type SearchFrequency = "manual" | "daily" | "weekly";

interface ICPCriteria {
  id: string;
  version: number;
  name: string;
  weight: number;
  is_active: boolean;
  preferred_company_size: string[] | null;
  minimum_confidence_score: number | null;
  exclude_duplicate_companies: boolean;
  search_depth: SearchDepth;
  search_frequency: SearchFrequency;
  target_buyer_types: { id: string; name: string }[];
  target_markets: { id: string; name: string }[];
  excluded_countries: { id: string; name: string }[];
  languages: { id: string; name: string }[];
}

interface ICPForm {
  name: string;
  weight: number;
  is_active: boolean;
  preferred_company_size: string[];
  minimum_confidence_score: string;
  exclude_duplicate_companies: boolean;
  search_depth: SearchDepth;
  search_frequency: SearchFrequency;
  target_buyer_type_ids: string[];
  target_market_country_ids: string[];
  excluded_country_ids: string[];
  language_ids: string[];
}

const EMPTY_FORM: ICPForm = {
  name: "Primary ICP",
  weight: 1,
  is_active: true,
  preferred_company_size: [],
  minimum_confidence_score: "",
  exclude_duplicate_companies: true,
  search_depth: "standard",
  search_frequency: "manual",
  target_buyer_type_ids: [],
  target_market_country_ids: [],
  excluded_country_ids: [],
  language_ids: [],
};

function toForm(icp: ICPCriteria): ICPForm {
  return {
    name: icp.name,
    weight: icp.weight,
    is_active: icp.is_active,
    preferred_company_size: icp.preferred_company_size ?? [],
    minimum_confidence_score: icp.minimum_confidence_score?.toString() ?? "",
    exclude_duplicate_companies: icp.exclude_duplicate_companies,
    search_depth: icp.search_depth,
    search_frequency: icp.search_frequency,
    target_buyer_type_ids: icp.target_buyer_types.map((t) => t.id),
    target_market_country_ids: icp.target_markets.map((t) => t.id),
    excluded_country_ids: icp.excluded_countries.map((t) => t.id),
    language_ids: icp.languages.map((t) => t.id),
  };
}

/**
 * CompanyICP — M8.7 Phase E3 (Settings zone). Migrated in place per Design
 * Bible Section 9.2: identical fetch/save-in-place/save-as-new calls, only
 * the markup moves onto design-system tokens/primitives.
 */
export default function CompanyICP() {
  const { companyId } = useParams();
  const [versions, setVersions] = useState<ICPCriteria[]>([]);
  const [buyerTypes, setBuyerTypes] = useState<MultiSelectOption[]>([]);
  const [countries, setCountries] = useState<MultiSelectOption[]>([]);
  const [languages, setLanguages] = useState<MultiSelectOption[]>([]);
  const [form, setForm] = useState<ICPForm>(EMPTY_FORM);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState(false);
  const savedMessageTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const latest = versions[0] ?? null;

  // Shared fetch, used by both the initial mount (full-page loading screen)
  // and the post-save refresh (silent - the form stays mounted, no loading
  // screen, no scroll jump). `showLoadingScreen` is the only thing that
  // differs between the two call sites.
  const fetchData = (showLoadingScreen: boolean) => {
    if (showLoadingScreen) setIsLoading(true);
    return Promise.all([
      apiClient.get(`/company-profiles/${companyId}/icp-criteria`),
      apiClient.get("/buyer-types"),
      apiClient.get("/countries"),
      apiClient.get("/languages"),
    ]).then(([icpRes, buyerRes, countryRes, langRes]) => {
      const sorted: ICPCriteria[] = icpRes.data;
      setVersions(sorted);
      setForm(sorted.length > 0 ? toForm(sorted[0]) : EMPTY_FORM);
      setBuyerTypes(buyerRes.data.map((b: { id: string; name: string }) => ({ id: b.id, label: b.name })));
      setCountries(countryRes.data.map((c: { id: string; name: string }) => ({ id: c.id, label: c.name })));
      setLanguages(langRes.data.map((l: { id: string; name: string }) => ({ id: l.id, label: l.name })));
      if (showLoadingScreen) setIsLoading(false);
    });
  };

  const load = () => {
    void fetchData(true);
  };
  const refreshAfterSave = () => fetchData(false);

  useEffect(load, [companyId]);

  // Clear any pending "Changes saved" auto-hide timer on unmount.
  useEffect(() => {
    return () => {
      if (savedMessageTimeout.current) clearTimeout(savedMessageTimeout.current);
    };
  }, []);

  const showSavedMessage = () => {
    setSavedMessage(true);
    if (savedMessageTimeout.current) clearTimeout(savedMessageTimeout.current);
    savedMessageTimeout.current = setTimeout(() => setSavedMessage(false), 3000);
  };

  const update = <K extends keyof ICPForm>(key: K, value: ICPForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const buildPayload = () => ({
    name: form.name,
    weight: form.weight,
    is_active: form.is_active,
    preferred_company_size: form.preferred_company_size,
    minimum_confidence_score: form.minimum_confidence_score === "" ? null : Number(form.minimum_confidence_score),
    exclude_duplicate_companies: form.exclude_duplicate_companies,
    search_depth: form.search_depth,
    search_frequency: form.search_frequency,
    rules: {},
    target_buyer_type_ids: form.target_buyer_type_ids,
    target_market_country_ids: form.target_market_country_ids,
    excluded_country_ids: form.excluded_country_ids,
    language_ids: form.language_ids,
  });

  const handleSaveInPlace = async (e: FormEvent) => {
    e.preventDefault();
    if (!latest) return handleSaveAsNew(e);
    setIsSaving(true);
    setError(null);
    setSavedMessage(false);
    try {
      await apiClient.put(`/company-profiles/${companyId}/icp-criteria/${latest.id}`, buildPayload());
      await refreshAfterSave();
      showSavedMessage();
    } catch {
      setError("Could not save this ICP.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveAsNew = async (e: FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setError(null);
    setSavedMessage(false);
    try {
      await apiClient.post(`/company-profiles/${companyId}/icp-criteria`, buildPayload());
      await refreshAfterSave();
      showSavedMessage();
    } catch {
      setError("Could not save this ICP.");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>;

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Ideal Customer Profile</h1>
      <p className="mb-6 text-body text-slate-400">
        This tells the Discovery Engine who to look for, alongside your products. Every save creates a new
        version — nothing is lost, and you can always look back at how your criteria evolved.
      </p>

      {error && <p className="mb-4 text-sm text-status-danger">{error}</p>}

      <form onSubmit={handleSaveInPlace}>
        <FormSection title={latest ? `Editing version ${latest.version}` : "First version"}>
          <Field label="Name">
            <Input required value={form.name} onChange={(e) => update("name", e.target.value)} />
          </Field>
          <Field label="Weight">
            <Input type="number" step="0.1" value={form.weight} onChange={(e) => update("weight", Number(e.target.value))} />
          </Field>
          <Field label="Minimum confidence score">
            <Input
              type="number"
              step="0.01"
              value={form.minimum_confidence_score}
              onChange={(e) => update("minimum_confidence_score", e.target.value)}
              placeholder="e.g. 0.7"
            />
          </Field>
          <Field label="Search depth">
            <Select value={form.search_depth} onChange={(e) => update("search_depth", e.target.value as SearchDepth)}>
              <option value="quick">Quick</option>
              <option value="standard">Standard</option>
              <option value="deep">Deep</option>
            </Select>
          </Field>
          <Field label="Search frequency">
            <Select value={form.search_frequency} onChange={(e) => update("search_frequency", e.target.value as SearchFrequency)}>
              <option value="manual">Manual</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
            </Select>
          </Field>
          <Field label="Active">
            <Toggle checked={form.is_active} onChange={(v) => update("is_active", v)} />
          </Field>
          <Field label="Exclude duplicate companies">
            <Toggle checked={form.exclude_duplicate_companies} onChange={(v) => update("exclude_duplicate_companies", v)} />
          </Field>
          <Field label="Preferred company size" full>
            <TagInput
              value={form.preferred_company_size}
              onChange={(v) => update("preferred_company_size", v)}
              placeholder="e.g. 11-50, 51-200"
            />
          </Field>
        </FormSection>

        <FormSection title="Target Buyer Types">
          <Field label="Buyer types" full>
            <MultiSelect options={buyerTypes} selected={form.target_buyer_type_ids} onChange={(v) => update("target_buyer_type_ids", v)} />
          </Field>
        </FormSection>

        <FormSection title="Target Markets">
          <Field label="Target countries" full>
            <MultiSelect options={countries} selected={form.target_market_country_ids} onChange={(v) => update("target_market_country_ids", v)} />
          </Field>
          <Field label="Excluded countries" full>
            <MultiSelect options={countries} selected={form.excluded_country_ids} onChange={(v) => update("excluded_country_ids", v)} />
          </Field>
          <Field label="Preferred languages" full>
            <MultiSelect options={languages} selected={form.language_ids} onChange={(v) => update("language_ids", v)} />
          </Field>
        </FormSection>

        <div className="flex items-center justify-end gap-3">
          {savedMessage && <span className="text-sm font-medium text-status-success">Changes saved</span>}
          <Button type="button" variant="secondary" onClick={handleSaveAsNew} disabled={isSaving}>
            Save as new version
          </Button>
          <Button type="submit" isLoading={isSaving}>
            {latest ? "Save changes" : "Create ICP"}
          </Button>
        </div>
      </form>

      {versions.length > 1 && (
        <div className="mt-8">
          <h3 className="mb-2 text-sm font-semibold text-slate-300">Version history</h3>
          <div className="space-y-2">
            {versions.map((v) => (
              <div key={v.id} className="rounded-lg border border-border-hairline bg-surface-1 px-4 py-2 text-sm text-slate-300">
                v{v.version} — {v.name} {v.is_active ? "(active)" : ""}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
