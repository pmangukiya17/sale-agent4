import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import OpportunityForecastCategory, OpportunityStage


class OpportunityCreate(BaseModel):
    """Stage is intentionally settable at creation only (defaults to
    QUALIFIED_LEAD if omitted) - every subsequent change goes through the
    dedicated advance-stage endpoint, never this schema again."""

    name: str
    prospect_id: uuid.UUID
    prospect_contact_id: uuid.UUID | None = None
    stage: OpportunityStage = OpportunityStage.QUALIFIED_LEAD
    estimated_revenue: float | None = None
    currency: str | None = None
    win_probability: float | None = None
    ai_confidence_score: float | None = None
    forecast_category: OpportunityForecastCategory | None = None
    ai_reasoning: str | None = None
    next_recommended_action: str | None = None
    expected_close_date: date | None = None
    owner_user_id: uuid.UUID | None = None
    source_task_id: uuid.UUID | None = None


class OpportunityUpdate(BaseModel):
    """Deliberately excludes `stage`/`lost_reason`/`closed_at` - a stage
    change (and everything it implies) only ever happens through
    POST .../advance-stage, so every transition is guaranteed to produce
    an OpportunityStageHistory row, never a silent PATCH. Mirrors why
    ProspectContact's archive/unarchive are their own routes rather than
    folded into its generic update."""

    name: str | None = None
    prospect_contact_id: uuid.UUID | None = None
    estimated_revenue: float | None = None
    actual_revenue: float | None = None
    currency: str | None = None
    win_probability: float | None = None
    ai_confidence_score: float | None = None
    forecast_category: OpportunityForecastCategory | None = None
    ai_reasoning: str | None = None
    next_recommended_action: str | None = None
    expected_close_date: date | None = None
    owner_user_id: uuid.UUID | None = None


class AdvanceStageRequest(BaseModel):
    to_stage: OpportunityStage
    lost_reason: str | None = None


class OpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    prospect_id: uuid.UUID
    prospect_contact_id: uuid.UUID | None
    name: str
    stage: OpportunityStage
    estimated_revenue: float | None
    actual_revenue: float | None
    currency: str | None
    win_probability: float | None
    ai_confidence_score: float | None
    forecast_category: OpportunityForecastCategory | None
    ai_reasoning: str | None
    next_recommended_action: str | None
    expected_close_date: date | None
    closed_at: datetime | None
    lost_reason: str | None
    owner_user_id: uuid.UUID | None
    source_task_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class OpportunityStageHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    opportunity_id: uuid.UUID
    from_stage: OpportunityStage | None
    to_stage: OpportunityStage
    changed_by_user_id: uuid.UUID | None
    changed_at: datetime


class OpportunityFunnelStage(BaseModel):
    """One row of GET .../opportunities/funnel - Pipeline Overview's own
    shape. `count` is how many Opportunities currently sit at `stage`
    (see app.opportunities.service.compute_funnel's own docstring for why
    this reads current state, not history)."""

    stage: OpportunityStage
    count: int


class OpportunityPipelineValue(BaseModel):
    """GET .../opportunities/pipeline-value - Revenue Pipeline's own KPI
    shape. open_pipeline_value sums estimated_revenue across every
    non-closed Opportunity; closed_won_value sums actual_revenue across
    CLOSED_WON Opportunities only - two distinct figures, never
    conflated."""

    open_pipeline_value: float
    closed_won_value: float
