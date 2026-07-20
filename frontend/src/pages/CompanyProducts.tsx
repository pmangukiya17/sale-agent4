import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { FormSection, Field, inputClass } from "../components/FormSection";
import { TagInput } from "../components/TagInput";
import { Card, Badge, Button, Input, Select, PlaceholderNotice } from "../design-system";

interface Product {
  id: string;
  name: string;
  category: string | null;
  description: string | null;
  keywords: string[] | null;
  hs_code: string | null;
  status: "active" | "inactive";
  applications: string[] | null;
  specifications: Record<string, string> | null;
  packaging: string | null;
  moq: string | null;
  lead_time: string | null;
  production_capacity: string | null;
}

interface ProductForm {
  name: string;
  category: string;
  description: string;
  keywords: string[];
  hs_code: string;
  status: "active" | "inactive";
  applications: string[];
  specEntries: { key: string; value: string }[];
  packaging: string;
  moq: string;
  lead_time: string;
  production_capacity: string;
}

const EMPTY_FORM: ProductForm = {
  name: "",
  category: "",
  description: "",
  keywords: [],
  hs_code: "",
  status: "active",
  applications: [],
  specEntries: [],
  packaging: "",
  moq: "",
  lead_time: "",
  production_capacity: "",
};

function productToForm(p: Product): ProductForm {
  return {
    name: p.name,
    category: p.category ?? "",
    description: p.description ?? "",
    keywords: p.keywords ?? [],
    hs_code: p.hs_code ?? "",
    status: p.status,
    applications: p.applications ?? [],
    specEntries: Object.entries(p.specifications ?? {}).map(([key, value]) => ({ key, value: String(value) })),
    packaging: p.packaging ?? "",
    moq: p.moq ?? "",
    lead_time: p.lead_time ?? "",
    production_capacity: p.production_capacity ?? "",
  };
}

/**
 * CompanyProducts — M8.7 Phase E1 (CRM zone). Migrated in place per Design
 * Bible Section 9.2: identical fetch/create/update/delete calls, only the
 * markup moves onto design-system primitives. FormSection/Field/TagInput
 * (shared components, not page-local) were restyled to permanent dark
 * tokens as part of this pass since both are used here - see their own
 * docstrings.
 */
