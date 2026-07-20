import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient } from "../../api/client";

/**
 * Lightweight, dismissible first-time checklist for the Delivery module.
 * Purely a view over data that already exists (ProviderConnection /
 * SendingProfile / DeliveryCampaign / DeliveryQueueItem via the
 * delivery-onboarding-status endpoint) - it creates nothing, changes no
 * write path, and never auto-creates a Sending Profile or anything else.
 * "Delivery Ready" is derived client-side as the AND of all four signals
 * rather than trusted as its own field, so there is exactly one source of
 * truth for what each step means.
 *
 * Dismissal is per-business (keyed by companyId) and persisted in
 * localStorage, following the same pattern CompanyContext.tsx already uses
 * for sales_agent_active_company_id. Once dismissed for a business it stays
 * dismissed even if the business later becomes fully onboarded again after
 * e.g. disconnecting a mailbox - re-showing a warning banner mid-workflow
 * would be noisier than helpful for a user who already knows the ropes.
 */

interface OnboardingStatus {
  has_connected_mailbox: boolean;
  has_sending_profile_with_mailbox: boolean;
  has_campaign: boolean;
  has_sent_email: boolean;
}

const dismissKey = (companyId: string) => `sales_agent_delivery_onboarding_dismissed_${companyId}`;

interface StepDef {
  label: string;
  done: (s: OnboardingStatus) => boolean;
  to: string;
}

export default function DeliveryOnboarding() {
  const { companyId } = useParams();
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (!companyId) return;
    setDismissed(localStorage.getItem(dismissKey(companyId)) === "1");
    apiClient
      .get<OnboardingStatus>(`/company-profiles/${companyId}/delivery-onboarding-status`)
      .then(({ data }) => setStatus(data))
      .catch(() => setStatus(null));
  }, [companyId]);

  if (!companyId || !status || dismissed) return null;

  const steps: StepDef[] = [
    { label: "Connect mailbox", done: (s) => s.has_connected_mailbox, to: `/businesses/${companyId}/delivery/connections` },
    {
      label: "Create Sending Profile",
      done: (s) => s.has_sending_profile_with_mailbox,
      to: `/businesses/${companyId}/delivery/sending-profiles`,
    },
    { label: "Create Campaign", done: (s) => s.has_campaign, to: `/businesses/${companyId}/delivery/campaigns` },
    { label: "Send first email", done: (s) => s.has_sent_email, to: `/businesses/${companyId}/delivery/campaigns` },
  ];

  const deliveryReady = steps.every((step) => step.done(status));

  const dismiss = () => {
    localStorage.setItem(dismissKey(companyId), "1");
    setDismissed(true);
  };

  if (deliveryReady && collapsed) return null;

  if (deliveryReady) {
    return (
      <div className="mb-6 flex items-center justify-between rounded-lg border border-status-success/30 bg-status-success/5 px-4 py-2.5 text-sm">
        <span className="font-medium text-status-success">✓ Delivery Ready</span>
        <div className="flex items-center gap-3">
          <button onClick={() => setCollapsed(true)} className="text-xs text-status-success hover:underline">
            Hide
          </button>
          <button onClick={dismiss} className="text-status-success hover:brightness-125" aria-label="Dismiss onboarding checklist">
            ×
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-6 rounded-lg border border-border-hairline bg-surface-1 px-4 py-3">
      <div className="mb-2.5 flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Get set up for delivery</p>
        <button onClick={dismiss} className="text-slate-500 hover:text-slate-200" aria-label="Dismiss onboarding checklist">
          ×
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {steps.map((step, i) => {
          const isDone = step.done(status);
          return (
            <div key={step.label} className="flex items-center gap-2">
              {isDone ? (
                <span className="flex items-center gap-1.5 rounded-pill bg-status-success/10 px-3 py-1 text-sm text-status-success">
                  <span>✓</span>
                  {step.label}
                </span>
              ) : (
                <Link
                  to={step.to}
                  className="flex items-center gap-1.5 rounded-pill border border-border-hairline px-3 py-1 text-sm text-slate-300 hover:border-border-hairline-strong hover:text-slate-100"
                >
                  <span className="text-slate-600">○</span>
                  {step.label}
                </Link>
              )}
              {i < steps.length - 1 && <span className="text-slate-600">→</span>}
            </div>
          );
        })}
        <span className="text-slate-600">→</span>
        <span
          className={`flex items-center gap-1.5 rounded-pill px-3 py-1 text-sm ${
            deliveryReady ? "bg-status-success/10 text-status-success" : "border border-dashed border-border-hairline-strong text-slate-500"
          }`}
        >
          {deliveryReady ? "✓" : "○"} Delivery Ready
        </span>
      </div>
    </div>
  );
}
