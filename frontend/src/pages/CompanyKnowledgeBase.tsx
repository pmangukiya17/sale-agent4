import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { FormSection, Field, inputClass } from "../components/FormSection";
import { TagInput } from "../components/TagInput";
import { Card, Button, Input, PlaceholderNotice, ConfirmDialog } from "../design-system";
import { useDeleteResource } from "../hooks/useDeleteResource";

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

/**
 * CompanyKnowledgeBase — M8.7 Phase E3 (Settings zone). Migrated in place
 * per Design Bible Section 9.2: identical fetch/create/update/delete
 * calls, only the markup moves onto design-system tokens/primitives.
 */
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

  // M8.17: shared Global Delete System pattern - see hooks/useDeleteResource.ts.
  const del = useDeleteResource({
    entityLabel: "Knowledge base entry",
    buildUrl: (id) => `/company-profiles/${companyId}/knowledge-base/${id}`,
    onDeleted: load,
  });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-h1 font-semibold text-slate-100">Knowledge Base</h1>
          <p className="text-body text-slate-400">
            Long-term memory every AI agent can draw on for this business — policies, FAQs, past decisions.
          </p>
        </div>
        <Button onClick={startCreate}>+ Add entry</Button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="mb-6">
          <FormSection title={editingId ? "Edit entry" : "New entry"}>
            <Field label="Title" full>
              <Input required value={form.title} onChange={(e) => update("title", e.target.value)} />
            </Field>
            <Field label="Category">
              <Input value={form.category} onChange={(e) => update("category", e.target.value)} />
            </Field>
            <Field label="Tags">
              <TagInput value={form.tags} onChange={(v) => update("tags", v)} placeholder="Add a tag and press Enter" />
            </Field>
            <Field label="Content" full>
              <textarea required className={inputClass} rows={6} value={form.content} onChange={(e) => update("content", e.target.value)} />
            </Field>
          </FormSection>

          {error && <p className="mb-4 text-sm text-status-danger">{error}</p>}

          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
            <Button type="submit">Save entry</Button>
          </div>
        </form>
      )}

      {!isLoading && entries.length === 0 && !showForm && (
        <PlaceholderNotice kind="no-data" reason="No knowledge base entries yet." />
      )}

      <div className="space-y-3">
        {isLoading &&
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="h-24 animate-pulse">
              {null}
            </Card>
          ))}

        {entries.map((entry) => (
          <Card key={entry.id}>
            <div className="mb-2 flex items-start justify-between">
              <div>
                <h3 className="font-semibold text-slate-100">{entry.title}</h3>
                {entry.category && <p className="text-xs text-slate-500">{entry.category}</p>}
              </div>
              <div className="flex gap-2 text-sm">
                <button onClick={() => startEdit(entry)} className="text-slate-300 hover:underline">
                  Edit
                </button>
                <button onClick={() => del.requestDelete(entry.id)} className="text-status-danger hover:underline">
                  Delete
                </button>
              </div>
            </div>
            <p className="whitespace-pre-wrap text-sm text-slate-300">{entry.content}</p>
            {entry.tags && entry.tags.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {entry.tags.map((tag) => (
                  <span key={tag} className="rounded-pill bg-surface-2 px-2 py-0.5 text-xs text-slate-300">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>

      <ConfirmDialog
        open={del.pendingId !== null}
        title="Delete knowledge base entry?"
        message="This can't be undone. AI agents drawing on this business's knowledge base will no longer see this entry."
        isLoading={del.isDeleting}
        onConfirm={del.confirmDelete}
        onCancel={del.cancel}
      />
    </div>
  );
}
