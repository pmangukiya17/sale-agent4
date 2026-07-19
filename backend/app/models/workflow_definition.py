import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import WorkflowDefinitionStatus


class WorkflowDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One immutable (key, version) workflow specification - see
    docs/architecture/m7-workflow-engine-plan.md section 3 and the
    Compatibility Policy subsection there for the full governance
    contract this model implements. Declarative, not code: `step_graph`
    is a plain JSONB blob (each step names an `action_key` plus
    transition rules) that app.workflow_engine.definitions.
    validate_step_graph() checks before a row is ever allowed to become
    ACTIVE (Part 1, Phase 2) - this model itself enforces nothing beyond
    its own column types; immutability and the DRAFT->ACTIVE->DEPRECATED
    lifecycle are enforced by the service layer
    (app.workflow_engine.definitions), never by application code writing
    to this table directly.

    `key` names WHAT workflow this is across all its versions (e.g.
    "draft_approved_to_reply_classified"); `version` is a plain,
    human-assigned integer, NOT auto-incremented by the database - each
    new version is a deliberate, separate INSERT the definitions-service
    layer performs, one higher than the previous version for that key.
    `UniqueConstraint(key, version)` below prevents two rows from ever
    claiming the same version number for the same key.

    `status` is WorkflowDefinitionStatus (DRAFT/ACTIVE/DEPRECATED) - see
    that enum's own docstring for the full lifecycle. **At most one
    version per `key` may be ACTIVE at a time** - enforced by a partial
    unique index on (key) WHERE status = 'ACTIVE', created in migration
    0014 (not mirrored here in __table_args__, matching this codebase's
    existing convention that partial/conditional indexes live only in
    the migration that creates them - see email_messages'
    uq_email_messages_connection_internet_message_id for the precedent).

    `trigger_event_type` + `trigger_filter` describe which Event(s) start
    a NEW WorkflowInstance of this definition - trigger_filter is an
    opaque JSONB filter expression (e.g. matched against Event.payload/
    subject_type), interpreted only by the Event Dispatcher worker (Part
    1, Phase 4), never by this model.

    `company_profile_id` is nullable - NULL means platform-authored
    (applies to every business), a non-null value means one specific
    business's own custom definition. Per the approved architecture's
    explicit v1 scope decision, ONLY platform-authored (NULL) definitions
    are created anywhere in this milestone - the column exists so a
    future milestone can support business-authored definitions without a
    schema change, but nothing in M7.1 itself ever sets it.

    A running WorkflowInstance pins BOTH `workflow_definition_id` and the
    specific `version` number at creation time (see WorkflowInstance's
    own docstring, Part 1 Phase 3) - this row's own `version` column is
    what gets copied at that moment; nothing about an instance's pinned
    version ever changes afterward, even if this same `key` later gets a
    v2, v3, v4. There is no automatic or manual engine-driven migration
    of a running instance to a different definition version, ever.
    """

    __tablename__ = "workflow_definitions"
    __table_args__ = (UniqueConstraint("key", "version", name="uq_workflow_definitions_key_version"),)

    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[WorkflowDefinitionStatus] = mapped_column(
        Enum(
            WorkflowDefinitionStatus,
            name="workflow_definition_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=WorkflowDefinitionStatus.DRAFT,
        nullable=False,
        index=True,
    )

    trigger_event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_filter: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    step_graph: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Nullable = platform-global (applies to every business). Non-null =
    # one specific business's own custom definition - NOT used by
    # anything in M7.1 itself (see docstring); declared now so a future
    # milestone supporting business-authored definitions needs no schema
    # change, matching the approved architecture's own explicit framing
    # of this as a deliberate, disclosed forward-compatibility column,
    # not speculative scope creep.
    company_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=True, index=True
    )

    company_profile: Mapped["CompanyProfile | None"] = relationship()
