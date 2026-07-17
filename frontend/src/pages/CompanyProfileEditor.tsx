import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { useCompanies } from "../companies/CompanyContext";
import { FormSection, Field, inputClass } from "../components/FormSection";
import { TagInput } from "../components/TagInput";
import { MultiSelect, type MultiSelectOption } from "../components/MultiSelect";
import { Toggle } from "../components/Toggle";
import { Breadcrumbs } from "../components/Breadcrumbs";

const BUSINESS_TYPE_OPTIONS = ["manufacturer", "trading_company", "exporter"];

interface CompanyProfileForm {
  name: string;
  logo_url: string;
  website: string;
  email: string;
  phone: string;
  country: string;
  address: string;
  about: string;
  description: string;
  business_type: string[];
  production_capacity: string;
  factory_location: string;
  shipping_ports: string[];
  export_certifications: string[];
  minimum_order_quantity: string;
  preferred_incoterms: string[];
  preferred_payment_terms: string[];
  timezone: string;
  ai_instructions: string;
  is_default: boolean;
  industry_ids: string[];
}

const EMPTY_FORM: CompanyProfileForm = {
  name: "",
  logo_url: "",
  website: "",
  email: "",
  phone: "",
  country: "",
  address: "",
  about: "",
  description: "",
  business_type: [],
  production_capacity: "",
  factory_location: "",
  shipping_ports: [],
  export_certifications: [],
  minimum_order_quantity: "",
  preferred_incoterms: [],
  preferred_payment_terms: [],
  timezone: "",
  ai_instructions: "",
  is_default: false,
  industry_ids: [],
};

