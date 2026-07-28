import { Card, PlaceholderNotice } from "../../design-system";
import { useRouting } from "../../ai-gateway/hooks/useRouting";
import { RoutingChainVisualizer } from "../../ai-gateway/components/RoutingChainVisualizer";

/**
 * AIGatewayRouting — /ai-gateway/routing. Replays the last real (mock)
 * routing decision per capability using `RoutingChainVisualizer`, per the
 * approved architecture doc's honesty principle: this shows what actually
 * happened for these requests, not a generic marketing diagram of what
 * the Gateway is capable of.
 */
export default function AIGatewayRouting() {
  const { data: decisions, isLoading, error } = useRouting();

  if (error) return <PlaceholderNotice kind="no-data" reason={error} />;

  return (
    <div className="flex flex-col gap-4">
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : decisions.length === 0 ? (
        <PlaceholderNotice kind="no-data" reason="No requests yet — the routing diagram will populate once one runs." />
      ) : (
        decisions.map((decision) => (
          <Card key={decision.id} className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-100">{decision.capability}</h2>
              <span className="text-xs text-slate-500">{new Date(decision.timestamp).toLocaleTimeString()}</span>
            </div>
            <RoutingChainVisualizer nodes={decision.nodes} />
          </Card>
        ))
      )}
    </div>
  );
}
