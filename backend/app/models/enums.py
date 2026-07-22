import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"


class PipelineStage(str, enum.Enum):
    DISCOVERED = "discovered"
    ENRICHED = "enriched"
    VERIFIED = "verified"
    WEBSITE_ANALYZED = "website_analyzed"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"
    CONTACT_FOUND = "contact_found"
    DRAFT_GENERATED = "draft_generated"
    PENDING_APPROVAL = "pending_approval"
    SENT = "sent"
    REPLIED = "replied"
    NO_REPLY = "no_reply"
    FOLLOW_UP_1 = "follow_up_1"
    FOLLOW_UP_2 = "follow_up_2"
    FOLLOW_UP_3 = "follow_up_3"
    WON = "won"
    LOST = "lost"
    NURTURE = "nurture"


class MessageDirection(str, enum.Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class FollowUpStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    CANCELLED = "cancelled"


class ProductStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class SearchDepth(str, enum.Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class SearchFrequency(str, enum.Enum):
    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"


class DateFormat(str, enum.Enum):
    DD_MM_YYYY = "DD/MM/YYYY"
    MM_DD_YYYY = "MM/DD/YYYY"
    YYYY_MM_DD = "YYYY-MM-DD"


class TimeFormat(str, enum.Enum):
    H12 = "12h"
    H24 = "24h"


class DiscoveryJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProspectStatus(str, enum.Enum):
    NEW = "new"
    DUPLICATE_REVIEW = "duplicate_review"
    SCORED = "scored"
    QUALIFIED = "qualified"
    UNQUALIFIED = "unqualified"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class DecisionMakerLevel(str, enum.Enum):
    FINAL_DECISION_MAKER = "final_decision_maker"
    INFLUENCER = "influencer"
    GATEKEEPER = "gatekeeper"
    UNKNOWN = "unknown"


# --- M2: AI Research & Prospect Intelligence --------------------------------
# A separate status enum from DiscoveryJobStatus, even though the values
# start identical - Research is a deliberately independent domain (per the
# approved M2 design) and sharing a Postgres type would couple the two.


class ResearchJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AIAnalysisType(str, enum.Enum):
    COMPANY_PROFILE = "company_profile"
    BUYER_PROFILE = "buyer_profile"
    BUSINESS_SIGNALS = "business_signals"
    SALES_INTELLIGENCE = "sales_intelligence"


class SignalStatus(str, enum.Enum):
    NEW = "new"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"


class SignalImportance(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SignalUrgency(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IMMEDIATE = "immediate"


class RecommendationType(str, enum.Enum):
    PRODUCT_FIT = "product_fit"
    SALES_ANGLE = "sales_angle"
    TALKING_POINT = "talking_point"
    OBJECTION_HANDLING = "objection_handling"
    RISK_MITIGATION = "risk_mitigation"
    # Added in M3 - Personalization writes these when it identifies a good
    # call-to-action; kept in the SAME table/enum as M2's other recommendation
    # types rather than a new "Personalization Recommendation" concept, so
    # there is exactly one canonical "atomic tactical idea" store across
    # M2 and M3.
    CALL_TO_ACTION = "call_to_action"


class RecommendationStatus(str, enum.Enum):
    NEW = "new"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


# --- M3: AI Personalization Engine ------------------------------------------
# Personalization is a pure synthesis domain - it reads what Discovery (M1)
# and Research (M2) already produced and never re-derives facts. A separate
# status enum from ResearchJobStatus/DiscoveryJobStatus, same independent-
# domain precedent as before. No PARTIALLY_COMPLETED value here: unlike
# Discovery/Research there is no provider fan-out to partially fail - a
# single synchronous synthesis pass either completes or fails outright.


class PersonalizationJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BuyerReadinessLevel(str, enum.Enum):
    """AI prediction, recalculated every time Personalization runs - how
    receptive/ready this buyer currently seems, inferred from Signals.
    Deliberately distinct from RelationshipStage (actual sales history)."""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    READY_TO_ENGAGE = "ready_to_engage"


class RelationshipStage(str, enum.Enum):
    """Actual sales history with this buyer - lives on Prospect as a live,
    mutable field (NOT versioned/frozen like BuyerReadinessLevel). M3 only
    ever reads this value; M4-M7 are what advance it as outreach happens."""

    COLD = "cold"
    CONTACTED = "contacted"
    ENGAGED = "engaged"
    QUALIFIED = "qualified"
    NEGOTIATION = "negotiation"


class PersonalizationStrategyRank(str, enum.Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    FALLBACK = "fallback"


class CommunicationFormality(str, enum.Enum):
    CASUAL = "casual"
    NEUTRAL = "neutral"
    FORMAL = "formal"


class CommunicationIntensityLevel(str, enum.Enum):
    """Shared 3-level scale reused across directness/warmth/technical_depth/
    authority/consultative_level/urgency on CommunicationStrategy - these
    are all "how much of this trait" axes, so one enum type serves all six
    columns rather than six near-identical enums."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CommunicationLength(str, enum.Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


# --- M4: AI Outreach Generation Engine ---------------------------------------
# Outreach is a pure consumer of Personalization (M3), same "independent
# domain, own status enum" precedent as Research-vs-Discovery and
# Personalization-vs-Research. No PARTIALLY_COMPLETED value, same reasoning
# as PersonalizationJobStatus: one synchronous render pass, no provider
# fan-out to partially fail.


class PersonalizationScope(str, enum.Enum):
    """Whether a PersonalizationSnapshot's strategy read is for the whole
    account (Prospect) or one specific named stakeholder (ProspectContact).
    M3/M4 only ever produce ACCOUNT-scoped snapshots - CONTACT is added now,
    unused, so a future per-stakeholder personalization upgrade needs no
    schema change. Lives on PersonalizationSnapshot, not here for M4's own
    entities - Outreach never redefines what Personalization already owns."""

    ACCOUNT = "account"
    CONTACT = "contact"


class OutreachJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutreachDraftStatus(str, enum.Enum):
    """Per-draft-version approval lifecycle - deliberately NOT the same
    thing as Prospect.relationship_stage (account-level sales history) or
    the CRM's PipelineStage (dormant until a Prospect->Company import
    exists). SUPERSEDED is distinct from simply "not is_current": it
    records that a specific version was actively replaced by a
    regeneration, vs. one that was just never promoted."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class OutreachBlockBehavior(str, enum.Enum):
    """How a single OutreachBlock is rendered. FIXED content is copied
    verbatim (never reworded by the AI, though a channel provider may still
    reformat its presentation). AI_ASSISTED lightly personalizes existing
    wording. AI_GENERATED is written fresh from ai_guidance + the buyer's
    PersonalizationSnapshot context."""

    FIXED = "fixed"
    AI_ASSISTED = "ai_assisted"
    AI_GENERATED = "ai_generated"


# --- M5: Outreach Delivery Engine --------------------------------------------
# Delivery is a pure consumer of Outreach (M4): it reads approved
# OutreachDrafts and never writes to OutreachDraft/OutreachPlaybook/etc.
# Unlike M1-M4, Delivery is NOT a synchronous Request->Job->Run pipeline - a
# DeliveryCampaign fans out into many DeliveryQueueItems, each dispatched
# independently, later, by a background worker. provider_key (on
# SendingProfile/ProviderConnection/ProviderCredential.backend) is a plain
# string, not an enum here, for the same reason channel_key/DiscoveryProvider.key
# are strings - adding SMTP/SES/SendGrid/Mailgun (or a new credential storage
# backend) must be a code+registry change, never a migration.


class ProviderConnectionStatus(str, enum.Enum):
    """Lifecycle of one OAuth grant to a real mailbox. CONNECTED and
    DISCONNECTED are both terminal-ish "known good/known off" states;
    EXPIRED (refresh failed, likely recoverable via Reconnect) and REVOKED
    (the provider says access was explicitly withdrawn) are kept distinct
    from the more general ERROR (an ambiguous failure, e.g. an unexpected
    API error during Verify) so the UI can give an accurate reason rather
    than a generic "broken" state. A connection is never hard-deleted by
    Disconnect - the row (and its history) persists; only its
    ProviderCredential is removed."""

    CONNECTED = "connected"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class DeliveryCampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DeliveryQueueItemStatus(str, enum.Enum):
    """QUEUED: enqueued, no send time assigned yet. SCHEDULED: the
    scheduler assigned scheduled_send_at. SENDING: a worker has claimed
    this item (via SELECT...FOR UPDATE SKIP LOCKED) and is dispatching it
    right now - a transient state, not a resting one. SENT/FAILED are
    terminal. RETRY means a transient failure occurred and this item will
    be re-scheduled with an incremented attempt_count. CANCELLED can be
    reached from QUEUED/SCHEDULED/RETRY (e.g. a paused campaign, or the
    source OutreachDraft was superseded before this item was sent)."""

    QUEUED = "queued"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRY = "retry"


class DeliveryEventType(str, enum.Enum):
    """Append-only history for one DeliveryQueueItem - never overwritten,
    same discipline as OutreachEdit/OutreachRun/ProspectTimelineEvent.
    Mirrors DeliveryQueueItemStatus's values exactly (one event per state
    transition) rather than being a separate vocabulary, so "what happened"
    and "what state is it in" never drift apart."""

    QUEUED = "queued"
    SCHEDULED = "scheduled"
    STARTED = "started"
    SENT = "sent"
    RETRY = "retry"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConversationStatus(str, enum.Enum):
    """Deliberately minimal for M6.1 - two states, not a workflow. OPEN is
    the only value anything writes today (Conversation's default); nothing
    in M6.1 ever transitions a row to CLOSED, since that requires either a
    human action or a staleness/freshness computation that belongs to a
    later milestone (M6.3 correlation at the earliest, more likely M7
    follow-up automation). Resist the temptation to add STALLED/ARCHIVED/
    etc. here speculatively - see m6-reply-intelligence-plan.md's own
    walked-back Attachment/InboxSyncState/Task scoping for why anticipatory
    schema for logic that doesn't exist yet is the thing to avoid."""

    OPEN = "open"
    CLOSED = "closed"


class ConversationParticipantRole(str, enum.Enum):
    """One participant's role on one conversation - a person can appear as
    FROM on one message and CC on another within the same thread, but
    ConversationParticipant is one row per (conversation, email), so this
    records whichever role is currently most relevant (see
    conversation_participant.py's docstring), not a per-message log."""

    TO = "to"
    CC = "cc"
    FROM_ = "from"  # trailing underscore: `from` is a Python keyword


# --- M6.2: Mailbox Synchronization -------------------------------------------


class MailboxSyncStatus(str, enum.Enum):
    """Outcome of the most recent sync tick for one MailboxSyncState row -
    deliberately just two values, same "minimal, not a workflow" discipline
    as ConversationStatus. OK means the last tick completed without a
    provider/credential error (it says nothing about whether any messages
    were found - zero-new-messages is still OK). ERROR means the last tick
    failed before it could advance the cursor - last_sync_detail carries
    the reason, attempt_count tracks how many consecutive ticks have failed
    (for future backoff logic, not implemented differently by this enum
    itself). Resist adding PAUSED/DISABLED here speculatively - if a
    per-connection sync toggle is ever needed, that is a boolean on
    MailboxSyncState or ProviderConnection, not a third status value mixing
    "is sync allowed to run" with "how did it go last time"."""

    OK = "ok"
    ERROR = "error"


# --- M6.4: Reply Intelligence -------------------------------------------------


class ReplyStatus(str, enum.Enum):
    """Deterministic MVP classification of a Conversation's MOST RECENT
    inbound reply - deliberately just these four values (explicit product
    scope for M6.4), not an open-ended taxonomy. This is a rolling,
    current-state field, not a history: reprocessing later, different
    replies overwrites it, the same way Conversation.last_reply_at/
    last_reply_from do - see Conversation's own docstring. A separate
    per-message ReplyAnalysis table (versioned, with confidence/reasoning)
    was considered and explicitly rejected for M6.4 - Conversation
    represents current state only; per-message analysis history is
    deferred to a future milestone if a real need for it appears.

    NEUTRAL is not "no reply yet" - a Conversation with no inbound reply
    at all simply has reply_status = NULL. NEUTRAL specifically means the
    deterministic rule engine looked at a real reply and found no
    confident signal either way - see rules_classifier.py."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    OUT_OF_OFFICE = "out_of_office"


# --- M7.1: Workflow Engine -----------------------------------------------
# The engine's own enums, kept in this same shared file per this
# project's single-enums-file convention - NOT in app/workflow_engine/,
# matching the "models (and their enums) always live in app/models/,
# only engine/service code gets its own per-milestone package" precedent
# already established for app/reply_intelligence/.


class WorkflowDefinitionStatus(str, enum.Enum):
    """Definition-level lifecycle - deliberately distinct from, and never
    to be confused with, WorkflowInstanceStatus (an INSTANCE's own
    RUNNING/WAITING/COMPLETED execution state, added in Part 1 Phase 3
    below). This describes whether one (key, version) row is currently
    eligible to start NEW instances at all - see the approved M7.1
    Compatibility Policy (docs/architecture/m7-workflow-engine-plan.md
    section 3) for the full governance contract this enum implements:

    DRAFT - being authored/tested. Never matches a trigger, never starts
    an instance - the ONLY status where in-place editing of the row is
    permitted at all.
    ACTIVE - eligible to start new instances. At most one version per
    `key` may be ACTIVE at a time, enforced by a partial unique database
    index (migration 0014), not only by application-level discipline.
    Immutable from the moment it becomes ACTIVE - no field on the row may
    change again while it holds this status.
    DEPRECATED - retired: no longer eligible to start new instances, but
    never deleted and never reopened for editing - exactly as immutable
    as ACTIVE, for the same reason (an already-running WorkflowInstance
    pinned to a DEPRECATED version keeps executing against it normally,
    to completion). A `key` may validly have zero ACTIVE versions at once
    (every version DEPRECATED) - a deliberate, supported way to pause a
    workflow from starting new instances without a replacement ready.

    The ONLY sanctioned code path that ever changes this field is
    app.workflow_engine.definitions.activate_definition() (Part 1, Phase
    2) - no other function, route, or migration is permitted to.
    """

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class WorkflowInstanceStatus(str, enum.Enum):
    """One running (or completed) execution of a WorkflowDefinition -
    deliberately distinct from WorkflowDefinitionStatus above (that one
    describes the definition template's own lifecycle; this one
    describes ONE EXECUTION of it). See docs/architecture/
    m7-workflow-engine-plan.md section 4 for the full state diagram this
    enum implements.

    PENDING - created (a trigger event matched), not yet picked up by
    the Step Runner worker.
    RUNNING - actively being processed; the Step Runner may claim it.
    WAITING - paused, subscribed to a specific event_type (read from the
    pinned definition's step_graph for the current step - see
    WorkflowInstance's own docstring), resumed by the Event Dispatcher
    worker when a matching event arrives. Also how a long-running
    domain Action (one that returns PENDING) is represented - there is
    no separate "async callback" mechanism; waiting for an Action to
    finish reuses this exact state.
    SUSPENDED - an OPERATOR-driven pause, distinct from WAITING (which is
    a normal, expected part of a flow) - not reached or left by any
    automatic transition in Part 1 of this milestone; the column/value
    exists per the approved architecture but no code path sets it yet.
    COMPLETED / FAILED / CANCELLED - terminal. Never deleted, never
    reused - a new trigger event always creates a brand-new instance,
    never resurrects a terminal one.

    No code path anywhere in this codebase migrates a running instance to
    a different WorkflowDefinition version - see that model's own
    docstring and the approved Compatibility Policy."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStepInvocationStatus(str, enum.Enum):
    """The persisted lifecycle of ONE ROW in workflow_step_invocations -
    one row per actual step-execution ATTEMPT (append-only, never
    updated in place once written - a retry is a new row, not an edit to
    the old one). Deliberately NOT the same vocabulary as
    app.workflow_engine.actions.base.ActionOutcome (an Action's own
    in-process return value) - the Step Runner worker (Part 1, Phase 5)
    is what translates one into the other; RUNNING and SKIPPED in
    particular are states an Action itself never returns, only the
    engine's own bookkeeping produces them."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class EventConsumptionOutcome(str, enum.Enum):
    """What one EventConsumption row records about the Event Dispatcher
    worker's processing of one Event against one candidate outcome - see
    EventConsumption's own docstring for exactly how NO_MATCH's
    nullable workflow_instance_id interacts with this table's unique
    constraint."""

    STARTED_NEW_INSTANCE = "started_new_instance"
    RESUMED_INSTANCE = "resumed_instance"
    NO_MATCH = "no_match"


# --- CRM Automation (relationship_stage state machine + Task/Recommended
# Actions) -------------------------------------------------------------------


class TaskPriority(str, enum.Enum):
    """A Task's urgency, set deterministically at creation time by
    app.crm_automation.state_machine's suggestion rules (e.g. a reply
    needing human review is always HIGH) - never edited by a human
    afterward in this milestone; if that's ever needed, it's an additive
    PATCH, not a redesign."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class TaskStatus(str, enum.Enum):
    """A Recommended Action's lifecycle - PENDING until a human acts on
    it, then COMPLETED or DISMISSED. Deliberately just these three, same
    "minimal, not a workflow" discipline as ConversationStatus/
    MailboxSyncStatus elsewhere in this codebase - resist adding
    IN_PROGRESS/SNOOZED speculatively."""

    PENDING = "pending"
    COMPLETED = "completed"
    DISMISSED = "dismissed"
