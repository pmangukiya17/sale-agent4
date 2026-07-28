import { PlaceholderNotice } from "../../design-system";
import { useProviders } from "../../ai-gateway/hooks/useProviders";
import { ProviderCard } from "../../ai-gateway/components/ProviderCard";

/**
 * AIGatewayProviders — /ai-gateway/providers. Grid of all 6 providers from
 * `useProviders()`. The set is fixed and known (mirrors the real
 * PROVIDER_CLIENT_REGISTRY per the approved architecture doc, Section
 * 4.2) so there is no "empty" case to design for beyond the loading
 * state - every card always renders, configured or not.
 */
export default function AIGatewayProviders() {
  const { data: providers, isLoading, error } = useProviders();

  if (error) {
    return <PlaceholderNotice kind="no-data" reason={error} />;
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {isLoading
        ? Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-40 animate-pulse rounded-card border border-border-hairline bg-surface-1" />
          ))
        : providers.map((provider) => <ProviderCard key={provider.key} provider={provider} />)}
    </div>
  );
}
