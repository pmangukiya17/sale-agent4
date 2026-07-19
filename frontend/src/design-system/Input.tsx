import { forwardRef } from "react";
import type { InputHTMLAttributes } from "react";
import { cn } from "./cn";

/**
 * Input — M8.1 primitive, Design Bible Section 4.6.
 *
 * Dark-surface field, hairline border, a visible accent-primary focus
 * ring. That focus ring is not optional styling - Section 12
 * (Accessibility Strategy) calls out, explicitly, that none of the nine
 * source concepts show a visible keyboard-focus state anywhere, and
 * names that as a real gap this system does not repeat. Every primitive
 * in this folder that's interactive (Button, Input, and Select/Dropdown
 * when they're built) carries this same focus-visible treatment for that
 * reason - it's a correction being enforced structurally, not a
 * per-component style choice someone could forget to add.
 */
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest },
  ref
) {
  return (
    <input
      ref={ref}
      className={cn(
        "h-10 w-full rounded-lg border border-border-hairline bg-surface-2 px-3 text-sm text-slate-100 placeholder:text-slate-500",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...rest}
    />
  );
});
