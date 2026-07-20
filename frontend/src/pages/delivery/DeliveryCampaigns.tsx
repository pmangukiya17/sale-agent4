import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient } from "../../api/client";
import { FormSection, Field, inputClass } from "../../components/FormSection";
import { Toggle } from "../../components/Toggle";
import { Card, Badge, Button, Input, Select, PlaceholderNotice } from "../../design-system";
import type { BadgeTone } from "../../design-system";

interface SendingProfile {
  id: string;
  label: string;
  provider_connection_id: string | null;
}

interface AvailableDraft {
  id: string;
  channel_key: string;
  prospect_name: string;
  contact_name: string | null;
  contact_email: string | null;
  subject_preview: string | null;
}

interface DeliveryCampaign {
  id: string;
  name: string;
  description: string | null;
  status: "draft" | "active" | "paused" | "completed" | "cancelled";
  sending_profile_id: string;
  created_at: string;
}

const STATUS_TONE: Record<string, BadgeTone> = {
  draft: "neutral",
  active: "info",
  paused: "warning",
  completed: "success",
  cancelled: "danger",
};

interface CampaignForm {
  name: string;
  description: string;
  sending_profile_id: string;
  outreach_draft_ids: string[];
  respect_recipient_timezone: boolean;
}

const EMPTY_FORM: CampaignForm = {
  name: "",
  description: "",
  sending_profile_id: "",
  outreach_draft_ids: [],
  respect_recipient_timezone: true,
};

/**
 * DeliveryCampaigns — M8.7 Phase E2 (AI Workforce zone). Migrated in place
 * per Design Bible Section 9.2: identical fetch/create calls, only the
 * markup moves onto design-system tokens/primitives - including retiring
 * the page-local StatusBadge in favor of the one canonical Badge (Design
 * Debt Budget, Section 10.1).
 */
export default function DeliveryCampaigns() {
  const { companyId } = useParams();
  const [campaigns, setCampaigns] = useState<DeliveryCampaign[]>([]);
  const [sendingProfiles, setSendingProfiles] = useState<SendingProfile[]>([]);
  const [availableDrafts, setAvailableDrafts] = useState<AvailableDraft[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<CampaignForm>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setIsLoading(true);
    Promise.all([
      apiClient.get<DeliveryCampaign[]>(`/company-profiles/${companyId}/delivery-campaigns`),
      apiClient.get<SendingProfile[]>(`/company-profiles/${companyId}/sending-profiles`),
      apiClient.get<AvailableDraft[]>(`/company-profiles/${companyId}/delivery-campaigns/available-drafts`),
    ])
      .then(([campaignsRes, profilesRes, draftsRes]) => {
        setCampaigns(campaignsRes.data);
        setSendingProfiles(profilesRes.data);
        setAvailableDrafts(draftsRes.data);
      })
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [companyId]);

  const update = <K extends keyof CampaignForm>(key: K, value: CampaignForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const toggleDraft = (id: string) => {
    update(
      "outreach_draft_ids",
      form.outreach_draft_ids.includes(id) ? form.outreach_draft_ids.filter((d) => d !== id) : [...form.outreach_draft_ids, id]
    );
  };

  const startCreate = () => {
    setForm(EMPTY_FORM);
    setError(null);
    setShowForm(true);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (form.outreach_draft_ids.length === 0) {
      setError("Select at least one approved draft to include in this campaign.");
      return;
    }
    try {
      await apiClient.post(`/company-profiles/${companyId}/delivery-campaigns`, {
        name: form.name,
        description: form.description || null,
        sending_profile_id: form.sending_profile_id,
        outreach_draft_ids: form.outreach_draft_ids,
        respect_recipient_timezone: form.respect_recipient_timezone,
      });
      setShowForm(false);
      load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Could not create this campaign.");
    }
  };

  const usableSendingProfiles = sendingProfiles.filter((p) => p.provider_connection_id);

  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <p className="text-sm text-slate-400">
          Sends already-approved outreach drafts through a sending profile, on a randomized human-like schedule.
        </p>
        <Button onClick={startCreate}>+ New campaign</Button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="mb-6">
          <FormSection title="New campaign">
            <Field label="Name">
              <Input required value={form.name} onChange={(e) => update("name", e.target.value)} />
            </Field>
            <Field label="Sending profile">
              <Select required value={form.sending_profile_id} onChange={(e) => update("sending_profile_id", e.target.value)}>
                <option value="" disabled>
                  Select a sending profile…
                </option>
                {usableSendingProfiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </Select>
              {usableSendingProfiles.length === 0 && (
                <p className="mt-1 text-xs text-status-warning">
                  No sending profile has a connected mailbox yet - set one up under Sending Profiles first.
                </p>
              )}
            </Field>
            <Field label="Description" full>
              <textarea className={inputClass} rows={2} value={form.description} onChange={(e) => update("description", e.target.value)} />
            </Field>
            <Field label="Respect recipient's local business hours">
              <Toggle checked={form.respect_recipient_timezone} onChange={(v) => update("respect_recipient_timezone", v)} />
            </Field>
          </FormSection>

          <FormSection
            title="Select drafts to include"
            description="Every APPROVED outreach draft across this business that isn't already queued elsewhere."
          >
            <div className="sm:col-span-2">
              {availableDrafts.length === 0 ? (
                <p className="text-sm text-slate-400">
                  No approved, unqueued drafts are available right now. Approve outreach for a prospect first.
                </p>
              ) : (
                <div className="max-h-72 space-y-1 overflow-y-auto rounded-lg border border-border-hairline p-2">
                  {availableDrafts.map((d) => (
                    <label key={d.id} className="flex cursor-pointer items-start gap-2 rounded px-2 py-1.5 text-sm hover:bg-surface-2">
                      <input
                        type="checkbox"
                        className="mt-0.5 h-4 w-4 rounded border-border-hairline-strong bg-surface-1 accent-accent-primary"
                        checked={form.outreach_draft_ids.includes(d.id)}
                        onChange={() => toggleDraft(d.id)}
                      />
                      <span>
                        <span className="font-medium text-slate-100">{d.prospect_name}</span>
                        {" — "}
                        <span className="text-slate-300">{d.contact_name ?? d.contact_email ?? "no contact name"}</span>
                        {d.subject_preview && <span className="block text-xs text-slate-500">{d.subject_preview}</span>}
                      </span>
                    </label>
                  ))}
                </div>
              )}
              <p className="mt-2 text-xs text-slate-500">{form.outreach_draft_ids.length} selected</p>
            </div>
          </FormSection>

          {error && <p className="mb-4 text-sm text-status-danger">{error}</p>}

          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
            <Button type="submit">Create campaign</Button>
          </div>
        </form>
      )}

      {!isLoading && campaigns.length === 0 && !showForm && <PlaceholderNotice kind="no-data" reason="No campaigns yet." />}

      <div className="space-y-3">
        {campaigns.map((c) => (
          <Link key={c.id} to={`/businesses/${companyId}/delivery/campaigns/${c.id}`} className="block">
            <Card className="hover:border-border-hairline-strong">
              <div className="flex items-center justify-between">
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <span className="font-medium text-slate-100">{c.name}</span>
                    <Badge tone={STATUS_TONE[c.status] ?? "neutral"}>{c.status}</Badge>
                  </div>
                  {c.description && <p className="text-sm text-slate-400">{c.description}</p>}
                </div>
                <span className="text-xs text-slate-500">{new Date(c.created_at).toLocaleString()}</span>
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
