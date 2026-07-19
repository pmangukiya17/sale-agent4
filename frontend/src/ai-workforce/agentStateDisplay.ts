import type { StatusKind } from "../design-system";
import type { AgentActivityState } from "./useAgentActivities";

/**
 * Presentation-layer verb mapping - Design Bible Section 5's own explicit
 * rule: "the extra specificity ('Researching' vs just 'Running') comes
 * from WHICH AGENT is executing... resolved by a presentation-layer
 * mapping, not a backend change." This is that mapping, and ONLY that
 * mapping - it never invents a state the backend doesn't actually report
 * (see this file's own inline notes on what's deliberately NOT done here).
 *
 * Inputs are real backend facts (AgentActivity.state, .workflow_key,
 * .current_action_key) - the verb choice is cosmetic, the underlying
 * truth (queued/running/waiting/paused/completed/failed/cancelled) is
 * never altered or hidden by it.
 */
export interface AgentStateDisplay {
  label: string;
  statusKind: StatusKind;
}

const RUNNING_VERB_RULES: { pattern: RegExp; verb: string }[] = [
  { pattern: /research/i, verb: "Researching" },
  { pattern: /personaliz/i, verb: "Writing" },
  { pattern: /outreach/i, verb: "Writing" },
  { pattern: /discover/i, verb: "Scoring" },
  { pattern: /qualif/i, verb: "Scoring" },
  { pattern: /repl(y|ies)|conversation/i, verb: "Reading" },
];

function runningVerb(workflowKey: string, actionKey: string | null): string {
  const haystack = `${workflowKey} ${actionKey ?? ""}`;
  const match = RUNNING_VERB_RULES.find((rule) => rule.pattern.test(haystack));
  // "Running" is the honest generic fallback the Design Bible itself names
  // for exactly this case - not every workflow_key maps to a named verb,
  // and guessing one would be exactly the kind of fabrication this
  // project avoids everywhere else.
  return match?.verb ?? "Running";
}

export function describeAgentState(
  state: AgentActivityState,
  workflowKey: string,
  actionKey: string | null
): AgentStateDisplay {
  switch (state) {
    case "queued":
      // Deliberately "Queued", not the Design Bible's "Idle" - Idle means
      // "no current invocation at all" (wouldn't appear in this roster);
      // Queued means real work IS assigned, just not started. Using the
      // more precise word instead of force-fitting the illustrative list.
      return { label: "Queued", statusKind: "idle" };
    case "running":
      return { label: runningVerb(workflowKey, actionKey), statusKind: "active" };
    case "waiting":
      // Not split into "Reviewing" (human-approval waits) - that would
      // require reading the Supervisor's own opaque SupervisionState
      // (resume_trigger type) out of WorkflowInstance.context, which the
      // AI Workforce mapper deliberately never does (see its own
      // docstring's "no engine imports" constraint). Disclosed gap, not
      // silently designed around.
      return { label: "Waiting", statusKind: "waiting" };
    case "paused":
      // Schema-real, currently dormant - see AgentActivityState's own
      // docstring. StatusIndicator already renders "paused" as an
      // outline-only, non-pulsing dot for exactly this reason.
      return { label: "Paused", statusKind: "paused" };
    case "completed":
      return { label: "Completed", statusKind: "success" };
    case "failed":
      return { label: "Failed", statusKind: "failed" };
    case "cancelled":
      return { label: "Cancelled", statusKind: "idle" };
  }
}
