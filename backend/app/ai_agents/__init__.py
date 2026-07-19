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

Scope note: M7.2 ships this infrastructure with ZERO concrete Agent
implementations and zero Workflow Action wiring - per the milestone's own
approved scope ("AI Agent Runtime, AI Gateway" only). A real Agent (and
the Workflow Action that invokes AgentRuntime.run() from within a
workflow step) is explicitly future (M7.3+) work.
"""
