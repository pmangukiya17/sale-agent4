"""
AI Workforce - M8.4 backend addition.

This package is the ONE translation layer between whatever the AI
execution engine happens to be built on today (the M7 Workflow Engine's
WorkflowInstance/WorkflowStepInvocation tables) and the "AI Workforce"
product concept the frontend actually consumes (app.schemas.ai_workforce).

Why this exists as its own package rather than living inline in
app/api/routes/ai_workforce.py: the route and its Pydantic contracts
(AgentActivityRead / AgentActivityTraceEntryRead) are meant to be a stable
frontend-facing surface. The storage this milestone happens to read from
is not - a future milestone could add Supervisor-level activities,
multi-instance "agent sessions," or a different execution model entirely.
As long as any such change still produces the same AgentActivityRead
shape, only mapper.py needs to change; the route and the frontend do not.

Hard constraints (same discipline as app/supervisor/__init__.py's own
constraints list):
  1. Read-only. This package never writes to WorkflowInstance/
     WorkflowStepInvocation, and exposes no write endpoints.
  2. No engine imports. This package depends only on the ORM models
     (app.models.workflow_instance, .workflow_step_invocation,
     .workflow_definition) - never app.workflow_engine or app.supervisor
     directly. It reads what the engine already persisted; it never calls
     into the engine's own runtime.
  3. company_profile_id-scoped. Every query here is scoped to one
     CompanyProfile, matching every other company-scoped route in this
     codebase (get_owned_company_profile) - there is no cross-tenant
     listing capability, by design.
"""
