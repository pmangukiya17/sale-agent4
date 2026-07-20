import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { FormSection, Field, inputClass } from "../components/FormSection";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { Card, Badge, Button, Input } from "../design-system";
import type { BadgeTone } from "../design-system";

interface OutreachBlock {
  id: string;
  block_key: string;
  behavior: "fixed" | "ai_assisted" | "ai_generated";
  fixed_content: string | null;
  ai_guidance: string | null;
  applicable_channels: string[] | null;
  is_mandatory: boolean;
  display_order: number;
}

interface OutreachPlaybook {
  id: string;
  company_profile_id: string | null;
  name: string;
  description: string | null;
  playbook_goal: string | null;
  version: number;
  is_current: boolean;
  derived_from_playbook_version: number | null;
  is_system_default: boolean;
  sales_methodology: string | null;
  brand_voice: string | null;
  core_value_proposition: string | null;
  communication_principles: string[] | null;
  cta_strategy: string | null;
  blocks: OutreachBlock[];
}

interface RevisionForm {
  name: string;
  description: string;
  playbook_goal: string;
  sales_methodology: string;
  brand_voice: string;
  core_value_proposition: string;
  cta_strategy: string;
  blocks: OutreachBlock[];
}

const BEHAVIOR_TONES: Record<string, BadgeTone> = {
  fixed: "neutral",
  ai_assisted: "info",
  ai_generated: "ai",
};

/**
 * OutreachPlaybooks — M8.7 Phase E2 (AI Workforce zone). Migrated in place
 * per Design Bible Section 9.2: identical fetch/clone/revise calls, only
 * the markup moves onto design-system tokens/primitives.
 */
