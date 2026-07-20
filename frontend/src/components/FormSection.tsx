import type { ReactNode } from "react";

/**
 * FormSection / Field — shared multi-field form layout primitive (grid of
 * labeled fields, two columns on larger screens), predating the M8.1
 * design system. Restyled to the permanent dark design-system tokens in
 * M8.7 Phase E rather than left on its OS-conditional `dark:` classes:
 * this app has one dark theme by design (Design Bible Section 3), it
 * isn't a light/dark toggle - Tailwind's default `dark:` strategy follows
 * the OS's `prefers-color-scheme`, which meant a user on a light-OS
 * profile would have seen this section render light while the rest of
 * the shell stayed dark. Kept as a distinct component from Card (Card is
 * a content container; this is specifically a label+field grid), per
 * Design Debt Budget - the alternative was inlining this same layout on
 * every settings/edit page, which is the pattern this component exists to
 * prevent.
 */
export function FormSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <div className="mb-6 rounded-card border border-border-hairline bg-surface-1 p-6">
      <h3 className="text-base font-semibold text-slate-100">{title}</h3>
      {description && <p className="mt-1 text-sm text-slate-400">{description}</p>}
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">{children}</div>
    </div>
  );
}

export function Field({
  label,
  full,
  children,
}: {
  label: string;
  full?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={full ? "sm:col-span-2" : undefined}>
      <label className="mb-1 block text-sm font-medium text-slate-300">{label}</label>
      {children}
    </div>
  );
}

// Retained only for any not-yet-migrated consumer's native <textarea>
// (the design system doesn't have a Textarea primitive yet - out of
// scope to add speculatively here, per Section 10.1's Design Debt
// Budget: only build a primitive when a real consumer needs it). Inputs
// and selects should use the design-system Input/Select components
// instead of this class directly wherever both exist.
export const inputClass =
  "w-full rounded-lg border border-border-hairline bg-surface-2 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0";
