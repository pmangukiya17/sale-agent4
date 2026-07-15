import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { FormSection, Field, inputClass } from "../components/FormSection";
import { TagInput } from "../components/TagInput";

interface KnowledgeBaseEntry {
  id: string;
  title: string;
  content: string;
  tags: string[] | null;
  category: string | null;
}

interface EntryForm {
  title: string;
  content: string;
  tags: string[];
  category: string;
}

const EMPTY_FORM: EntryForm = { title: "", content: "", tags: [], category: "" };

export default function CompanyKnowledgeBase() {
  const { companyId } = useParams();
  const [entries, setEntries] = useState<KnowledgeBaseEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<EntryForm>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setIsLoading(true);
    apiClient
      .get(`/company-profiles/${companyId}/knowledge-base`)
      .then((res) => setEntries(res.data))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [companyId]);

  const update = <K extends keyof EntryForm>(key: K, value: EntryForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const startCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
  };

  const startEdit = (entry: KnowledgeBaseEntry) => {
    setEditingId(entry.id);
    setForm({
      title: entry.title,
      content: entry.content,
      tags: entry.tags ?? [],
      category: entry.category ?? "",
    });
    setShowForm(true);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const payload = {
      title: form.title,
      content: form.content,
      tags: form.tags,
      category: form.category || null,
    };
    try {
      if (editingId) {
        await apiClient.put(`/company-profiles/${companyId}/knowledge-base/${editingId}`, payload);
      } else {
        await apiClient.post(`/company-profiles/${companyId}/knowledge-base`, payload);
      }
      setShowForm(false);
      load();
    } catch {
      setError("Could not save this entry.");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this knowledge base entry?")) return;
    await apiClient.delete(`/company-profiles/${companyId}/knowledge-base/${id}`);
    load();
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">Knowledge Base</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Long-term memory every AI agent can draw on for this business — policies, FAQs, past decisions.
          </p>
        </div>
        <button
          onClick={startCreate}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:bg-indigo-600 dark:hover:bg-indigo-500"
        >
          + Add entry
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="mb-6">
          <FormSection title={editingId ? "Edit entry" : "New entry"}>
            <Field label="Title" full>
              <input required className={inputClass} value={form.title} onChange={(e) => update("title", e.target.value)} />
            </Field>
            <Field label="Category">
              <input className={inputClass} value={form.category} onChange={(e) => update("category", e.target.value)} />
            </Field>
            <Field label="Tags">
              <TagInput value={form.tags} onChange={(v) => update("tags", v)} placeholder="Add a tag and press Enter" />
            </Field>
            <Field label="Content" full>
              <textarea required className={inputClass} rows={6} value={form.content} onChange={(e) => update("content", e.target.value)} />
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
              Save entry
            </button>
          </div>
        </form>
      )}

      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}

      {!isLoading && entries.length === 0 && !showForm && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900">
          No knowledge base entries yet.
        </div>
      )}

      <div className="space-y-3">
        {entries.map((entry) => (
          <div key={entry.id} className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
            <div className="mb-2 flex items-start justify-between">
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-slate-100">{entry.title}</h3>
                {entry.category && <p className="text-xs text-slate-500">{entry.category}</p>}
              </div>
              <div className="flex gap-2 text-sm">
                <button onClick={() => startEdit(entry)} className="text-slate-600 hover:underline dark:text-slate-300">
                  Edit
                </button>
                <button onClick={() => handleDelete(entry.id)} className="text-red-600 hover:underline">
                  Delete
                </button>
              </div>
            </div>
            <p className="whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-300">{entry.content}</p>
            {entry.tags && entry.tags.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {entry.tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-700 dark:text-slate-300"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
