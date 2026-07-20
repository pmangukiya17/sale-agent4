import { createContext, useCallback, useContext, useState } from "react";
import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { cn } from "./cn";

/**
 * Toast — M8.7 Phase D primitive, Design Bible Section 4.6: "toast
 * (transient, bottom-right) for user-triggered action feedback... a
 * different surface and job from the notification bell's dropdown
 * (persistent list, for AI-originated events)." This is exclusively the
 * former - a page calling `showToast()` after a user's own save/delete/
 * submit action succeeds or fails. It is never a channel for AI-
 * originated events; those go through the Notification Center
 * (notifications/useNotifications.ts) and TopCommandStrip's bell, a
 * deliberately separate system with a different lifespan and urgency.
 *
 * Needs app-wide state (a queue of currently-visible toasts triggered
 * from anywhere), unlike every other primitive in this folder - hence a
 * Context/Provider pair rather than a plain component. `ToastProvider` is
 * mounted once at the app root (main.tsx), and any component calls
 * `useToast().showToast(...)` - never constructs its own toast queue.
 */
export type ToastTone = "neutral" | "success" | "danger";

export interface ToastOptions {
  message: string;
  tone?: ToastTone;
  durationMs?: number;
}

interface ToastRecord {
  id: string;
  message: string;
  tone: ToastTone;
}

interface ToastContextValue {
  showToast: (options: ToastOptions) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const TONE_STYLES: Record<ToastTone, { icon: typeof Info; border: string; iconColor: string }> = {
  neutral: { icon: Info, border: "border-border-hairline-strong", iconColor: "text-accent-secondary" },
  success: { icon: CheckCircle2, border: "border-status-success/40", iconColor: "text-status-success" },
  danger: { icon: AlertTriangle, border: "border-status-danger/40", iconColor: "text-status-danger" },
};

const DEFAULT_DURATION_MS = 4000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);

  const showToast = useCallback((options: ToastOptions) => {
    const id = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Date.now() + Math.random());
    const tone = options.tone ?? "neutral";
    setToasts((prev) => [...prev, { id, message: options.message, tone }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, options.durationMs ?? DEFAULT_DURATION_MS);
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
        {toasts.map((toast) => {
          const style = TONE_STYLES[toast.tone];
          const Icon = style.icon;
          return (
            <div
              key={toast.id}
              role="status"
              className={cn(
                "pointer-events-auto flex items-start gap-2 rounded-card border bg-surface-1/95 p-3 text-sm text-slate-100 shadow-elevation-3 backdrop-blur-xl",
                style.border
              )}
            >
              <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", style.iconColor)} aria-hidden="true" />
              <span>{toast.message}</span>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider (see main.tsx's own provider tree)");
  }
  return ctx;
}
