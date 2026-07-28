import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "./cn";

/**
 * SlideOver — AI Gateway UI Foundation (M8.1) primitive, Design Bible
 * Section 4.5 (Glass: "used sparingly and specifically for overlays that
 * sit above other content... a z-axis cue, not a finish applied
 * everywhere").
 *
 * This is a right-edge inspector panel - the reading pattern for a log/
 * table row a user scans and dismisses without losing their place (its
 * first consumer is AI Gateway's Activity Detail view - see
 * ai-gateway/components/ActivityDetailDrawer.tsx). A centered `Modal`
 * would obscure the very row that opened it and reset visual context on
 * every open/close; a fixed-width panel that slides in from the right
 * keeps the triggering row in view instead.
 *
 * Deliberately its OWN component, not a `placement` prop bolted onto
 * `Modal` - per the approved M8.1 scope. `Modal`'s existing 20+ call
 * sites are all centered, small, form/confirmation-shaped dialogs; a
 * slide-over is a structurally different surface (full-height, edge-
 * anchored, meant to sit alongside content rather than interrupt it), and
 * overloading one component with two geometries would mean every future
 * reader of Modal.tsx has to hold both shapes in mind to change either.
 * Two small single-purpose components, not one branching one - the same
 * judgment call this project already made elsewhere (e.g. ConfirmDialog
 * staying separate from Modal rather than becoming a Modal variant).
 *
 * Reuses Modal's own internal patterns directly (per the approved scope):
 * `createPortal` into `document.body` so an ancestor's `overflow-hidden`
 * never clips it, Escape-to-close, backdrop-click-to-close, focus moved
 * to the panel on open. Same disclosed, MVP-scope gap as Modal: no full
 * focus trap (Tab cycling back from the last focusable element) yet -
 * flagged here rather than silently assumed solved, exactly as Modal's
 * own docstring flags it.
 */
export interface SlideOverProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  className?: string;
}

export function SlideOver({ open, onClose, title, children, className }: SlideOverProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={cn(
          "relative flex h-full w-full max-w-md flex-col border-l border-border-hairline-strong bg-surface-1/95 p-6 shadow-elevation-3 backdrop-blur-xl transition-transform duration-state-change ease-standard focus:outline-none",
          "motion-reduce:transition-none",
          className
        )}
      >
        {title && (
          <div className="mb-4 flex shrink-0 items-center justify-between">
            <h2 className="text-h3 font-semibold text-slate-100">{title}</h2>
            <button
              onClick={onClose}
              className="rounded-lg p-1 text-slate-400 hover:bg-surface-2 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
              aria-label="Close"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body
  );
}