export default function CompanyProducts() {
  const { companyId } = useParams();
  const [products, setProducts] = useState<Product[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<ProductForm>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setIsLoading(true);
    apiClient
      .get(`/company-profiles/${companyId}/products`)
      .then((res) => setProducts(res.data))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [companyId]);

  const update = <K extends keyof ProductForm>(key: K, value: ProductForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const startCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
  };

  const startEdit = (p: Product) => {
    setEditingId(p.id);
    setForm(productToForm(p));
    setShowForm(true);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const specifications = Object.fromEntries(
      form.specEntries.filter((entry) => entry.key.trim() !== "").map((entry) => [entry.key.trim(), entry.value])
    );
    const payload = {
      name: form.name,
      category: form.category || null,
      description: form.description || null,
      keywords: form.keywords,
      hs_code: form.hs_code || null,
      status: form.status,
      applications: form.applications,
      specifications,
      packaging: form.packaging || null,
      moq: form.moq || null,
      lead_time: form.lead_time || null,
      production_capacity: form.production_capacity || null,
    };
    try {
      if (editingId) {
        await apiClient.put(`/company-profiles/${companyId}/products/${editingId}`, payload);
      } else {
        await apiClient.post(`/company-profiles/${companyId}/products`, payload);
      }
      setShowForm(false);
      load();
    } catch {
      setError("Could not save this product.");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this product?")) return;
    await apiClient.delete(`/company-profiles/${companyId}/products/${id}`);
    load();
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-h1 font-semibold text-slate-100">Products</h1>
        <Button onClick={startCreate}>+ Add product</Button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="mb-6">
          <FormSection title={editingId ? "Edit product" : "New product"}>
            <Field label="Name">
              <Input required value={form.name} onChange={(e) => update("name", e.target.value)} />
            </Field>
            <Field label="Category">
              <Input value={form.category} onChange={(e) => update("category", e.target.value)} />
            </Field>
            <Field label="HS Code">
              <Input value={form.hs_code} onChange={(e) => update("hs_code", e.target.value)} />
            </Field>
            <Field label="Status">
              <Select value={form.status} onChange={(e) => update("status", e.target.value as "active" | "inactive")}>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </Select>
            </Field>
            <Field label="Description" full>
              <textarea className={inputClass} rows={3} value={form.description} onChange={(e) => update("description", e.target.value)} />
            </Field>
            <Field label="Keywords" full>
              <TagInput value={form.keywords} onChange={(v) => update("keywords", v)} placeholder="Add a keyword and press Enter" />
            </Field>
            <Field label="Applications" full>
              <TagInput value={form.applications} onChange={(v) => update("applications", v)} placeholder="e.g. Bedding, Upholstery" />
            </Field>
            <Field label="Packaging">
              <Input value={form.packaging} onChange={(e) => update("packaging", e.target.value)} />
            </Field>
            <Field label="MOQ">
              <Input value={form.moq} onChange={(e) => update("moq", e.target.value)} />
            </Field>
            <Field label="Lead time">
              <Input value={form.lead_time} onChange={(e) => update("lead_time", e.target.value)} />
            </Field>
            <Field label="Production capacity">
              <Input value={form.production_capacity} onChange={(e) => update("production_capacity", e.target.value)} />
            </Field>
            <Field label="Specifications" full>
              <div className="space-y-2">
                {form.specEntries.map((entry, idx) => (
                  <div key={idx} className="flex gap-2">
                    <Input
                      placeholder="Attribute (e.g. GSM)"
                      value={entry.key}
                      onChange={(e) => {
                        const next = [...form.specEntries];
                        next[idx] = { ...next[idx], key: e.target.value };
                        update("specEntries", next);
                      }}
                    />
                    <Input
                      placeholder="Value (e.g. 300)"
                      value={entry.value}
                      onChange={(e) => {
                        const next = [...form.specEntries];
                        next[idx] = { ...next[idx], value: e.target.value };
                        update("specEntries", next);
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => update("specEntries", form.specEntries.filter((_, i) => i !== idx))}
                      className="px-2 text-slate-500 hover:text-slate-200"
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => update("specEntries", [...form.specEntries, { key: "", value: "" }])}
                  className="text-xs font-medium text-slate-400 underline hover:text-slate-200"
                >
                  + Add specification
                </button>
              </div>
            </Field>
          </FormSection>

          {error && <p className="mb-4 text-sm text-status-danger">{error}</p>}

          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
            <Button type="submit">Save product</Button>
          </div>
        </form>
      )}

      {!isLoading && products.length === 0 && !showForm && (
        <PlaceholderNotice kind="no-data" reason="No products yet. Add your first one so the AI knows what this business sells." />
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {isLoading &&
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="h-32 animate-pulse">
              {null}
            </Card>
          ))}

        {products.map((p) => (
          <Card key={p.id}>
            <div className="mb-2 flex items-start justify-between">
              <h3 className="font-semibold text-slate-100">{p.name}</h3>
              <Badge tone={p.status === "active" ? "success" : "neutral"}>{p.status}</Badge>
            </div>
            {p.category && <p className="mb-1 text-xs text-slate-500">{p.category}</p>}
            {p.description && <p className="mb-3 text-sm text-slate-300">{p.description}</p>}
            <div className="flex gap-2 text-sm">
              <button
                onClick={() => startEdit(p)}
                className="rounded-lg border border-border-hairline px-3 py-1.5 text-slate-200 hover:border-border-hairline-strong hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
              >
                Edit
              </button>
              <button
                onClick={() => handleDelete(p.id)}
                className="rounded-lg border border-border-hairline px-3 py-1.5 text-status-danger hover:bg-status-danger/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
              >
                Delete
              </button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
