import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react";
import { cn } from "./cn";

/**
 * Table — M8.7 Phase D primitive, Design Bible Section 4.6 ("Tables —
 * dense by default (Bloomberg-influenced), row hover = surface-2,
 * sortable column headers, sticky header on scroll, status/badge cells
 * use the semantic status colors from 4.1").
 *
 * Generic over the row type `T` so every List-template page (Section 9)
 * shares this ONE table shell rather than each page hand-rolling its own
 * <table>/<thead>/<tbody> markup - the Design Debt Budget's "one table
 * system" requirement (Section 10.1) made concrete. A column's `render`
 * returns arbitrary ReactNode, so a status/badge cell is just a caller
 * rendering a `Badge`/`StatusIndicator` inside `render` - Table itself
 * doesn't need to know about status vocabulary at all, it only owns the
 * grid/sort/hover mechanics.
 *
 * Sorting is client-side only, over whatever `rows` the caller already
 * fetched - this component never fetches data itself (same "no business
 * logic in presentation components" rule KpiCard's own docstring states).
 * A column opts in via `sortable` + a `sortValue` accessor; clicking its
 * header cycles asc -> desc -> (a different column resets to asc).
 */
export interface TableColumn<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  sortable?: boolean;
  /** Required when `sortable` is true - the comparable value to sort by,
   * independent of whatever ReactNode `render` produces for display. */
  sortValue?: (row: T) => string | number;
  align?: "left" | "right" | "center";
  widthClassName?: string;
}

export interface TableProps<T> {
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  isLoading?: boolean;
  emptyMessage?: string;
  onRowClick?: (row: T) => void;
  className?: string;
}

type SortState = { key: string; direction: "asc" | "desc" } | null;

const ALIGN_CLASSES: Record<NonNullable<TableColumn<unknown>["align"]>, string> = {
  left: "text-left",
  right: "text-right",
  center: "text-center",
};

export function Table<T>({ columns, rows, rowKey, isLoading = false, emptyMessage = "No data yet.", onRowClick, className }: TableProps<T>) {
  const [sort, setSort] = useState<SortState>(null);

  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    const column = columns.find((c) => c.key === sort.key);
    if (!column?.sortValue) return rows;
    const sortValue = column.sortValue;
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = sortValue(a);
      const bv = sortValue(b);
      const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
      return sort.direction === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [rows, sort, columns]);

  function toggleSort(column: TableColumn<T>) {
    if (!column.sortable) return;
    setSort((prev) => {
      if (prev?.key !== column.key) return { key: column.key, direction: "asc" };
      if (prev.direction === "asc") return { key: column.key, direction: "desc" };
      return null;
    });
  }

  return (
    <div className={cn("overflow-auto rounded-card border border-border-hairline", className)}>
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-surface-1">
          <tr>
            {columns.map((column) => {
              const isSorted = sort?.key === column.key;
              const SortIcon = isSorted ? (sort!.direction === "asc" ? ChevronUp : ChevronDown) : ChevronsUpDown;
              return (
                <th
                  key={column.key}
                  className={cn(
                    "border-b border-border-hairline px-3 py-2 text-xs font-medium uppercase tracking-wide text-slate-500",
                    ALIGN_CLASSES[column.align ?? "left"],
                    column.widthClassName,
                    column.sortable && "cursor-pointer select-none hover:text-slate-300"
                  )}
                  onClick={() => toggleSort(column)}
                  aria-sort={isSorted ? (sort!.direction === "asc" ? "ascending" : "descending") : undefined}
                >
                  <span className="inline-flex items-center gap-1">
                    {column.header}
                    {column.sortable && <SortIcon className={cn("h-3 w-3", isSorted ? "text-accent-primary" : "text-slate-600")} aria-hidden="true" />}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-6 text-center text-xs text-slate-500">
                Loading…
              </td>
            </tr>
          ) : sortedRows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-6 text-center text-xs text-slate-500">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            sortedRows.map((row) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={cn("border-b border-border-hairline last:border-0 hover:bg-surface-2", onRowClick && "cursor-pointer")}
              >
                {columns.map((column) => (
                  <td key={column.key} className={cn("px-3 py-2 text-slate-200", ALIGN_CLASSES[column.align ?? "left"])}>
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