export default function OutreachPlaybooks() {
  const { companyId } = useParams();
  const [playbooks, setPlaybooks] = useState<OutreachPlaybook[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [revisingId, setRevisingId] = useState<string | null>(null);
  const [form, setForm] = useState<RevisionForm | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setIsLoading(true);
    apiClient
      .get(`/company-profiles/${companyId}/outreach-playbooks`)
      .then((res) => setPlaybooks(res.data))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [companyId]);

  const clonePlaybook = async (playbook: OutreachPlaybook) => {
    setError(null);
    try {
      await apiClient.post(`/company-profiles/${companyId}/outreach-playbooks/${playbook.id}/clone`);
      load();
    } catch {
      setError("Could not clone this playbook.");
    }
  };

  const startRevise = (playbook: OutreachPlaybook) => {
    setRevisingId(playbook.id);
    setForm({
      name: playbook.name,
      description: playbook.description ?? "",
      playbook_goal: playbook.playbook_goal ?? "",
      sales_methodology: playbook.sales_methodology ?? "",
      brand_voice: playbook.brand_voice ?? "",
      core_value_proposition: playbook.core_value_proposition ?? "",
      cta_strategy: playbook.cta_strategy ?? "",
      blocks: playbook.blocks.map((b) => ({ ...b })),
    });
  };

  const updateBlockContent = (blockId: string, value: string) => {
    setForm((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        blocks: prev.blocks.map((b) =>
          b.id === blockId ? { ...b, [b.behavior === "fixed" ? "fixed_content" : "ai_guidance"]: value } : b
        ),
      };
    });
  };

  const submitRevision = async (e: FormEvent) => {
    e.preventDefault();
    if (!form || !revisingId) return;
    setError(null);
    try {
      await apiClient.post(`/company-profiles/${companyId}/outreach-playbooks/${revisingId}/revise`, {
        name: form.name,
        description: form.description || null,
        playbook_goal: form.playbook_goal || null,
        sales_methodology: form.sales_methodology || null,
        brand_voice: form.brand_voice || null,
        core_value_proposition: form.core_value_proposition || null,
        cta_strategy: form.cta_strategy || null,
        blocks: form.blocks.map((b) => ({
          block_key: b.block_key,
          behavior: b.behavior,
          fixed_content: b.fixed_content,
          ai_guidance: b.ai_guidance,
          applicable_channels: b.applicable_channels,
          is_mandatory: b.is_mandatory,
          display_order: b.display_order,
        })),
      });
      setRevisingId(null);
      setForm(null);
      load();
    } catch {
      setError("Could not save this new playbook version.");
    }
  };

  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Businesses", to: "/businesses" }, { label: "Outreach Playbooks" }]} />

      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Outreach Playbooks</h1>
      <p className="mb-6 text-body text-slate-400">
        How this business sells: methodology, brand voice, value proposition, and reusable blocks. Never edited in
        place - "Revise" creates a new version and keeps the old one intact for comparison/audit.
      </p>

      {error && <p className="mb-4 text-sm text-status-danger">{error}</p>}

      <div className="space-y-3">
        {playbooks.map((playbook) => {
          const isOpen = expandedId === playbook.id;
          const isRevising = revisingId === playbook.id;
          return (
            <Card key={playbook.id}>
              <button className="flex w-full items-start justify-between text-left" onClick={() => setExpandedId(isOpen ? null : playbook.id)}>
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <h3 className="font-semibold text-slate-100">{playbook.name}</h3>
                    <Badge tone="neutral">v{playbook.version}</Badge>
                    {playbook.is_system_default && <Badge tone="info">system default</Badge>}
                    {playbook.playbook_goal && <Badge tone="neutral">{playbook.playbook_goal.replace(/_/g, " ")}</Badge>}
                  </div>
                  {playbook.description && <p className="text-xs text-slate-500">{playbook.description}</p>}
                </div>
              </button>

              {isOpen && !isRevising && (
                <div className="mt-4 space-y-4 border-t border-border-hairline pt-4">
                  {playbook.sales_methodology && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-slate-500">Sales methodology</p>
                      <p className="text-sm text-slate-300">{playbook.sales_methodology}</p>
                    </div>
                  )}
                  {playbook.core_value_proposition && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-slate-500">Core value proposition</p>
                      <p className="text-sm text-slate-300">{playbook.core_value_proposition}</p>
                    </div>
                  )}
                  <div>
                    <p className="mb-2 text-xs font-medium text-slate-500">Blocks (in render order)</p>
                    <div className="space-y-2">
                      {[...playbook.blocks].sort((a, b) => a.display_order - b.display_order).map((block) => (
                        <div key={block.id} className="rounded-lg bg-surface-2 p-2 text-xs">
                          <div className="mb-1 flex items-center gap-2">
                            <span className="font-medium text-slate-200">{block.block_key}</span>
                            <Badge tone={BEHAVIOR_TONES[block.behavior]}>{block.behavior.replace(/_/g, " ")}</Badge>
                            {block.is_mandatory && <span className="text-slate-500">mandatory</span>}
                          </div>
                          <p className="text-slate-400">{block.fixed_content || block.ai_guidance}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    {playbook.is_system_default ? (
                      <Button size="sm" variant="secondary" onClick={() => clonePlaybook(playbook)}>
                        Clone into my business
                      </Button>
                    ) : (
                      <Button size="sm" variant="secondary" onClick={() => startRevise(playbook)}>
                        Revise (creates v{playbook.version + 1})
                      </Button>
                    )}
                  </div>
                </div>
              )}

              {isRevising && form && (
                <form onSubmit={submitRevision} className="mt-4 border-t border-border-hairline pt-4">
                  <FormSection title={`Revise "${playbook.name}"`}>
                    <Field label="Name" full>
                      <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                    </Field>
                    <Field label="Playbook goal">
                      <Input value={form.playbook_goal} onChange={(e) => setForm({ ...form, playbook_goal: e.target.value })} />
                    </Field>
                    <Field label="Description" full>
                      <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
                    </Field>
                    <Field label="Sales methodology" full>
                      <textarea className={inputClass} rows={3} value={form.sales_methodology} onChange={(e) => setForm({ ...form, sales_methodology: e.target.value })} />
                    </Field>
                    <Field label="Brand voice" full>
                      <textarea className={inputClass} rows={2} value={form.brand_voice} onChange={(e) => setForm({ ...form, brand_voice: e.target.value })} />
                    </Field>
                    <Field label="Core value proposition" full>
                      <textarea className={inputClass} rows={2} value={form.core_value_proposition} onChange={(e) => setForm({ ...form, core_value_proposition: e.target.value })} />
                    </Field>
                    <Field label="CTA strategy" full>
                      <textarea className={inputClass} rows={2} value={form.cta_strategy} onChange={(e) => setForm({ ...form, cta_strategy: e.target.value })} />
                    </Field>
                  </FormSection>

                  <div className="mb-4">
                    <p className="mb-2 text-sm font-medium text-slate-200">Blocks</p>
                    <div className="space-y-2">
                      {form.blocks.map((block) => (
                        <div key={block.id}>
                          <div className="mb-1 flex items-center gap-2 text-xs">
                            <span className="font-medium text-slate-200">{block.block_key}</span>
                            <Badge tone={BEHAVIOR_TONES[block.behavior]}>{block.behavior.replace(/_/g, " ")}</Badge>
                          </div>
                          <textarea
                            className={inputClass}
                            rows={2}
                            value={(block.behavior === "fixed" ? block.fixed_content : block.ai_guidance) ?? ""}
                            onChange={(e) => updateBlockContent(block.id, e.target.value)}
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="flex justify-end gap-3">
                    <Button type="button" variant="secondary" onClick={() => { setRevisingId(null); setForm(null); }}>
                      Cancel
                    </Button>
                    <Button type="submit">Save new version</Button>
                  </div>
                </form>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
