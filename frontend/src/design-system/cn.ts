/**
 * Minimal classnames helper - M8.1. Joins truthy class fragments with a
 * space, skips falsy ones (undefined/null/false/""). Deliberately not a
 * dependency (clsx/classnames): every primitive in this folder only ever
 * needs this one, small, conditional-join behavior, so adding a package
 * for it would be an unjustified dependency for what a five-line function
 * already does correctly.
 */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
