/**
 * Single source of truth for the AI Gateway zone's own page metadata -
 * mirrors navConfig.ts's own "one shared list, no drift" rationale, but
 * scoped to this zone: `AIGatewayLayout` reads this to render the
 * breadcrumb/title/subtitle/cross-page nav strip, so no individual page
 * component needs to repeat its own title/subtitle (the "no duplicate
 * UI" quality bar the approved M8.1 scope calls out).
 *
 * The `/ai-gateway/providers/:providerKey` detail route deliberately has
 * no entry here - it's not one of the 8 destinations a user navigates
 * between, it's a drill-down from Providers. AIGatewayLayout falls back
 * to matching by path-prefix, so the nav strip highlights "Providers"
 * while on a provider's detail page, and the detail page itself renders
 * its own more specific sub-header (provider name) inside the outlet.
 */
export interface AIGatewayPageMeta {
  to: string;
  label: string;
  title: string;
  subtitle: string;
}

export const AI_GATEWAY_PAGES: AIGatewayPageMeta[] = [
  {
    to: "/ai-gateway",
    label: "Overview",
    title: "AI Overview",
    subtitle: "Provider-neutral routing, cost, and approval for every AI feature.",
  },
  {
    to: "/ai-gateway/providers",
    label: "Providers",
    title: "AI Providers",
    subtitle: "Every provider the Gateway can route to, and its current standing.",
  },
  {
    to: "/ai-gateway/routing",
    label: "Routing",
    title: "Gateway Routing",
    subtitle: "How the last request for each capability was actually decided.",
  },
  {
    to: "/ai-gateway/activity",
    label: "Activity",
    title: "AI Activity",
    subtitle: "Every AI Gateway request, in order.",
  },
  {
    to: "/ai-gateway/usage",
    label: "Usage & Cost",
    title: "AI Usage",
    subtitle: "Cost, tokens, and provider mix over time.",
  },
  {
    to: "/ai-gateway/approvals",
    label: "Approvals",
    title: "Premium Approval Center",
    subtitle: "Requests that need a human decision before spending premium budget.",
  },
  {
    to: "/ai-gateway/health",
    label: "Health",
    title: "Gateway Health",
    subtitle: "Provider health, failover events, and routing diagnostics.",
  },
  {
    to: "/ai-gateway/settings",
    label: "Settings",
    title: "AI Settings",
    subtitle: "Routing mode, provider priority, and cost limits.",
  },
];

export function findActivePageMeta(pathname: string): AIGatewayPageMeta {
  const exact = AI_GATEWAY_PAGES.find((p) => p.to === pathname);
  if (exact) return exact;
  // Fallback for drill-down routes (e.g. /ai-gateway/providers/:providerKey)
  // - longest matching prefix wins so /ai-gateway itself doesn't
  // accidentally match every nested path.
  const prefixMatches = AI_GATEWAY_PAGES.filter((p) => p.to !== "/ai-gateway" && pathname.startsWith(p.to));
  if (prefixMatches.length > 0) return prefixMatches[0];
  return AI_GATEWAY_PAGES[0];
}
