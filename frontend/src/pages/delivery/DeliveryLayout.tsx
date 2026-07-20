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
 *
 * M8.7 Phase E2: restyled to the dark design-system tokens. The tab bar
 * itself stays hand-rolled NavLink (not the design-system Tabs primitive)
 * because these tabs are routes with their own URLs and an <Outlet/> -
 * Tabs.tsx is deliberately state-only (Design Bible's own Command Center
 * use case), so reusing it here would mean losing real URLs for each tab.
 * The visual treatment (border-b-2, accent-primary when active) matches
 * Tabs.tsx's own styling so the two "look" like one system even though
 * they're two different components for two different jobs.
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

      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Delivery</h1>
      <p className="mb-6 text-body text-slate-400">
        Connect mailboxes, configure sending identities, and send approved outreach on a human-like schedule.
      </p>

      <div className="mb-6 flex gap-1 border-b border-border-hairline">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={`/businesses/${companyId}/delivery/${tab.to}`}
            className={({ isActive }) =>
              `border-b-2 px-4 py-2 text-sm font-medium ${
                isActive ? "border-accent-primary text-slate-100" : "border-transparent text-slate-500 hover:text-slate-300"
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
