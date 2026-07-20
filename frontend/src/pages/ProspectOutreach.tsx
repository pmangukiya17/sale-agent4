import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import DOMPurify from "dompurify";
import { apiClient } from "../api/client";
import { inputClass } from "../components/FormSection";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { Card, Badge, Button, Select } from "../design-system";
import type { BadgeTone } from "../design-system";

interface OutreachPlaybook {
  id: string;
  name: string;
  is_system_default: boolean;
}

interface OutreachRequest {
  id: string;
  channel_key: string;
  status: string;
  outreach_playbook: OutreachPlaybook;
  created_at: string;
}

interface OutreachEvidence {
  id: string;
  block_key: string | null;
  excerpt: string | null;
  confidence_score: number | null;
}

interface OutreachEdit {
  id: string;
  edited_at: string;
  edit_reason: string | null;
}

interface RenderedBlock {
  block_key: string;
  behavior: string;
  content: string;
  reasoning: string | null;
}

// `assembled` is channel-shaped; for email it's {subject, body} plus an
// OPTIONAL third key, signature_html - the Business Email Signature frozen
// at generation time. Deliberately never concatenated into body server-side
// (see EmailChannelProvider.render) - rendered here as its own block so a
// future channel that doesn't use signature_html never has to parse it back
// out of body.
interface OutreachDraft {
  id: string;
  channel_key: string;
  version: number;
  is_current: boolean;
  ai_generated_content: { blocks: RenderedBlock[]; assembled: Record<string, string> };
  current_content: { blocks: RenderedBlock[]; assembled: Record<string, string> };
  reasoning: string | null;
  confidence: number | null;
  status: "draft" | "pending_approval" | "approved" | "rejected" | "superseded";
  evidence: OutreachEvidence[];
  edits: OutreachEdit[];
}

const STATUS_TONES: Record<string, BadgeTone> = {
  draft: "neutral",
  pending_approval: "info",
  approved: "success",
  rejected: "danger",
  superseded: "neutral",
};

const CHANNEL_OPTIONS = [{ key: "email", label: "Email" }];

/**
 * ProspectOutreach — M8.7 Phase E2 (AI Workforce zone). Migrated in place
 * per Design Bible Section 9.2: identical fetch/create/run/approve/reject/
 * edit calls, only the markup moves onto design-system tokens/primitives.
 */
