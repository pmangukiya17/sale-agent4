import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Identity, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Event(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One published Workflow Engine event - the entire input surface of the
    M7.1 orchestration layer (see docs/architecture/m7-workflow-engine-
    plan.md section 2). Deliberately opaque: `event_type` is a plain
    string the publishing domain module owns completely (same "adding one
    is a code change, never a migration" convention as
    EmailMessage.provider/ProviderConnection.provider_key elsewhere in
    this codebase) - this table, and every engine module built on top of
    it, must never interpret what a given `event_type` or `payload` means.

    Written via app.workflow_engine.events.publish_event(), always inside
    the SAME transaction as whatever domain write it reports - this is
    the transactional-outbox pattern the approved architecture requires
    instead of a message broker: in this project's single-Postgres
    deployment, the "outbox" and "the log the engine reads" are the same
    table. No caller should ever construct/add an Event row directly;
    publish_event() is the one sanctioned entry point (mirrors this
    project's own "one shared helper, not scattered call sites"
    discipline used for _log_event in app.delivery.dispatch_service).

    id (from UUIDPrimaryKeyMixin) is this event's identity. sequence_no is
    a SEPARATE, monotonic BigInteger identity column - the true total
    order the Event Dispatcher worker polls by. UUIDs are not sortable in
    insertion order and occurred_at can tie within one transaction/
    millisecond, so neither is sufficient alone as an ordering key; this
    is the first table in this codebase that needs a real insertion-order
    sequence, hence the new (to this project) BigInteger Identity column
    - every other table's ordering need so far has been satisfied by a
    plain timestamp column.

    company_profile_id is the one piece of tenant-scope knowledge the
    engine is allowed to know (see the architecture doc's section 1
    "necessary exception") - ondelete=CASCADE matches the convention
    already used for Conversation/EmailMessage.company_profile_id.

    subject_type/subject_id are opaque correlation keys ("what business
    entity is this about") - the engine indexes and stores them but never
    interprets subject_type strings; only publishing/consuming domain
    code and Action handlers give them meaning. Both nullable - not every
    event is about one specific entity.

    correlation_id ties a whole related chain of events/workflow activity
    together across module boundaries; causation_id is the specific
    event or action invocation one level up that directly produced this
    one. Neither is a foreign key - causation_id in particular can point
    at either another Event or a (Phase 3+) WorkflowStepInvocation, so a
    single-table FK would be wrong; both are plain, unconstrained UUID
    columns, the same "opaque correlation key" treatment as subject_id.

    payload is a plain JSONB blob, nullable - meaningful only to the
    publishing module and whatever Action handlers later read it; the
    engine never validates or interprets its shape. schema_version exists
    so a payload's shape can evolve later without breaking already-stored
    rows - defaults to 1, unused by anything in Part 1 of the M7.1
    implementation plan.

    Append-only - no code path in this milestone ever updates or deletes
    an Event row once written. `updated_at` (from TimestampMixin) is kept
    for consistency with every other table in this codebase, even though
    nothing is expected to ever change it in practice.
    """

    __tablename__ = "events"

    sequence_no: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), nullable=False, unique=True, index=True
    )

    # event_type/occurred_at deliberately NOT individually indexed here -
    # they're covered by the composite (company_profile_id, event_type,
    # occurred_at) index created explicitly in the migration, matching
    # the exact two-index design in the approved architecture doc
    # (section 2/11) rather than adding redundant single-column indexes
    # alongside it.
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False)

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False
    )

    subject_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Indexed on its own (unlike subject_type) - a cheap, direct "show
    # everything about this entity" lookup, serving the explainability
    # design principle, independent of the composite index above.
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    source: Mapped[str] = mapped_column(String(255), nullable=False)

    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # --- M8.5 Event Backbone: additive columns only, migration 0016 ----
    # No change to sequence_no/ordering, indexes above, publish_event()'s
    # existing required parameters, or the Event Dispatcher worker's own
    # matching logic - this table remains the exact same single platform
    # event stream M7.1 built, just carrying four more optional facts.
    #
    # actor_type/actor_id - who or what produced this event. Same "opaque,
    # domain-owned string pair" treatment as subject_type/subject_id
    # above, deliberately NOT a UUID foreign key: actors are not
    # uniformly UUID-keyed rows in this codebase (a human User is a UUID,
    # but an Agent is a plain string key - see app.ai_agents.registry's
    # AGENT_REGISTRY: dict[str, Agent] - and "system" isn't a row at
    # all). actor_type distinguishes which of those three a given
    # actor_id string means; the engine/API never interprets either.
    actor_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # severity - plain string, not a Postgres enum, matching event_type/
    # source's own "domain owns the vocabulary, adding a value is a code
    # change not a migration" convention (same reasoning as
    # provider_key/channel_key elsewhere). Expected values today:
    # "info"/"warning"/"critical", but this column enforces none of that
    # - a future publisher can introduce a new severity string without a
    # schema change.
    severity: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # category - a coarser grouping than event_type (e.g. "research" for
    # "research.completed"), for filtering/analytics/dashboard grouping.
    # Same free-string treatment as severity, for the same reason. Kept
    # deliberately separate from event_type rather than derived from it
    # by string-splitting convention, since not every event_type is
    # guaranteed to follow a "category.verb" naming shape forever.
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    company_profile: Mapped["CompanyProfile"] = relationship()
