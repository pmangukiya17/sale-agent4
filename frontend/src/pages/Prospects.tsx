import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { Card, Badge, Button, Input, Select, PlaceholderNotice } from "../design-system";
import type { BadgeTone } from "../design-system";

type ProspectStatus =
  | "new" | "duplicate_review" | "scored" | "qualified" | "unqualified"
  | "in_review" | "approved" | "rejected" | "archived";

interface ScoreBreakdownEntry {
  factor: string;
  weight: number;
  matched: boolean | null;
  points: number;
  explanation: string;
}

interface ProspectContact {
  id: string;
  name: string | null;
  role: string | null;
  department: string | null;
  decision_maker_level: string;
  email: string | null;
  phone: string | null;
  confidence: number | null;
}

interface Prospect {
  id: string;
  name: string;
  website: string | null;
  country: string | null;
  company_size_range: string | null;
  description: string | null;
  status: ProspectStatus;
  total_score: number | null;
  score_breakdown: ScoreBreakdownEntry[] | null;
  ai_reasoning: string | null;
  potential_duplicate_of_prospect_id: string | null;
  duplicate_confidence: number | null;
  rejection_reason: string | null;
  contacts: ProspectContact[];
}

interface TimelineEvent {
  id: string;
  event_type: string;
  actor: string;
  created_at: string;
}

const STATUS_LABELS: Record<ProspectStatus, string> = {
  new: "New", duplicate_review: "Needs duplicate review", scored: "Scored",
  qualified: "Qualified", unqualified: "Unqualified", in_review: "In review",
  approved: "Approved", rejected: "Rejected", archived: "Archived",
};

// Maps each prospect status onto the design system's fixed Badge tone
// vocabulary (Design Bible Section 4.6) - replaces the page's own bespoke
// light/dark color pairs per status with the one shared semantic palette.
const STATUS_TONES: Record<ProspectStatus, BadgeTone> = {
  new: "neutral",
  duplicate_review: "warning",
  scored: "neutral",
  qualified: "success",
  unqualified: "neutral",
  in_review: "info",
  approved: "success",
  rejected: "danger",
  archived: "neutral",
};

// Manual contact entry only - mirrors app/schemas/prospect_contact.py's
// ProspectContactCreate exactly. Not automated contact discovery (that's
// M5's territory); this just exposes the existing CRUD endpoint that
// Outreach (M4) already depends on but nothing in the UI ever called.
interface ContactForm {
  name: string;
  role: string;
  department: string;
  decision_maker_level: string;
  email: string;
  phone: string;
}

const EMPTY_CONTACT_FORM: ContactForm = {
  name: "",
  role: "",
  department: "",
  decision_maker_level: "unknown",
  email: "",
  phone: "",
};

const DECISION_MAKER_LEVELS: { value: string; label: string }[] = [
  { value: "unknown", label: "Unknown" },
  { value: "final_decision_maker", label: "Final decision maker" },
  { value: "influencer", label: "Influencer" },
  { value: "gatekeeper", label: "Gatekeeper" },
];

/**
 * Prospects — M8.7 Phase E1 (CRM zone). Migrated in place per Design
 * Bible Section 9.2: every fetch, form, and action call below is
 * byte-identical to the pre-migration version - only the markup moves
 * from bespoke light/dark-variant Tailwind onto the design-system
 * primitives (Card, Badge, Button, Input, Select, PlaceholderNotice).
 * Kept as one expandable-row page rather than reshaped into the Table
 * primitive, since each row's expanded state (score breakdown, contacts
 * form, timeline, approve/reject/archive actions) isn't tabular data -
 * Table is for uniform rows of scalar cells, per its own docstring.
 */
