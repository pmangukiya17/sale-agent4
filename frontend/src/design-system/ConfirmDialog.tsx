import { Button } from "./Button";
import { Modal } from "./Modal";

/**
 * ConfirmDialog — M8.17 (Global Delete System) primitive, Design Bible
 * Section 4.6's Modal building block specialized for one job: "are you
 * sure?" before a destructive, hard-to-undo action.
 *
 * Built on the existing `Modal` primitive rather than a new overlay
 * mechanism (Design Debt Budget, Section 10.1) - this is deliberately
 * the ONLY confirmation surface in the app going forward. Before M8.17,
 * three pages (CompanyProducts.tsx, CompanyKnowledgeBase.tsx,
 * DeliverySendingProfiles.tsx) each called the browser's native
 * `window.confirm()` directly - unstyled, blocking, and with no loading
 * state while the request is in flight. This component - paired with
 * `hooks/useDeleteResource.ts` - replaces every one of those call sites
 * and is the only pattern new delete-capable pages should reach for.
 *
 * Deliberately generic (title/message/confirmLabel/tone are the only
 * knobs) rather than delete-specific, so a future "confirm before
 * archiving" or "confirm before sending" flow can reuse it too -
 * `useDeleteResource` is the delete-specific layer on top of this,
 * not baked into the dialog itself.
 */
export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "danger" | "neutral";
  isLoading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  tone = "danger",
  isLoading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Modal open={open} onClose={isLoading ? () => {} : onCancel} title={title} className="max-w-md">
      <p className="text-sm text-slate-300">{message}</p>
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel} disabled={isLoading}>
          {cancelLabel}
        </Button>
        <Button variant={tone === "danger" ? "destructive" : "primary"} onClick={onConfirm} isLoading={isLoading}>
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
