"""
M6 Reply Intelligence - its own package, separate from app/delivery/,
per the master plan's "M6 owns its own tables, its own background
worker(s), its own API routes" principle (see
docs/architecture/m6-reply-intelligence-plan.md). M6.2 is the first phase
to add code here: mailbox synchronization only (normalize.py,
sync_worker.py) - no conversation building, no reply intelligence, no AI,
no UI. Models (Conversation/EmailMessage/ConversationParticipant/
MailboxSyncState/Attachment) still live in app/models/, matching this
project's existing "models always live in app/models/, only engine/
service code gets its own per-milestone package" convention (see e.g.
app/discovery/, app/research/, app/personalization/, app/outreach/,
app/delivery/).
"""
