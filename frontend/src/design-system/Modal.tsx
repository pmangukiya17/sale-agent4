import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "./cn";

/**
 * Modal — M8.7 Phase D primitive, Design Bible Section 4.6 (Modal) +
 * Section 4.5 (Glass): "used sparingly and specifically for overlays
 * that sit above other content — the command palette, modals, dropdown
 * menus, toast notifications... a z-axis cue, not a finish applied
 * everywhere." This is the one place in the design system glass is the
 * DEFAULT treatment, matching that rule directly - the panel is
 * `bg-surface-1/95 backdrop-blur-xl`, the same glass treatment
 * TopCommandStrip's own notification dropdown already established, not a
 * new one invented per component (Design Debt Budget, Section 10.1).
 *
 * Rendered via `createPortal` into `document.body` (react-dom, no new
 * dependency) so a modal opened from deep inside a page's own DOM
 * hierarchy is never accidentally clipped by an ancestor's
 * `overflow-hidden`/`max-h-*` - a real risk in this dashboard's own
 * densely-nested layout (Section 8).
 *
 * Deliberately a simplified, MVP focus-management scope, disclosed
 * rather than silently incomplete: closes on Escape and on backdrop
 * click, and moves focus to the panel itself on open, but does NOT
 * implement a full focus trap (cycling Tab back to the first focusable
 * element once it reaches the last). A real accessibility gap for
 * keyboard-only users navigating past the modal's last control - flagged
 * here as a named, future refinement (Section 12's own accessibility
 * strategy), not something to claim is already solved.
 */
export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  className?: string;
}

export function Modal({ open, onClose, title, children, className }: ModalProps) {
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={cn(
          "relative w-full max-w-lg rounded-card border border-border-hairline-strong bg-surface-1/95 p-6 shadow-elevation-3 backdrop-blur-xl focus:outline-none",
          className
        )}
      >
        {title && (
          <div className="mb-4 flex items-center justify-between">
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
        {children}
      </div>
    </div>,
    document.body
  );
}
