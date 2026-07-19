import { forwardRef } from "react";
import type { ButtonHTMLAttributes } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "./cn";

/**
 * Button — M8.1 primitive, Design Bible Section 4.6.
 *
 * Four variants, matching the Design Bible's own catalog exactly:
 * primary (filled, accent-primary), secondary (hairline border,
 * transparent fill), ghost (text-only), destructive (danger). States:
 * default, hover, active, focus-visible, disabled, loading - `isLoading`
 * swaps the label for a spinner WITHOUT changing the button's width
 * (min-width reserved via the label staying in the DOM, visually hidden),
 * so a loading action never causes a layout jump - a small but real
 * "no decorative-but-false motion" rule (Design Bible Section 11) applied
 * to a primitive, not just to the flashier modules.
 */
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "destructive";
  size?: "sm" | "md";
  isLoading?: boolean;
}

const VARIANT_CLASSES: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary: "bg-accent-primary text-white hover:brightness-110 active:brightness-95 shadow-elevation-1",
  secondary: "bg-transparent text-slate-100 border border-border-hairline hover:border-border-hairline-strong hover:bg-surface-2",
  ghost: "bg-transparent text-slate-300 hover:text-white hover:bg-surface-2",
  destructive: "bg-status-danger text-white hover:brightness-110 active:brightness-95",
};

const SIZE_CLASSES: Record<NonNullable<ButtonProps["size"]>, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", isLoading = false, disabled, className, children, ...rest },
  ref
) {
  return (
    <button
      ref={ref}
      disabled={disabled || isLoading}
      className={cn(
        "relative inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0",
        "disabled:cursor-not-allowed disabled:opacity-50",
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        className
      )}
      {...rest}
    >
      {/* The label stays in the DOM at full size (just visually hidden)
          so the button's own width never changes between idle and
          loading - the spinner overlays on top rather than being laid
          out alongside a hidden-but-still-reserved label, which would
          make the loading state wider than idle. */}
      <span className={cn("inline-flex items-center gap-2", isLoading && "invisible")}>{children}</span>
      {isLoading && (
        <span className="absolute inset-0 flex items-center justify-center">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          <span className="sr-only">Loading</span>
        </span>
      )}
    </button>
  );
});
