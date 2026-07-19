"""
Supervisor / Orchestrator Layer - M7.3. Sits between Workflow Action and
Agent Runtime:

    Workflow Engine -> Workflow Action -> Supervisor -> Agent Runtime ->
    Prompt Builder -> AI Gateway -> Provider Router -> Claude/OpenAI/Gemini

Four hard constraints this whole package is built to make structurally
true, not just documented (the fourth added in M7.4 - see below):

  1. Supervisor must never bypass AgentRuntime. Enforced by what a
     concrete Supervisor implementation's decide_next() method can even
     reach: it receives a SupervisionState (a read-only value) and
     returns a SupervisorDecision (a plain data value naming agent_keys)
     - it never receives a reference to AgentRuntime, AIGateway,
     PromptBuilder, or any Agent instance. Only SupervisorRuntime
     (runtime.py) ever calls AgentRuntime.run_with_metadata() - and it
     is the ONLY thing in this package that does.

  2. Agents must never call each other. Unchanged from M7.2 - an Agent's
     build_context()/interpret() signatures have no reachable path to
     AgentRuntime, another Agent, or anything in this package. Concrete
     Agent implementations must never import app.supervisor.

  3. Supervisor coordinates execution only. A Supervisor implementation's
     decide_next() reads history and returns a decision - it never
     itself builds a PromptContext, never receives a raw GatewayResponse,
     never touches ExecutionPolicy/provider/model. It operates at the
     same abstraction level a Workflow Action already operates at when
     reading an ActionOutput.result: consuming already-interpreted
     results, not doing AI work itself.

  4. [M7.4] Supervisors must never invoke other Supervisors directly.
     Cross-specialization composition (e.g. a Research plan handing off
     to an Outbound plan) happens EXCLUSIVELY through the Workflow
     Engine's own step_graph transitions chaining multiple
     SupervisorInvocationAction-driven steps (Workflow -> Supervisor A ->
     Workflow -> Supervisor B), never via one Supervisor's decide_next()
     calling into SUPERVISOR_REGISTRY/SupervisorRuntime itself. Enforced
     the same way constraint 1 is: decide_next()'s own reachable
     signature (state in, SupervisorDecision out) has no path to
     SUPERVISOR_REGISTRY or SupervisorRuntime at all - a concrete
     Supervisor implementation would have to explicitly import
     app.supervisor.registry/app.supervisor.runtime itself, against this
     package's own convention, to violate this. A nested "one Supervisor
     runs a sub-plan" primitive (sketched during the M7.4 architecture
     review as RUN_SUB_PLAN, with a recursion guard and a
     parent_execution_id field) was deliberately designed but NOT built -
     explicitly deferred pending a genuine business need for it, per the
     M7.4 architecture review's own explicit confirmation.

Self-registration for concrete Supervisor implementations
(app.supervisor.registry.SUPERVISOR_REGISTRY) mirrors
ACTION_REGISTRY/AGENT_REGISTRY exactly, for the identical reason: this
package must never import a concrete Supervisor implementation at module
level, so the import arrow always points from a domain-authored
Supervisor into this package, never the reverse.

Scope note, matching the M7.2 precedent: M7.3 shipped this infrastructure
with ZERO concrete Supervisor implementations (no Planning Agent, no
Research-then-Email plan, nothing wired into a real WorkflowDefinition
trigger). M7.4 adds the Workflow Action bridge itself
(app/workflow_actions/supervisor_invocation_action.py -
SupervisorInvocationAction) plus code-level plan versioning
(registry.py's DEFAULT_SUPERVISOR_VERSION), but STILL ships zero concrete
Supervisor implementations and wires nothing into a real
WorkflowDefinition trigger - that remains explicitly future work, the
same "infrastructure first, a real business plan later" scope discipline
applied a second time. Also still out of scope, named explicitly rather
than silently skipped: persisting SupervisionState to its OWN database
table, independent of any one WorkflowInstance's context (app.supervisor.
serialization's state_to_dict()/state_from_dict(), M7.4, only serializes
INTO a WorkflowInstance's existing opaque context column - no new
migration exists); genuine event-driven resumption of a WAIT(EVENT)
decision (M7.4's SupervisorInvocationAction resumes WAIT decisions via
time-based RETRY polling only - see that module's own docstring for the
full, disclosed reasoning and its real limits); nested Supervisor-to-
Supervisor composition (constraint 4 above).
"""
