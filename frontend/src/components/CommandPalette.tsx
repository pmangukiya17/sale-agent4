import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { useCompanies } from "../companies/CompanyContext";
import { getNavZones, SETTINGS_NAV_ITEMS, type NavItem } from "../navigation/navConfig";
import { cn } from "../design-system";

/**
 * Command Palette — M8.2, Design Bible Section 3. Keyboard-first
 * (Cmd/Ctrl+K), in the Cursor/Linear tradition. Reads from the SAME
 * navigation/navConfig.ts list the Sidebar renders, so it can never list
 * a destination the sidebar doesn't also have (or vice versa) - one
 * source of truth, two presentations.
 *
 * This is real, functional keyboard navigation (open/close, arrow-key
 * selection, Enter to navigate, Escape to close, click to navigate) -
 * not a static mock. It complements the dashboard's own persistent
 * quick-action bar (M8.3) rather than replacing it - see Design Bible
 * Section 0 item 7 for why both are kept. Disabled (company-required,
 * no active company) destinations are filtered out here entirely rather
 * than shown disabled, since a palette result a user can't act on is
 * pure noise in a list that's supposed to be fast.
 */
export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlighted, setHighlighted] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { activeCompanyId } = useCompanies();

  const allItems = useMemo<NavItem[]>(() => {
    const zones = getNavZones(activeCompanyId);
    return [...zones.flatMap((zone) => zone.items), ...SETTINGS_NAV_ITEMS].filter((item) => item.to !== "#");
  }, [activeCompanyId]);

  const results = useMemo(() => {
    if (!query.trim()) return allItems;
    const q = query.trim().toLowerCase();
    return allItems.filter((item) => item.label.toLowerCase().includes(q));
  }, [allItems, query]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const isPaletteShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
      if (isPaletteShortcut) {
        event.preventDefault();
        setOpen((prev) => !prev);
      } else if (event.key === "Escape" && open) {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setHighlighted(0);
      // Focus after the overlay actually mounts, not before.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    setHighlighted(0);
  }, [query]);

  function navigateTo(item: NavItem) {
    navigate(item.to);
    setOpen(false);
  }

  function onInputKeyDown(event: ReactKeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((prev) => Math.min(prev + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((prev) => Math.max(prev - 1, 0));
    } else if (event.key === "Enter" && results[highlighted]) {
      event.preventDefault();
      navigateTo(results[highlighted]);
    }
  }

  return (
    <>
      {/* Trigger - lives in the top command strip (TopCommandStrip.tsx),
          this component owns the overlay/behavior only, so the strip
          doesn't need to know how the palette works internally. */}
      <button
        onClick={() => setOpen(true)}
        className="flex h-9 w-64 items-center gap-2 rounded-lg border border-border-hairline bg-surface-2 px-3 text-sm text-slate-400 hover:border-border-hairline-strong"
      >
        <Search className="h-4 w-4" aria-hidden="true" />
        <span className="flex-1 text-left">Search anything…</span>
        <kbd className="rounded border border-border-hairline bg-surface-1 px-1.5 py-0.5 text-[10px] text-slate-500">⌘K</kbd>
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-[15vh]" onClick={() => setOpen(false)}>
          {/* Glass treatment is reserved for overlays per Design Bible 4.5
              - this IS one, unlike a resting dashboard card. */}
          <div
            className="w-full max-w-lg rounded-card border border-border-hairline-strong bg-surface-1/90 shadow-elevation-3 backdrop-blur-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b border-border-hairline px-4 py-3">
              <Search className="h-4 w-4 text-slate-500" aria-hidden="true" />
              <input
                ref={inputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={onInputKeyDown}
                placeholder="Search pages…"
                className="flex-1 bg-transparent text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none"
              />
              <kbd className="rounded border border-border-hairline px-1.5 py-0.5 text-[10px] text-slate-500">Esc</kbd>
            </div>
            <div className="max-h-80 overflow-y-auto p-2">
              {results.length === 0 && <p className="px-3 py-6 text-center text-sm text-slate-500">No matches.</p>}
              {results.map((item, index) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.label}
                    onMouseEnter={() => setHighlighted(index)}
                    onClick={() => navigateTo(item)}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm",
                      index === highlighted ? "bg-surface-2 text-white" : "text-slate-300"
                    )}
                  >
                    <Icon className="h-4 w-4 text-slate-500" aria-hidden="true" />
                    <span className="flex-1">{item.label}</span>
                    {item.badge && (
                      <span className="shrink-0 rounded-pill border border-status-warning/30 bg-status-warning/10 px-1.5 py-0.5 text-[10px] font-medium leading-none text-status-warning">
                        {item.badge}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
