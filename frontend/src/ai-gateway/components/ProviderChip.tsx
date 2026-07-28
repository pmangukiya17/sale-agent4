import { Link } from "react-router-dom";
import { cn } from "../../design-system";
import { getProviderIdentity } from "../identity/providerIdentity";
import type { ProviderKey } from "../types";

/**
 * ProviderChip — small "via {Provider}" tag, built as a standalone,
 * reusable component per the approved M8.1 scope. Reused wherever a
 * request/activity/agent needs to show which provider handled it (the
 * Activity table, ApprovalCard, ActivityDetailDrawer today; a future
 * addition to AgentCard on /ai-workforce, deliberately NOT built in this
 * milestone - see the implementation report's scope-boundary note).
 *
 * Deep-links to that provider's Detail page when `linked` is true (the
 * default) - the cross-zone thread the AI Gateway architecture doc calls
 * for (Section 1.2). Rendered as plain text (no link) when a caller
 * explicitly opts out, e.g. inside a component that is itself already a
 * link/button and cannot nest another interactive element.
 */
export function ProviderChip({
  providerKey,
  linked = true,
  className,
}: {
  providerKey: ProviderKey;
  linked?: boolean;
  className?: string;
}) {
  const identity = getProviderIdentity(providerKey);
  const Icon = identity.icon;

  const content = (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium text-slate-300", className)}>
      <Icon className="h-3 w-3 shrink-0" style={{ color: identity.dotHex }} aria-hidden="true" />
      <span className="truncate">{identity.label}</span>
    </span>
  );

  if (!linked) return content;

  return (
    <Link to={`/ai-gateway/providers/${identity.key}`} className="inline-flex hover:text-slate-100" onClick={(e) => e.stopPropagation()}>
      {content}
    </Link>
  );
}
