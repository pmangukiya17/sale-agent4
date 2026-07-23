"""
Opportunity domain - Track C3 (dashboard-capabilities-architecture-plan.md,
Section 1). Mirrors app.crm_automation's package shape: a pure
state_machine.py (zero DB access, deterministic, unit-testable with no
fixtures) and a service.py (the only module that writes
Opportunity/OpportunityStageHistory rows - app/api/routes/opportunities.py
is the only caller).

Opportunity is a plain, deterministic system-of-record - the same
category as Task, not a new AI engine alongside Discovery/Research/
Personalization/Outreach. No background worker, no AI content-generation
call anywhere in this package for this initial slice; see Section 1.6/1.7
of the architecture doc for where a future AI-driven nudge would plug in
without redesigning this schema.
"""
