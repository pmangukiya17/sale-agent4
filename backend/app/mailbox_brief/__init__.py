"""
Mailbox Brief - Track C5 (dashboard-capabilities-architecture-plan.md,
Section 6). A pure PROJECTION/synthesis over already-existing CRM data
(Conversation, Recommendation, Opportunity/OpportunityStageHistory) -
per the CEO's explicit instruction, this package never creates or
duplicates business data; it only reads what Track C1-C4 already built
and reuses their own service functions (app.opportunities.service's
compute_funnel/compute_pipeline_value) rather than re-deriving that math
a second time.

Kept as its own package, separate from app/reply_intelligence/ (per-
message classification) and app/crm_automation/ (deterministic
stage-advance rules) - this is portfolio-level SYNTHESIS across multiple
domains at once, a different job from either of those, the same
Research-vs-Personalization-vs-Outreach boundary discipline this project
already applies everywhere.

Mirrors app/personalization/'s own shape: context.py assembles a bounded
read-only context, engine/ holds a pluggable synthesis-engine interface
with exactly one concrete implementation today
(DeterministicMailboxBriefEngine - no real LLM call, same explicit
"deterministic stub now, real engine later, zero schema change"
precedent app/personalization/engine/deterministic_stub.py already set),
and service.py is the only module that writes MailboxBrief rows.
"""
