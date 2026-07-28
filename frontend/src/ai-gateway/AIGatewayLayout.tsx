import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { GatewayDataProviderProvider } from "./providers/GatewayDataProviderContext";
import { AI_GATEWAY_PAGES, findActivePageMeta } from "./pageMeta";

/**
 * AIGatewayLayout — AI Gateway UI Foundation (M8.1).
 *
 * Follows DeliveryLayout's philosophy (breadcrumb + heading + a routed
 * cross-page nav strip + <Outlet/>), not its exact shape: DeliveryLayout's
 * three tabs are three views of one concept ("Delivery"), so one static
 * title covers all of them. The AI Gateway's 8 destinations are each their
 * own distinct page (Overview, Providers, Routing...), so this layout
 * derives its title/subtitle from the CURRENT route via `pageMeta.ts`'s
 * shared config instead of hardcoding one - the one deliberate departure
 * from the Delivery precedent, and the reason no individual AI Gateway
 * page component repeats its own title/subtitle (avoids the "duplicate
 * UI" this milestone's quality bar explicitly warns against).
 *
 * Uses hand-rolled `NavLink`s for the page strip, not the design-system
 * `Tabs` primitive - identical reasoning to DeliveryLayout's own
 * docstring: these are real routes with real URLs, and `Tabs` is
 * deliberately state-only.
 *
 * Mounts `GatewayDataProviderProvider` here (not in main.tsx) so the mock
 * data layer is scoped to this route subtree only - see that provider's
 * own docstring for why.
 */
export function AIGatewayLayout() {
  const location = useLocation();
  const active = findActivePageMeta(location.pathname);

  return (
    <GatewayDataProviderProvider>
      <div>
        <Breadcrumbs items={[{ label: "AI Gateway", to: "/ai-gateway" }, { label: active.label }]} />

        <h1 className="mb-1 text-h1 font-semibold text-slate-100">{active.title}</h1>
        <p className="mb-6 text-body text-slate-400">{active.subtitle}</p>

        <div className="mb-6 flex flex-wrap gap-1 border-b border-border-hairline">
          {AI_GATEWAY_PAGES.map((page) => (
            <NavLink
              key={page.to}
              to={page.to}
              end={page.to === "/ai-gateway"}
              className={({ isActive }) =>
                `border-b-2 px-4 py-2 text-sm font-medium ${
                  isActive ? "border-accent-primary text-slate-100" : "border-transparent text-slate-500 hover:text-slate-300"
                }`
              }
            >
              {page.label}
            </NavLink>
          ))}
        </div>

        <Outlet />
      </div>
    </GatewayDataProviderProvider>
  );
}
