from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_company_profile
from app.db.session import get_db
from app.mailbox_brief.service import generate_brief, get_latest_brief
from app.models.company_profile import CompanyProfile
from app.models.mailbox_brief import MailboxBrief
from app.models.user import User
from app.schemas.mailbox_brief import MailboxBriefRead

router = APIRouter()

# Track C5 (dashboard-capabilities-architecture-plan.md, Section 6). Two
# routes only, matching the CEO's explicit persistence model: GET never
# generates (a plain read of whatever was last saved, or 404 if nothing
# has been generated yet), POST .../generate is the only way a new
# MailboxBrief row is ever created - always an explicit "Generate New
# Brief" action, never a page-load side effect. Both go through the same
# get_owned_company_profile dependency every other route in this codebase
# uses - no new isolation mechanism invented.


@router.get(
    "/company-profiles/{company_profile_id}/mailbox-brief",
    response_model=MailboxBriefRead,
)
def get_mailbox_brief(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    db: Session = Depends(get_db),
) -> MailboxBrief:
    brief = get_latest_brief(db, profile.id)
    if brief is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Mailbox Brief has been generated yet for this business.",
        )
    return brief


@router.post(
    "/company-profiles/{company_profile_id}/mailbox-brief/generate",
    response_model=MailboxBriefRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_mailbox_brief(
    profile: CompanyProfile = Depends(get_owned_company_profile),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MailboxBrief:
    """A POST, not a GET, deliberately - this is an action with a real
    cost (a synthesis pass, real cost when a future LLM engine replaces
    the deterministic stub) and a real privacy posture ("the workspace is
    read only in response to an explicit user click"), not an idempotent
    read - matches the existing convention of using POST for Discovery/
    Research/Personalization/Outreach "run" actions."""
    return generate_brief(db, profile, requested_by_user_id=current_user.id)
