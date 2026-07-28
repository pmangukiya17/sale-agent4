import type {
  ActivityLogEntry,
  ApprovalRequest,
  ConnectionTestResult,
  GatewayOverview,
  GatewaySettings,
  ModelRole,
  ModelRoleWrite,
  ProviderConfig,
  ProviderConfigAuditEntry,
  ProviderConfigWrite,
  ProviderKey,
  ProviderSummary,
  RoutingDecision,
  RoutingSimulationRequestInput,
  RoutingSimulationResult,
} from "../types";

/**
 * GatewayDataProvider — the abstraction every AI Gateway hook is written
 * against, per the approved M8.1 scope ("hooks should consume the provider
 * abstraction," not read fixtures directly).
 *
 * Today the only implementation is `MockGatewayProvider` (static fixtures,
 * simulated network delay). The intended future implementation is an
 * `ApiGatewayProvider` that calls the real backend (app/ai_gateway,
 * app/ai_workforce) via `apiClient` - see api/client.ts and
 * ai-workforce/useAgentActivities.ts for the existing precedent this would
 * follow. Swapping providers is a one-file change
 * (GatewayDataProviderContext.tsx's instantiation), not a hook/page
 * rewrite, because every hook only ever calls methods on this interface.
 *
 * Every method returns a Promise so the mock implementation's simulated
 * async delay and a real implementation's actual network request are
 * indistinguishable from a calling hook's point of view.
 *
 * M8.2 (AI Gateway Backend Integration): `ApiGatewayProvider` is now the
 * real, default implementation (see GatewayDataProviderContext.tsx) -
 * `MockGatewayProvider` is kept as-is (unused by default) rather than
 * deleted, since it's still a useful fixture/offline-dev fallback and
 * every hook depends on this interface, never on which concrete class is
 * behind it. `getSettings()` is an ADDITIVE method on this interface (M8.2)
 * - every pre-existing method's signature is completely unchanged, so no
 * M8.1 hook needed to change its own contract for this milestone.
 */
export interface GatewayDataProvider {
  getOverview(): Promise<GatewayOverview>;
  listProviders(): Promise<ProviderSummary[]>;
  getProvider(key: ProviderKey): Promise<ProviderSummary | null>;
  listActivity(): Promise<ActivityLogEntry[]>;
  listApprovals(): Promise<ApprovalRequest[]>;
  listRoutingDecisions(): Promise<RoutingDecision[]>;
  getSettings(): Promise<GatewaySettings>;
  /** M8.3 Step 2 (Provider Management) additions - see ../types.ts's own
   * docstring for each shape. Admin-only server-side (403 for a
   * non-admin caller) - callers should gate rendering the write form on
   * the caller's own role (useAuth()'s user.role), but every method here
   * still just propagates whatever the backend returns/throws; this
   * interface itself has no notion of roles. */
  getProviderConfig(key: ProviderKey): Promise<ProviderConfig | null>;
  saveProviderConfig(key: ProviderKey, patch: ProviderConfigWrite): Promise<ProviderConfig>;
  listProviderConfigAudit(key: ProviderKey, limit?: number): Promise<ProviderConfigAuditEntry[]>;
  testConnection(key: ProviderKey): Promise<ConnectionTestResult>;
  /** M8.3 Step 3 (Model Role Management) additions. Admin-only
   * server-side (403 for a non-admin caller), same convention as the
   * Step 2 methods above. Local-tier only - see ModelRole's own
   * docstring in ../types.ts. */
  listModelRoles(): Promise<ModelRole[]>;
  saveModelRole(roleName: string, patch: ModelRoleWrite): Promise<ModelRole>;
  deleteModelRole(roleName: string): Promise<void>;
  /** M8.3 Step 4 (Routing Simulator) addition. READ-ONLY - never mutates
   * any setting, never attempts a real provider call. See
   * RoutingSimulationResult's own docstring in ../types.ts. */
  simulateRouting(request: RoutingSimulationRequestInput): Promise<RoutingSimulationResult>;
}
