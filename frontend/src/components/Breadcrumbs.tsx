import { Link } from "react-router-dom";

export interface BreadcrumbItem {
  label: string;
  /** Omit on the last item - the current page is shown as plain text, not a link. */
  to?: string;
}

/**
 * Shared page-navigation trail, used across every major workflow page
 * instead of one-off "Back to X" links. Deliberately built as an ordered
 * list of {label, to} segments rather than a single "go back" affordance,
 * so it can grow into fuller breadcrumbs later (e.g. inserting the active
 * business's name as its own segment) without changing how any page calls
 * it - only the `items` array a given page passes in would need to change.
 */
export function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-4 flex flex-wrap items-center gap-1.5 text-sm">
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <span className="text-slate-700">/</span>}
          {item.to ? (
            <Link to={item.to} className="text-slate-500 hover:text-slate-200">
              {item.label}
            </Link>
          ) : (
            <span className="font-medium text-slate-200">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
