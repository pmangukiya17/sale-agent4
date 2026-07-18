import { NavLink, Outlet } from "react-router-dom";
import { useParams } from "react-router-dom";
import { Breadcrumbs } from "../../components/Breadcrumbs";
import DeliveryOnboarding from "./DeliveryOnboarding";

/**
 * Tabbed shell for the Delivery module (Campaigns / Sending Profiles /
 * Connections) - a single top-level Sidebar entry per the explicit
 * refinement over the original three-separate-entries plan, so future
 * operational modules (Analytics, Conversations, Automation, Inbox)
 * don't each need their own Sidebar slot. Campaign DETAIL
 * (delivery/campaigns/:campaignId) is deliberately its own separate page
 * outside this tab shell, not a fourth tab - same drill-down precedent
 * ProspectOutreach.tsx already follows relative to Prospects.tsx, so a
 * single-item detail view never has to fight a tab bar that has nothing
 * meaningful to highlight for it.
 */

const TABS = [
  { to: "campaigns", label: "Campaigns" },
  { to: "sending-profiles", label: "Sending Profiles" },
  { to: "connections", label: "Connections" },
];

export default function DeliveryLayout() {
  const { companyId } = useParams();

  return (
    <div>
      <Breadcrumbs items={[{ label: "Businesses", to: "/businesses" }, { label: "Delivery" }]} />

      <h2 className="mb-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">Delivery</h2>
      <p className="mb-6 text-sm text-slate-500 dark:text-slate-400">
        Connect mailboxes, configure sending identities, and send approved outreach on a human-like schedule.
      </p>

      <div className="mb-6 flex gap-1 border-b border-slate-200 dark:border-slate-700">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={`/businesses/${companyId}/delivery/${tab.to}`}
            className={({ isActive }) =>
              `border-b-2 px-4 py-2 text-sm font-medium ${
                isActive
                  ? "border-slate-900 text-slate-900 dark:border-indigo-500 dark:text-indigo-400"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </div>

      <DeliveryOnboarding />

      <Outlet />
    </div>
  );
}
