import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AIPremiumPreauthorization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    M8.3 (AI Gateway Management & Control, Step 7 - Premium Approval UI).
    Implements the CEO-approved (2026-07-28/29) "pre-authorization, not
    pause/resume" model - see docs/architecture/m8-3-ai-gateway-control-
    center-plan.md Section 12 Decision 1 and Section 13.1 for the full
    reasoning. One row per Approve/Reject DECISION an admin makes against a
    flagged `AIRequestLog` row - never mutated once written; a correction
    (e.g. approving after an earlier rejection) is a new row, matching this
    codebase's existing `AIProviderConfigAudit` "append-only audit" pattern
    (Step 1/Step 2) rather than an editable status field.

    An "approved" row is a genuine, load-bearing GATE OVERRIDE - read by
    `app.ai_gateway.premium_approval_resolver.SQLAlchemyPremiumApprovalResolver`
    on `AIGateway`'s own decision path - as well as an audit record. A
    "rejected" row is audit-only (per Decision 1c: "Reject is an audit
    annotation") - it changes nothing about the gate; it exists purely so
    the History view (Step 7) has a real row to show, not a synthesized
    one.

    Scope is deliberately `(company_profile_id, capability)`, matching
    Decision 1's own wording ("for that capability/company") - NOT scoped
    to the single `AIRequestLog` row that prompted it. Approving one
    flagged event clears every future attempt of that same capability for
    that same company until `expires_at`, not just a literal retry of the
    exact same request - this is the whole point of "pre-authorization"
    over "resume a specific request" (Section 1.1/1.3 of the Step 7 plan:
    there is nothing to resume, and nothing to resume even if it were
    wanted - `AIRequestLog` itself carries no reference back to whichever
    business object originated it).

    `company_profile_id` uses `ondelete="RESTRICT"`, NOT CASCADE (CEO
    decision, 2026-07-29 - overriding this table's own original design
    note, which had recommended CASCADE): even though a grant is
    short-lived, it is still a governance/audit record, and this project
    has consistently moved toward protecting business data from silent
    deletion (see the Track A "fix 7 CASCADE FKs to RESTRICT" migration).
    Deleting a CompanyProfile while pre-authorization rows still reference
    it must be an explicit administrative action (delete the rows first),
    never an implicit side effect of deleting the company.

    `decided_by_user_id` uses `ondelete="SET NULL"` - the admin who made
    the decision may later be deleted without destroying the audit record
    of the decision itself, exactly the same reasoning
    `AIProviderConfig.updated_by_user_id`/`AIRequestLog.company_profile_id`
    already established for "historical/operational record outlives its
    referenced actor."

    `source_request_log_id` uses `ondelete="SET NULL"` - traceability back
    to the specific flagged `AIRequestLog` event that prompted this
    decision, when known (it always is for a decision made through the
    Premium Approval Center's own Approve/Reject buttons, since those
    always act on a specific row's id) - but `AIRequestLog` rows are pure,
    disposable observability history (see that model's own docstring), so
    losing one must never block or cascade-delete a real governance
    decision that happened to reference it.

    `expires_at` is nullable - set for `decision="approved"` rows
    (`decided_at` + `settings.AI_GATEWAY_PREMIUM_PREAUTH_MINUTES`, 120
    minutes per the CEO's 2026-07-29 decision), left NULL for
    `decision="rejected"` rows (nothing to expire - a rejection has no
    window, it just is one).
    """

    __tablename__ = "ai_premium_preauthorizations"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    capability: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source_request_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_request_logs.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company_profile: Mapped["CompanyProfile"] = relationship()
    decided_by_user: Mapped["User | None"] = relationship()
    source_request_log: Mapped["AIRequestLog | None"] = relationship()
