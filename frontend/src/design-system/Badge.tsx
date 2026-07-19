import type { ReactNode } from "react";
import { cn } from "./cn";

/**
 * Badge — M8.1 primitive, Design Bible Section 4.6 ("Badges / tags").
 *
 * `tone` is the ENTIRE semantic vocabulary this system uses for
 * status/impact/attribution everywhere - impact level (High/Medium/Low),
 * pipeline stage, agent type, AI-attribution. `ai` is fixed to
 * accent-ai (purple) specifically so "purple means the AI produced this"
 * holds true on every page (Design Bible Section 6/9.1), not just the
 * dashboard - this is the primitive that enforces that rule in practice.
 */
export type BadgeTone = "neutral" | "primary" | "ai" | "success" | "warning" | "danger" | "info";

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-surface-2 text-slate-300 border-border-hairline",
  primary: "bg-accent-primary/10 text-accent-primary border-accent-primary/30",
  ai: "bg-accent-ai/10 text-accent-ai-soft border-accent-ai/30",
  success: "bg-status-success/10 text-status-success border-status-success/30",
  warning: "bg-status-warning/10 text-status-warning border-status-warning/30",
  danger: "bg-status-danger/10 text-status-danger border-status-danger/30",
  info: "bg-status-info/10 text-status-info border-status-info/30",
};

export interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}

export function Badge({ tone = "neutral", children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-pill border px-2.5 py-0.5 text-xs font-medium leading-5",
        TONE_CLASSES[tone],
        className
      )}
    >
      {children}
    </span>
  );
}
