import { Button, Modal } from "../design-system";

/**
 * PremiumApprovalDialog — M9 (AI Provider Hierarchy). Renders the exact
 * "STOP, ask user" prompt the AI Provider Hierarchy spec describes:
 * local/free AI providers were unavailable, and using a premium provider
 * (Claude/OpenAI/Gemini) requires the user's explicit Yes/No, never an
 * automatic call. Shown from ProspectResearch.tsx BEFORE a research run
 * is submitted (see app/research/ai_preflight.py's own docstring for why
 * this is a pre-flight check, not a mid-workflow interrupt).
 *
 * Built on the existing Modal primitive directly (not ConfirmDialog) since
 * the content here - a reasons list plus a cost estimate - needs more
 * structure than ConfirmDialog's single message string offers; this is
 * still the one Modal primitive underneath, not a new overlay mechanism.
 */
export interface PremiumApprovalDialogProps {
  open: boolean;
  candidateProviderKey: string | null;
  estimatedCostUsd: number | null;
  reasons: string[];
  isSubmitting?: boolean;
  onApprove: () => void;
  onDecline: () => void;
}

function providerLabel(providerKey: string | null): string {
  if (!providerKey) return "a premium AI provider";
  return providerKey
    .split("_")
    .map((part) => (part.length > 0 ? part[0].toUpperCase() + part.slice(1) : part))
    .join(" ");
}

export function PremiumApprovalDialog({
  open,
  candidateProviderKey,
  estimatedCostUsd,
  reasons,
  isSubmitting = false,
  onApprove,
  onDecline,
}: PremiumApprovalDialogProps) {
  return (
    <Modal open={open} onClose={isSubmitting ? () => {} : onDecline} title="This task is unusually complex" className="max-w-md">
      <p className="text-sm text-slate-300">
        Local and free AI providers aren't available for this run. Completing it with full AI analysis would use{" "}
        <span className="font-medium text-slate-100">{providerLabel(candidateProviderKey)}</span>, a premium provider.
      </p>

      {reasons.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Reason(s)</p>
          <ul className="mt-1 list-inside list-disc text-sm text-slate-300">
            {reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-3 text-sm text-slate-300">
        Estimated API cost:{" "}
        <span className="font-medium text-slate-100">
          {estimatedCostUsd != null ? `~$${estimatedCostUsd.toFixed(4)}` : "not available"}
        </span>
      </p>

      <p className="mt-3 text-sm text-slate-400">
        Without approval, this run will complete without AI-generated signals/recommendations - your existing
        research data is never lost, and you can approve and re-run at any time.
      </p>

      <div className="mt-6 flex justify-end gap-2">
        <Button variant="secondary" onClick={onDecline} disabled={isSubmitting}>
          No, skip AI analysis
        </Button>
        <Button variant="primary" onClick={onApprove} isLoading={isSubmitting}>
          Yes, use {providerLabel(candidateProviderKey)}
        </Button>
      </div>
    </Modal>
  );
}
