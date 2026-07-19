import { useState } from "react";
import { NavLink } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { useCompanies } from "../companies/CompanyContext";
import { CompanySwitcher } from "./CompanySwitcher";
import { cn } from "../design-system";
import { getNavZones, SETTINGS_NAV_ITEMS, type NavItem } from "../navigation/navConfig";

/**
 * Sidebar — M8.2. Replaces the old flat 5-item list with the grouped
 * four-zone information architecture from the M8 Design Bible, Section 2
 * (Command Center / AI Workforce / CRM / Intelligence) plus a
 * de-emphasized Settings group - the resolution the Design Bible's own
 * Section 0 item 1 argued for over the flat list several of the source
 * concepts used.
 *
 * Nav destinations themselves live in navigation/navConfig.ts, shared
 * with CommandPalette.tsx - this component is purely presentational
 * (grouping, collapse state, active-item styling) over that one shared
 * list. See navConfig.ts's own docstring for the full routing discipline
 * (existing routes preserved exactly, company-scoped items follow the
 * pre-existing Delivery-link conditional pattern, not-yet-built pages
 * route to the shared ComingSoon placeholder).
 */
function NavItemLink({ item }: { item: NavItem }) {
  const disabled = item.requiresCompany && item.to === "#";
  const Icon = item.icon;

  if (disabled) {
    return (
      <span
        title="Select a business first"
        className="flex cursor-not-allowed items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600"
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
        {item.label}
      </span>
    );
  }

  return (
    <NavLink
      to={item.to}
      end={item.to === "/"}
      className={({ isActive }) =>
        cn(
          "group flex items-center gap-3 rounded-lg border-l-2 px-3 py-2 text-sm font-medium transition-colors",
          isActive
            ? "border-accent-primary bg-surface-2 text-white"
            : "border-transparent text-slate-400 hover:border-border-hairline-strong hover:bg-surface-2 hover:text-slate-100"
        )
      }
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="flex-1 truncate">{item.label}</span>
      {item.badge && (
        <span className="shrink-0 rounded-pill border border-status-warning/30 bg-status-warning/10 px-1.5 py-0.5 text-[10px] font-medium leading-none text-status-warning">
          {item.badge}
        </span>
      )}
    </NavLink>
  );
}

function ZoneHeader({ label, open, onToggle }: { label: string; open: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className="flex w-full items-center justify-between px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-300"
    >
      {label}
      <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", !open && "-rotate-90")} aria-hidden="true" />
    </button>
  );
}

export function Sidebar() {
  const { user, logout } = useAuth();
  const { activeCompanyId } = useCompanies();
  const zones = getNavZones(activeCompanyId);
  const [collapsedZones, setCollapsedZones] = useState<Record<string, boolean>>({});

  return (
    <aside className="flex h-screen w-64 flex-col justify-between border-r border-border-hairline bg-surface-0">
      <div className="overflow-y-auto">
        <div className="flex items-center gap-2 px-5 py-6">
          {/* Placeholder mark - Design Bible Section 6/14: a final production
              logo asset does not exist yet. This gradient glyph is the
              recommended direction (faceted, blue->purple), not the final
              file - swap for the real SVG once it's produced. */}
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-accent-primary to-accent-ai text-sm font-bold text-white">
            S
          </div>
          <div>
            <h1 className="text-sm font-semibold leading-tight text-slate-100">sales-agent4</h1>
            <p className="text-[11px] leading-tight text-slate-500">AI Sales Operating System</p>
          </div>
        </div>

        <div className="mb-4">
          <CompanySwitcher />
        </div>

        <nav className="flex flex-col gap-4 px-3 pb-4">
          {zones.map((zone) => {
            const isOpen = zone.label ? collapsedZones[zone.label] !== true : true;
            return (
              <div key={zone.label ?? "standalone"}>
                {zone.label && (
                  <ZoneHeader
                    label={zone.label}
                    open={isOpen}
                    onToggle={() => setCollapsedZones((prev) => ({ ...prev, [zone.label as string]: !isOpen }))}
                  />
                )}
                {isOpen && (
                  <div className="flex flex-col gap-0.5">
                    {zone.items.map((item) => (
                      <NavItemLink key={item.label} item={item} />
                    ))}
                  </div>
                )}
              </div>
            );
          })}

          {/* Settings - de-emphasized, always visible, no zone-collapse
              affordance (it's small enough that collapsing it saves
              nothing and would just be one more click). */}
          <div className="mt-2 border-t border-border-hairline pt-3">
            <div className="flex flex-col gap-0.5">
              {SETTINGS_NAV_ITEMS.map((item) => (
                <NavItemLink key={item.label} item={item} />
              ))}
            </div>
          </div>
        </nav>
      </div>

      <div className="border-t border-border-hairline px-5 py-4">
        <p className="truncate text-sm text-slate-300">{user?.email}</p>
        <button onClick={logout} className="mt-1 text-xs font-medium text-slate-500 hover:text-slate-300">
          Sign out
        </button>
      </div>
    </aside>
  );
}
