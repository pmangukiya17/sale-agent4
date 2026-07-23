"""
Pure Opportunity stage-transition logic - Track C3
(dashboard-capabilities-architecture-plan.md, Section 1). No database
session, no model imports beyond the one enum this module reasons over -
every function here is a plain, deterministic value transformation,
unit-testable with zero fixtures (see
tests/test_opportunity_state_machine.py), same discipline as
app.crm_automation.state_machine.

Per the CEO's explicit final design decision for this track: an
Opportunity MAY skip stages, and this platform does NOT enforce a linear
progression through OpportunityStage's values - there is deliberately no
"you must pass through NEGOTIATION before PURCHASE_ORDER" rule here, and
no rule against moving "backwards" either (e.g. re-opening a CLOSED_LOST
deal back to NEGOTIATION). The only transition this module refuses is a
genuine no-op (to_stage == current_stage) - not a workflow-order
violation, just nothing to actually record.
"""
from dataclasses import dataclass

from app.models.enums import OpportunityStage

_CLOSED_STAGES = frozenset({OpportunityStage.CLOSED_WON, OpportunityStage.CLOSED_LOST})


class InvalidStageTransitionError(ValueError):
    """Raised only for a no-op transition (to_stage == current_stage) -
    never for "skipping" stages, which this platform explicitly allows.
    app.api.routes.opportunities translates this into a 400."""


def is_closed_stage(stage: OpportunityStage) -> bool:
    return stage in _CLOSED_STAGES


@dataclass(frozen=True)
class StageTransition:
    """What app.opportunities.service.advance_stage needs to apply one
    transition: the destination stage, and whether it lands the
    Opportunity in a closed state (which drives closed_at)."""

    to_stage: OpportunityStage
    is_closed: bool


def plan_stage_transition(current_stage: OpportunityStage, to_stage: OpportunityStage) -> StageTransition:
    """Validates and describes one stage transition. Raises
    InvalidStageTransitionError only for a same-stage no-op; every other
    (from, to) pair is valid, including "skipping" stages in either
    direction - per the CEO's explicit direction, this state machine
    never enforces a linear order."""
    if to_stage == current_stage:
        raise InvalidStageTransitionError(
            f"Opportunity is already at stage {current_stage.value!r} - nothing to transition."
        )
    return StageTransition(to_stage=to_stage, is_closed=is_closed_stage(to_stage))