export default function Prospects() {
  const { companyId } = useParams();
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [minScore, setMinScore] = useState<string>("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);

  const [showContactForm, setShowContactForm] = useState<Record<string, boolean>>({});
  const [contactForms, setContactForms] = useState<Record<string, ContactForm>>({});
  const [contactSaving, setContactSaving] = useState<Record<string, boolean>>({});
  const [contactErrors, setContactErrors] = useState<Record<string, string | null>>({});
  const [contactSavedMessage, setContactSavedMessage] = useState<Record<string, boolean>>({});
  const contactSavedTimeouts = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // Shared fetch. `showLoadingScreen=true` is the initial/filtered load
  // (full-page loading state, same as before); `false` is used after
  // adding a contact so the list refreshes in place - no collapse to a
  // loading screen, no scroll jump, same fix as CompanyICP's save flow.
  const fetchProspects = (showLoadingScreen: boolean) => {
    if (showLoadingScreen) setIsLoading(true);
    const params = new URLSearchParams();
    if (statusFilter) params.set("status", statusFilter);
    if (minScore) params.set("min_score", minScore);
    return apiClient
      .get(`/company-profiles/${companyId}/prospects?${params.toString()}`)
      .then((res) => {
        setProspects(res.data);
        if (showLoadingScreen) setIsLoading(false);
      });
  };

  const load = () => {
    void fetchProspects(true);
  };
  const refreshProspectsSilently = () => fetchProspects(false);

  useEffect(load, [companyId, statusFilter, minScore]);

  // Clear any pending "Contact added" auto-hide timers on unmount.
  useEffect(() => {
    return () => {
      Object.values(contactSavedTimeouts.current).forEach(clearTimeout);
    };
  }, []);

  const toggleContactForm = (prospectId: string) => {
    setContactErrors((prev) => ({ ...prev, [prospectId]: null }));
    setShowContactForm((prev) => {
      const opening = !prev[prospectId];
      if (opening && !contactForms[prospectId]) {
        setContactForms((f) => ({ ...f, [prospectId]: { ...EMPTY_CONTACT_FORM } }));
      }
      return { ...prev, [prospectId]: opening };
    });
  };

  const updateContactForm = (prospectId: string, field: keyof ContactForm, value: string) => {
    setContactForms((prev) => ({
      ...prev,
      [prospectId]: { ...(prev[prospectId] ?? EMPTY_CONTACT_FORM), [field]: value },
    }));
  };

  const showContactSavedMessage = (prospectId: string) => {
    setContactSavedMessage((prev) => ({ ...prev, [prospectId]: true }));
    if (contactSavedTimeouts.current[prospectId]) clearTimeout(contactSavedTimeouts.current[prospectId]);
    contactSavedTimeouts.current[prospectId] = setTimeout(() => {
      setContactSavedMessage((prev) => ({ ...prev, [prospectId]: false }));
    }, 3000);
  };

  const handleAddContact = async (e: FormEvent, prospectId: string) => {
    e.preventDefault();
    const form = contactForms[prospectId] ?? EMPTY_CONTACT_FORM;
    if (!form.name.trim()) {
      setContactErrors((prev) => ({ ...prev, [prospectId]: "Name is required." }));
      return;
    }
    setContactErrors((prev) => ({ ...prev, [prospectId]: null }));
    setContactSaving((prev) => ({ ...prev, [prospectId]: true }));
    try {
      await apiClient.post(`/company-profiles/${companyId}/prospects/${prospectId}/contacts`, {
        name: form.name.trim(),
        role: form.role.trim() || null,
        department: form.department.trim() || null,
        decision_maker_level: form.decision_maker_level,
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
      });
      await refreshProspectsSilently();
      setContactForms((prev) => ({ ...prev, [prospectId]: { ...EMPTY_CONTACT_FORM } }));
      setShowContactForm((prev) => ({ ...prev, [prospectId]: false }));
      showContactSavedMessage(prospectId);
    } catch {
      setContactErrors((prev) => ({ ...prev, [prospectId]: "Could not save this contact." }));
    } finally {
      setContactSaving((prev) => ({ ...prev, [prospectId]: false }));
    }
  };

  const toggleExpand = async (prospect: Prospect) => {
    if (expandedId === prospect.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(prospect.id);
    const res = await apiClient.get(`/company-profiles/${companyId}/prospects/${prospect.id}/timeline`);
    setTimeline(res.data);
  };

  const runAction = async (prospect: Prospect, action: "approve" | "reject" | "archive") => {
    setActionError(null);
    try {
      if (action === "reject") {
        const reason = window.prompt("Reason for rejecting this prospect?");
        if (!reason) return;
        await apiClient.post(`/company-profiles/${companyId}/prospects/${prospect.id}/reject`, { rejection_reason: reason });
      } else {
        await apiClient.post(`/company-profiles/${companyId}/prospects/${prospect.id}/${action}`);
      }
      load();
    } catch {
      setActionError(`Could not ${action} this prospect.`);
    }
  };

  return (
    <div>
      <Breadcrumbs items={[{ label: "Businesses", to: "/businesses" }, { label: "Prospects" }]} />

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-h1 font-semibold text-slate-100">Prospects</h1>
          <p className="text-body text-slate-400">
            Review what Discovery found. Nothing reaches the CRM until you approve it here.
          </p>
        </div>
        <div className="flex gap-2">
          <Select className="w-48" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All statuses</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </Select>
          <Input
            className="w-32"
            placeholder="Min score"
            type="number"
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
          />
        </div>
      </div>

      {actionError && <p className="mb-4 text-sm text-status-danger">{actionError}</p>}

      {!isLoading && prospects.length === 0 && (
        <PlaceholderNotice kind="no-data" reason="No prospects match these filters yet." />
      )}

      <div className="space-y-3">
        {isLoading &&
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="h-20 animate-pulse">
              {null}
            </Card>
          ))}

        {prospects.map((prospect) => {
          const isOpen = expandedId === prospect.id;
          return (
            <Card key={prospect.id}>
              <button className="flex w-full items-start justify-between text-left" onClick={() => toggleExpand(prospect)}>
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <h3 className="font-semibold text-slate-100">{prospect.name}</h3>
                    <Badge tone={STATUS_TONES[prospect.status]}>{STATUS_LABELS[prospect.status]}</Badge>
                    {prospect.potential_duplicate_of_prospect_id && (
                      <Badge tone="warning">
                        possible duplicate ({Math.round((prospect.duplicate_confidence ?? 0) * 100)}%)
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-slate-500">
                    {[prospect.website, prospect.country, prospect.company_size_range].filter(Boolean).join(" · ")}
                  </p>
                </div>
                <span className="text-lg font-semibold text-slate-200">
                  {prospect.total_score != null ? Math.round(prospect.total_score) : "—"}
                </span>
              </button>

              {isOpen && (
                <div className="mt-4 space-y-4 border-t border-border-hairline pt-4">
                  {prospect.description && <p className="text-sm text-slate-300">{prospect.description}</p>}

                  {prospect.score_breakdown && prospect.score_breakdown.length > 0 && (
                    <div>
                      <p className="mb-2 text-sm font-medium text-slate-200">Score breakdown</p>
                      <div className="space-y-2">
                        {prospect.score_breakdown.map((entry, i) => (
                          <div key={i}>
                            <div className="mb-0.5 flex justify-between text-xs text-slate-500">
                              <span>{entry.factor.replace(/_/g, " ")}</span>
                              <span>{entry.points} / {entry.weight}</span>
                            </div>
                            <div className="h-2 w-full rounded-full bg-surface-2">
                              <div
                                className="h-2 rounded-full bg-accent-primary"
                                style={{ width: `${Math.min(100, (entry.points / entry.weight) * 100)}%` }}
                              />
                            </div>
                            <p className="mt-0.5 text-xs text-slate-500">{entry.explanation}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {prospect.ai_reasoning && (
                    <div>
                      <p className="mb-1 text-sm font-medium text-slate-200">AI reasoning</p>
                      <p className="text-sm text-slate-300">{prospect.ai_reasoning}</p>
                    </div>
                  )}

                  {prospect.rejection_reason && (
                    <p className="text-sm text-status-danger">Rejected: {prospect.rejection_reason}</p>
                  )}

                  <div>
                    <div className="mb-1 flex items-center justify-between">
                      <p className="text-sm font-medium text-slate-200">Contacts</p>
                      <div className="flex items-center gap-2">
                        {contactSavedMessage[prospect.id] && (
                          <span className="text-xs font-medium text-status-success">Contact added</span>
                        )}
                        <button
                          type="button"
                          onClick={() => toggleContactForm(prospect.id)}
                          className="text-xs font-medium text-slate-300 underline hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
                        >
                          {showContactForm[prospect.id] ? "Cancel" : "+ Add contact"}
                        </button>
                      </div>
                    </div>

                    {prospect.contacts.length === 0 && !showContactForm[prospect.id] && (
                      <p className="text-xs text-slate-500">No contacts yet.</p>
                    )}

                    {prospect.contacts.length > 0 && (
                      <div className="mb-2 space-y-1">
                        {prospect.contacts.map((c) => (
                          <div key={c.id} className="flex items-center justify-between gap-2">
                            <p className="text-xs text-slate-500">
                              {[c.name, c.role, c.department, c.decision_maker_level, c.email, c.phone].filter(Boolean).join(" · ")}
                            </p>
                            <Link
                              to={`/businesses/${companyId}/prospects/${prospect.id}/contacts/${c.id}/outreach`}
                              className="shrink-0 rounded-lg border border-border-hairline px-2 py-0.5 text-xs font-medium text-slate-200 hover:border-border-hairline-strong hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
                            >
                              Outreach
                            </Link>
                          </div>
                        ))}
                      </div>
                    )}

                    {showContactForm[prospect.id] && (
                      <form
                        onSubmit={(e) => handleAddContact(e, prospect.id)}
                        className="mt-2 space-y-2 rounded-lg border border-border-hairline bg-surface-2 p-3"
                      >
                        {contactErrors[prospect.id] && (
                          <p className="text-xs text-status-danger">{contactErrors[prospect.id]}</p>
                        )}
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <Input
                            placeholder="Name"
                            value={contactForms[prospect.id]?.name ?? ""}
                            onChange={(e) => updateContactForm(prospect.id, "name", e.target.value)}
                          />
                          <Input
                            placeholder="Job title / role"
                            value={contactForms[prospect.id]?.role ?? ""}
                            onChange={(e) => updateContactForm(prospect.id, "role", e.target.value)}
                          />
                          <Input
                            placeholder="Department"
                            value={contactForms[prospect.id]?.department ?? ""}
                            onChange={(e) => updateContactForm(prospect.id, "department", e.target.value)}
                          />
                          <Select
                            value={contactForms[prospect.id]?.decision_maker_level ?? "unknown"}
                            onChange={(e) => updateContactForm(prospect.id, "decision_maker_level", e.target.value)}
                          >
                            {DECISION_MAKER_LEVELS.map((lvl) => (
                              <option key={lvl.value} value={lvl.value}>{lvl.label}</option>
                            ))}
                          </Select>
                          <Input
                            placeholder="Email"
                            type="email"
                            value={contactForms[prospect.id]?.email ?? ""}
                            onChange={(e) => updateContactForm(prospect.id, "email", e.target.value)}
                          />
                          <Input
                            placeholder="Phone"
                            value={contactForms[prospect.id]?.phone ?? ""}
                            onChange={(e) => updateContactForm(prospect.id, "phone", e.target.value)}
                          />
                        </div>
                        <div className="flex justify-end gap-2">
                          <Button type="button" variant="secondary" size="sm" onClick={() => toggleContactForm(prospect.id)}>
                            Cancel
                          </Button>
                          <Button type="submit" size="sm" isLoading={contactSaving[prospect.id]}>
                            Save contact
                          </Button>
                        </div>
                      </form>
                    )}
                  </div>

                  {timeline.length > 0 && (
                    <div>
                      <p className="mb-1 text-sm font-medium text-slate-200">Timeline</p>
                      <div className="space-y-1">
                        {timeline.map((event) => (
                          <p key={event.id} className="text-xs text-slate-500">
                            {new Date(event.created_at).toLocaleString()} — {event.event_type.replace(/_/g, " ")} ({event.actor})
                          </p>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex flex-wrap gap-2">
                    <Link
                      to={`/businesses/${companyId}/prospects/${prospect.id}/research`}
                      className="rounded-lg border border-border-hairline px-3 py-1.5 text-sm font-medium text-slate-200 hover:border-border-hairline-strong hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
                    >
                      Research
                    </Link>
                    <Link
                      to={`/businesses/${companyId}/prospects/${prospect.id}/strategy`}
                      className="rounded-lg border border-border-hairline px-3 py-1.5 text-sm font-medium text-slate-200 hover:border-border-hairline-strong hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
                    >
                      Strategy
                    </Link>
                    <Button size="sm" onClick={() => runAction(prospect, "approve")}>
                      Approve
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => runAction(prospect, "reject")}>
                      Reject
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => runAction(prospect, "archive")}>
                      Archive
                    </Button>
                  </div>
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
