"""
AI Agent Runtime - M7.2. The top of the AI Execution Platform stack:

    Workflow Action -> AI Agent Runtime -> Prompt Builder -> AI Gateway -> Provider Router

This package owns three things: the Agent contract (base.py), a
self-registration registry for concrete Agent implementations
(registry.py, mirroring app.workflow_engine.actions.registry's own
domain-registers-itself pattern - this package must never import a
concrete Agent implementation at module level, same reasoning as
ACTION_REGISTRY), and the orchestration that ties an Agent to
PromptBuilder/AIGateway (runtime.py).

Scope note: M7.2 shipped this infrastructure with ZERO concrete Agent
implementations and zero Workflow Action wiring - per that milestone's
own approved scope ("AI Agent Runtime, AI Gateway" only). M2 Phase 3
ships the first one, ResearchAnalysisAgent - deliberately living in
app.research.analysis (the Research domain's own package), NOT in this
package, mirroring how concrete Workflow Actions live in
app.workflow_actions rather than in app.workflow_engine.actions itself.
This package stays generic, domain-agnostic infrastructure only - see
registry.py's own docstring for why it must never import a concrete
Agent implementation at module level.
"""
