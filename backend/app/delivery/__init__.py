"""
M5 Outreach Delivery Engine: delivers already-approved OutreachDrafts
through connected email providers at the right time, using intelligent
scheduling and pacing. A completely separate bounded context from M4
(Outreach) - see docs/architecture/future-milestones.md for the boundary.
Outreach must never know how delivery works; this package only ever reads
OutreachDraft/Prospect/ProspectContact, never writes to them.

Unlike M1-M4, this package has two distinct orchestration concerns
instead of one: request-time (campaign_service/queue_service/
connection_service, invoked synchronously from API routes) and worker-time
(dispatch_service/worker.py, invoked on the worker's own clock, independent
of any HTTP request). See delivery_campaign.py's model docstring for why
this isn't a Request->Job->Run pipeline like M1-M4.
"""