export default function CompanyProfileEditor() {
  const { companyId } = useParams();
  const isEditing = Boolean(companyId);
  const navigate = useNavigate();
  const { refresh } = useCompanies();

  const [form, setForm] = useState<CompanyProfileForm>(EMPTY_FORM);
  const [industries, setIndustries] = useState<MultiSelectOption[]>([]);
  const [isLoading, setIsLoading] = useState(isEditing);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .get("/industries")
      .then((res) =>
        setIndustries(res.data.map((i: { id: string; name: string }) => ({ id: i.id, label: i.name })))
      )
      .catch(() => setIndustries([]));
  }, []);

  useEffect(() => {
    if (!isEditing) return;
    apiClient
      .get(`/company-profiles/${companyId}`)
      .then((res) => {
        const data = res.data;
        setForm({
          name: data.name ?? "",
          logo_url: data.logo_url ?? "",
          website: data.website ?? "",
          email: data.email ?? "",
          phone: data.phone ?? "",
          country: data.country ?? "",
          address: data.address ?? "",
          about: data.about ?? "",
          description: data.description ?? "",
          business_type: data.business_type ?? [],
          production_capacity: data.production_capacity ?? "",
          factory_location: data.factory_location ?? "",
          shipping_ports: data.shipping_ports ?? [],
          export_certifications: data.export_certifications ?? [],
          minimum_order_quantity: data.minimum_order_quantity ?? "",
          preferred_incoterms: data.preferred_incoterms ?? [],
          preferred_payment_terms: data.preferred_payment_terms ?? [],
          timezone: data.timezone ?? "",
          ai_instructions: data.ai_instructions ?? "",
          is_default: data.is_default ?? false,
          industry_ids: (data.industries ?? []).map((i: { id: string }) => i.id),
        });
      })
      .catch(() => setError("Could not load this business."))
      .finally(() => setIsLoading(false));
  }, [companyId, isEditing]);

  const update = <K extends keyof CompanyProfileForm>(key: K, value: CompanyProfileForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setError(null);

    const payload = {
      ...form,
      logo_url: form.logo_url || null,
      website: form.website || null,
      email: form.email || null,
      phone: form.phone || null,
      country: form.country || null,
      address: form.address || null,
      about: form.about || null,
      description: form.description || null,
      production_capacity: form.production_capacity || null,
      factory_location: form.factory_location || null,
      minimum_order_quantity: form.minimum_order_quantity || null,
      timezone: form.timezone || null,
      ai_instructions: form.ai_instructions || null,
    };

    try {
      if (isEditing) {
        await apiClient.put(`/company-profiles/${companyId}`, payload);
      } else {
        await apiClient.post("/company-profiles", payload);
      }
      await refresh();
      navigate("/businesses");
    } catch {
      setError("Could not save this business. Check the form and try again.");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return <p className="text-sm text-slate-500">Loading…</p>;
  }

  return (
    <div className="mx-auto max-w-4xl">
      <Breadcrumbs items={[{ label: "Businesses", to: "/businesses" }, { label: "Business Settings" }]} />

      <h2 className="mb-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">
        {isEditing ? "Edit business" : "Add a business"}
      </h2>
      <p className="mb-6 text-sm text-slate-500 dark:text-slate-400">
        This is what every AI agent will read before doing anything on this business's behalf.
      </p>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      <form onSubmit={handleSubmit}>
        <FormSection title="Basic Info">
          <Field label="Company name" full>
            <input
              required
              className={inputClass}
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
            />
          </Field>
          <Field label="Logo URL">
            <input className={inputClass} value={form.logo_url} onChange={(e) => update("logo_url", e.target.value)} />
          </Field>
          <Field label="Website">
            <input className={inputClass} value={form.website} onChange={(e) => update("website", e.target.value)} />
          </Field>
          <Field label="Email">
            <input className={inputClass} value={form.email} onChange={(e) => update("email", e.target.value)} />
          </Field>
          <Field label="Phone">
            <input className={inputClass} value={form.phone} onChange={(e) => update("phone", e.target.value)} />
          </Field>
          <Field label="Country">
            <input className={inputClass} value={form.country} onChange={(e) => update("country", e.target.value)} />
          </Field>
          <Field label="Timezone (IANA, e.g. Europe/Berlin)">
            <input className={inputClass} value={form.timezone} onChange={(e) => update("timezone", e.target.value)} />
          </Field>
          <Field label="Address" full>
            <textarea
              className={inputClass}
              rows={2}
              value={form.address}
              onChange={(e) => update("address", e.target.value)}
            />
          </Field>
          <Field label="Set as default business">
            <Toggle checked={form.is_default} onChange={(v) => update("is_default", v)} />
          </Field>
        </FormSection>

        <FormSection title="About">
          <Field label="About the company" full>
            <textarea className={inputClass} rows={3} value={form.about} onChange={(e) => update("about", e.target.value)} />
          </Field>
          <Field label="Company description" full>
            <textarea
              className={inputClass}
              rows={3}
              value={form.description}
              onChange={(e) => update("description", e.target.value)}
            />
          </Field>
          <Field label="Industries" full>
            <MultiSelect
              options={industries}
              selected={form.industry_ids}
              onChange={(ids) => update("industry_ids", ids)}
            />
          </Field>
        </FormSection>

        <FormSection title="Business Details">
          <Field label="Business type" full>
            <div className="flex flex-wrap gap-3">
              {BUSINESS_TYPE_OPTIONS.map((option) => (
                <label key={option} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={form.business_type.includes(option)}
                    onChange={() =>
                      update(
                        "business_type",
                        form.business_type.includes(option)
                          ? form.business_type.filter((v) => v !== option)
                          : [...form.business_type, option]
                      )
                    }
                  />
                  {option.replace("_", " ")}
                </label>
              ))}
            </div>
          </Field>
          <Field label="Production capacity">
            <input
              className={inputClass}
              value={form.production_capacity}
              onChange={(e) => update("production_capacity", e.target.value)}
              placeholder="e.g. 50,000 meters/month"
            />
          </Field>
          <Field label="Factory location">
            <input
              className={inputClass}
              value={form.factory_location}
              onChange={(e) => update("factory_location", e.target.value)}
            />
          </Field>
          <Field label="Minimum order quantity">
            <input
              className={inputClass}
              value={form.minimum_order_quantity}
              onChange={(e) => update("minimum_order_quantity", e.target.value)}
              placeholder="e.g. 1000 meters"
            />
          </Field>
          <Field label="Shipping ports" full>
            <TagInput value={form.shipping_ports} onChange={(v) => update("shipping_ports", v)} placeholder="Add a port and press Enter" />
          </Field>
          <Field label="Export certifications" full>
            <TagInput
              value={form.export_certifications}
              onChange={(v) => update("export_certifications", v)}
              placeholder="e.g. OEKO-TEX, GOTS, ISO 9001"
            />
          </Field>
          <Field label="Preferred Incoterms" full>
            <TagInput
              value={form.preferred_incoterms}
              onChange={(v) => update("preferred_incoterms", v)}
              placeholder="e.g. FOB, CIF, EXW"
            />
          </Field>
          <Field label="Preferred payment terms" full>
            <TagInput
              value={form.preferred_payment_terms}
              onChange={(v) => update("preferred_payment_terms", v)}
              placeholder="e.g. T/T, L/C"
            />
          </Field>
        </FormSection>

        <FormSection title="AI Instructions" description="Permanent instructions every AI agent reads before acting on this business's behalf.">
          <Field label="Instructions" full>
            <textarea
              className={inputClass}
              rows={5}
              value={form.ai_instructions}
              onChange={(e) => update("ai_instructions", e.target.value)}
              placeholder="e.g. Always mention our 15 years of export experience. Never quote prices directly - defer to sales team."
            />
          </Field>
        </FormSection>

        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={() => navigate("/businesses")}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isSaving}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50 dark:bg-indigo-600 dark:hover:bg-indigo-500"
          >
            {isSaving ? "Saving…" : "Save business"}
          </button>
        </div>
      </form>
    </div>
  );
}
