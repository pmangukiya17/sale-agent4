import { createContext, useContext, useMemo } from "react";
import type { ReactNode } from "react";
import { apiClient } from "../../api/client";
import type { GatewayDataProvider } from "./GatewayDataProvider";
import { ApiGatewayProvider } from "./ApiGatewayProvider";

/**
 * GatewayDataProviderContext — supplies the active `GatewayDataProvider`
 * implementation to every AI Gateway hook.
 *
 * M8.2 (AI Gateway Backend Integration): now instantiates
 * `ApiGatewayProvider` (the real backend, via the same `apiClient` every
 * other real hook in this app already uses) instead of
 * `MockGatewayProvider` - exactly the one-line change M8.1's own version
 * of this file predicted, and the reason nothing else in ai-gateway/
 * needed to change: every hook/page/component depends on the
 * `GatewayDataProvider` interface, never on which concrete class
 * implements it. `MockGatewayProvider` is kept in the codebase (unused
 * here) as an offline-dev fixture, not deleted.
 *
 * Mounted by `AIGatewayLayout`, scoped to the AI Gateway route subtree
 * only - this data has no reason to be instantiated for the rest of the
 * app (unlike ToastProvider/AuthProvider/CompanyProvider in main.tsx,
 * which every route needs), so it stays out of the app-root provider tree.
 */
const GatewayDataProviderContext = createContext<GatewayDataProvider | null>(null);

export function GatewayDataProviderProvider({ children }: { children: ReactNode }) {
  // useMemo so the same provider instance persists across re-renders of
  // the layout, rather than being reconstructed on every render.
  const provider = useMemo<GatewayDataProvider>(() => new ApiGatewayProvider(apiClient), []);
  return <GatewayDataProviderContext.Provider value={provider}>{children}</GatewayDataProviderContext.Provider>;
}

export function useGatewayDataProvider(): GatewayDataProvider {
  const ctx = useContext(GatewayDataProviderContext);
  if (!ctx) {
    throw new Error("useGatewayDataProvider must be used within a GatewayDataProviderProvider (see AIGatewayLayout.tsx)");
  }
  return ctx;
}
