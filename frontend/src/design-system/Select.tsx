import { forwardRef } from "react";
import type { SelectHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "./cn";

/**
 * Select — M8.7 Phase D primitive, Design Bible Section 4.6 ("Inputs /
 * dropdowns / multi-select — dark-surface fields, hairline border,
 * accent-primary focus ring").
 *
 * A styled wrapper around the native `<select>`, not a from-scratch
 * custom dropdown/combobox - deliberately, matching this project's own
 * "deterministic MVP, not over-built" discipline elsewhere (e.g.
 * event_dispatcher_worker.py's own _matches_filter() docstring on the
 * backend). Native `<select>` already gives correct keyboard operability,
 * screen-reader semantics, and mobile-native picker UI for free - a
 * hand-built combobox would have to re-earn all of that. The tradeoff,
 * disclosed rather than silently accepted: the OPTION LIST's own dropdown
 * panel cannot be restyled with our dark surface/glass tokens (that's the
 * browser's native rendering, outside any CSS's reach) - only the closed-
 * state trigger is themed. If a future page genuinely needs a fully
 * custom-styled option list (e.g. options with icons/rich content) or
 * true multi-select-with-chips, that is a deliberately separate,
 * heavier component to build then, not a silent expansion of this one -
 * named here so it isn't mistaken for an oversight.
 *
 * Native `multiple` attribute is passed straight through
 * (SelectHTMLAttributes already includes it) rather than reimplemented -
 * it works, it just renders as a native multi-row list box rather than a
 * chip-style multi-select. Same "real but simplified, not fake" choice as
 * above.
 */
export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...rest },
  ref
) {
  return (
    <div className="relative">
      <select
        ref={ref}
        className={cn(
          "h-10 w-full appearance-none rounded-lg border border-border-hairline bg-surface-2 pl-3 pr-9 text-sm text-slate-100",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        {...rest}
      >
        {children}
      </select>
      {!rest.multiple && (
        <ChevronDown
          className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
          aria-hidden="true"
        />
      )}
    </div>
  );
});