export default function ProspectOutreach() {
  const { companyId, prospectId, contactId } = useParams();
  const base = `/company-profiles/${companyId}/prospects/${prospectId}/contacts/${contactId}`;

  const [playbooks, setPlaybooks] = useState<OutreachPlaybook[]>([]);
  const [requests, setRequests] = useState<OutreachRequest[]>([]);
  const [draft, setDraft] = useState<OutreachDraft | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedPlaybookId, setSelectedPlaybookId] = useState("");
  const [selectedChannel, setSelectedChannel] = useState("email");
  const [runningRequestId, setRunningRequestId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [editedBody, setEditedBody] = useState("");
  const [isEditing, setIsEditing] = useState(false);

  const loadAll = () => {
    setIsLoading(true);
    Promise.all([
      apiClient.get(`/company-profiles/${companyId}/outreach-playbooks`),
      apiClient.get(`${base}/outreach-requests`),
      apiClient.get(`${base}/outreach-drafts/current?channel_key=${selectedChannel}`).catch(() => ({ data: null })),
    ]).then(([playbooksRes, requestsRes, draftRes]) => {
      setPlaybooks(playbooksRes.data);
      if (!selectedPlaybookId && playbooksRes.data.length > 0) setSelectedPlaybookId(playbooksRes.data[0].id);
      setRequests(requestsRes.data);
      setDraft(draftRes.data);
      setIsEditing(false);
      setIsLoading(false);
    });
  };

  useEffect(loadAll, [companyId, prospectId, contactId, selectedChannel]);

  const createRequest = async () => {
    if (!selectedPlaybookId) return;
    setActionError(null);
    try {
      await apiClient.post(`${base}/outreach-requests`, {
        outreach_playbook_id: selectedPlaybookId,
        channel_key: selectedChannel,
      });
      loadAll();
    } catch {
      setActionError("Could not create an outreach request.");
    }
  };

  const runRequest = async (requestId: string) => {
    setActionError(null);
    setRunningRequestId(requestId);
    try {
      await apiClient.post(`${base}/outreach-requests/${requestId}/run`, {});
      loadAll();
    } catch {
      setActionError("This generation run failed. Check the Outreach Jobs for details.");
    } finally {
      setRunningRequestId(null);
    }
  };

  const approveDraft = async () => {
    if (!draft) return;
    setActionError(null);
    try {
      await apiClient.post(`${base}/outreach-drafts/${draft.id}/approve`, {});
      loadAll();
    } catch {
      setActionError("Could not approve this draft.");
    }
  };

  const rejectDraft = async () => {
    if (!draft) return;
    const reason = window.prompt("Reason for rejecting this draft?") ?? undefined;
    setActionError(null);
    try {
      await apiClient.post(`${base}/outreach-drafts/${draft.id}/reject`, { reason });
      loadAll();
    } catch {
      setActionError("Could not reject this draft.");
    }
  };

  const sanitizedSignature = useMemo(() => {
    const html = draft?.current_content.assembled.signature_html;
    return html ? DOMPurify.sanitize(html) : null;
  }, [draft?.current_content.assembled.signature_html]);

  const startEdit = () => {
    if (!draft) return;
    setEditedBody(draft.current_content.assembled.body ?? "");
    setIsEditing(true);
  };

  const saveEdit = async () => {
    if (!draft) return;
    setActionError(null);
    try {
      await apiClient.post(`${base}/outreach-drafts/${draft.id}/edit`, {
        new_content: { ...draft.current_content, assembled: { ...draft.current_content.assembled, body: editedBody } },
        edit_reason: "Manual edit from the Outreach page",
      });
      setIsEditing(false);
      loadAll();
    } catch {
      setActionError("Could not save this edit.");
    }
  };

  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>;

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Businesses", to: "/businesses" },
          { label: "Prospects", to: `/businesses/${companyId}/discovery/prospects` },
          { label: "Outreach" },
        ]}
      />

      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Outreach</h1>
      <p className="mb-6 text-body text-slate-400">
        Generated from this business's Outreach Playbook and this prospect's current Personalization strategy - never
        invents facts beyond what Research/Personalization already verified.
      </p>

      {actionError && <p className="mb-4 text-sm text-status-danger">{actionError}</p>}

      <Card className="mb-6">
        <p className="mb-2 text-sm font-medium text-slate-200">Generate outreach</p>
        <div className="flex flex-wrap items-center gap-2">
          <Select className="w-40" value={selectedChannel} onChange={(e) => setSelectedChannel(e.target.value)}>
            {CHANNEL_OPTIONS.map((c) => (
              <option key={c.key} value={c.key}>{c.label}</option>
            ))}
          </Select>
          <Select className="w-64" value={selectedPlaybookId} onChange={(e) => setSelectedPlaybookId(e.target.value)}>
            {playbooks.map((p) => (
              <option key={p.id} value={p.id}>{p.name}{p.is_system_default ? " (system)" : ""}</option>
            ))}
          </Select>
          <Button size="sm" onClick={createRequest}>Create request</Button>
        </div>
      </Card>

      <div className="mb-6">
        <p className="mb-2 text-sm font-medium text-slate-200">Outreach requests</p>
        <div className="space-y-2">
          {requests.length === 0 && <p className="text-sm text-slate-500">No outreach requested yet.</p>}
          {requests.map((r) => (
            <Card key={r.id} padding="compact" className="flex items-center justify-between text-sm">
              <span className="text-slate-200">{r.channel_key} · {r.outreach_playbook.name} — <span className="text-xs text-slate-500">{r.status}</span></span>
              <Button size="sm" variant="secondary" onClick={() => runRequest(r.id)} isLoading={runningRequestId === r.id}>
                Run
              </Button>
            </Card>
          ))}
        </div>
      </div>

      {draft && (
        <Card>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-slate-200">Draft v{draft.version} ({draft.channel_key})</p>
            <Badge tone={STATUS_TONES[draft.status] ?? "neutral"}>{draft.status.replace(/_/g, " ")}</Badge>
            {draft.confidence != null && <span className="text-xs text-slate-500">{Math.round(draft.confidence * 100)}% confidence</span>}
          </div>

          {draft.reasoning && <p className="mb-3 text-xs text-slate-400">{draft.reasoning}</p>}

          {draft.current_content.assembled.subject && (
            <p className="mb-2 text-sm font-medium text-slate-100">
              Subject: {draft.current_content.assembled.subject}
            </p>
          )}

          {!isEditing ? (
            <pre className="mb-4 whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-sm text-slate-200">
              {draft.current_content.assembled.body}
            </pre>
          ) : (
            <textarea className={`${inputClass} mb-4`} rows={10} value={editedBody} onChange={(e) => setEditedBody(e.target.value)} />
          )}

          {sanitizedSignature && (
            <div className="mb-4">
              <p className="mb-1 text-xs font-medium text-slate-400">Signature</p>
              <div className="rounded-lg bg-surface-2 p-3 text-sm text-slate-200" dangerouslySetInnerHTML={{ __html: sanitizedSignature }} />
            </div>
          )}

          {draft.edits.length > 0 && (
            <p className="mb-4 text-xs text-slate-500">
              {draft.edits.length} human edit(s) logged - the original AI wording stays permanently recoverable.
            </p>
          )}

          {/* Explainability is never removed, just kept out of the way for
              business users - developers/reviewers can still inspect every
              block's reasoning, evidence, and raw ids on demand. */}
          <details className="mb-4 rounded-lg border border-border-hairline">
            <summary className="cursor-pointer select-none px-3 py-2 text-xs font-medium text-slate-400 hover:text-slate-200">
              Developer details
            </summary>
            <div className="space-y-4 border-t border-border-hairline p-3">
              <div>
                <p className="mb-1 text-xs font-medium text-slate-500">Draft ID</p>
                <p className="font-mono text-xs text-slate-500">{draft.id}</p>
              </div>

              <div>
                <p className="mb-2 text-xs font-medium text-slate-500">Block breakdown</p>
                <div className="space-y-2">
                  {draft.ai_generated_content.blocks.map((block) => (
                    <div key={block.block_key} className="rounded-lg bg-surface-2 p-2 text-xs">
                      <div className="mb-1 flex items-center gap-2">
                        <span className="font-medium text-slate-200">{block.block_key}</span>
                        <span className="rounded-pill bg-surface-3 px-2 py-0.5 text-slate-400">{block.behavior.replace(/_/g, " ")}</span>
                      </div>
                      {block.reasoning && <p className="text-slate-500">{block.reasoning}</p>}
                    </div>
                  ))}
                </div>
              </div>

              {draft.evidence.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-medium text-slate-500">Evidence</p>
                  <p className="text-xs text-slate-500">
                    {draft.evidence.map((e) => `${e.block_key ?? "draft"}: ${e.excerpt ?? ""}`).filter(Boolean).join(" · ")}
                  </p>
                </div>
              )}

              <div>
                <p className="mb-1 text-xs font-medium text-slate-500">Raw AI-generated content (frozen, never edited)</p>
                <pre className="overflow-x-auto rounded-lg bg-surface-2 p-2 text-xs text-slate-500">
                  {JSON.stringify(draft.ai_generated_content, null, 2)}
                </pre>
              </div>
            </div>
          </details>

          <div className="flex flex-wrap gap-2">
            {draft.status !== "approved" && draft.status !== "rejected" && (
              <>
                <Button size="sm" onClick={approveDraft}>Approve</Button>
                <Button size="sm" variant="destructive" onClick={rejectDraft}>Reject</Button>
              </>
            )}
            {!isEditing ? (
              <Button size="sm" variant="secondary" onClick={startEdit}>Edit</Button>
            ) : (
              <>
                <Button size="sm" onClick={saveEdit}>Save edit</Button>
                <Button size="sm" variant="secondary" onClick={() => setIsEditing(false)}>Cancel</Button>
              </>
            )}
          </div>
        </Card>
      )}
      {!draft && (
        <div className="rounded-lg border border-dashed border-border-hairline-strong bg-surface-2/50 p-6 text-center text-sm text-slate-500">
          No outreach draft generated yet for this channel - create and run a request above.
        </div>
      )}
    </div>
  );
}
