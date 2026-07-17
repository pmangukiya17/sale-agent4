import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import OutreachDraftStatus


class OutreachEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outreach_draft_id: uuid.UUID
    block_key: str | None
    personalization_strategy_id: uuid.UUID | None
    signal_id: uuid.UUID | None
    recommendation_id: uuid.UUID | None
    intelligence_snapshot_id: uuid.UUID | None
    excerpt: str | None
    confidence_score: float | None


class OutreachEditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outreach_draft_id: uuid.UUID
    edited_by_user_id: uuid.UUID | None
    edited_at: datetime
    previous_content: dict[str, Any]
    new_content: dict[str, Any]
    edit_reason: str | None


class OutreachDraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outreach_job_id: uuid.UUID | None
    prospect_id: uuid.UUID
    prospect_contact_id: uuid.UUID
    company_profile_id: uuid.UUID
    channel_key: str
    outreach_playbook_id: uuid.UUID
    outreach_playbook_version: int
    prompt_version_id: uuid.UUID
    version: int
    is_current: bool
    rendered_prompt: str | None
    ai_generated_content: dict[str, Any]
    current_content: dict[str, Any]
    reasoning: str | None
    confidence: float | None
    status: OutreachDraftStatus
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    rejected_reason: str | None
    evidence: list[OutreachEvidenceRead] = []
    edits: list[OutreachEditRead] = []
    created_at: datetime
    updated_at: datetime


class OutreachDraftApproveBody(BaseModel):
    pass


class OutreachDraftRejectBody(BaseModel):
    reason: str | None = None


class OutreachDraftEditBody(BaseModel):
    new_content: dict[str, Any]
    edit_reason: str | None = None
