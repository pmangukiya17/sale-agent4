import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import OutreachBlockBehavior


class OutreachBlockBase(BaseModel):
    block_key: str
    behavior: OutreachBlockBehavior
    fixed_content: str | None = None
    ai_guidance: str | None = None
    applicable_channels: list[str] | None = None
    is_mandatory: bool = False
    display_order: int = 0


class OutreachBlockCreate(OutreachBlockBase):
    pass


class OutreachBlockRead(OutreachBlockBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outreach_playbook_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class OutreachPlaybookBase(BaseModel):
    name: str
    description: str | None = None
    playbook_goal: str | None = None
    sales_methodology: str | None = None
    brand_voice: str | None = None
    core_value_proposition: str | None = None
    communication_principles: list[str] | None = None
    personalization_rules: dict[str, Any] | None = None
    channel_preferences: dict[str, Any] | None = None
    cta_strategy: str | None = None


class OutreachPlaybookCreate(OutreachPlaybookBase):
    # A new playbook always starts its own version-1 lineage; blocks are
    # supplied inline so the whole playbook is created in one call, same
    # "create the parent + its children together" convention used
    # elsewhere (e.g. DiscoverySearch + its criteria).
    blocks: list[OutreachBlockCreate] = []


class OutreachPlaybookReviseRequest(OutreachPlaybookBase):
    """
    Body for creating a new version of an existing playbook lineage
    (same company_profile_id + name). Never edits the previous version in
    place - see OutreachPlaybook's docstring on versioning. All fields
    optional-with-defaults-from-base so a caller only needs to send what
    changed; the route fills in the rest from the current version.
    """
    blocks: list[OutreachBlockCreate] = []


class OutreachPlaybookRead(OutreachPlaybookBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID | None
    version: int
    is_current: bool
    derived_from_playbook_version: int | None
    is_system_default: bool
    blocks: list[OutreachBlockRead] = []
    created_at: datetime
    updated_at: datetime
