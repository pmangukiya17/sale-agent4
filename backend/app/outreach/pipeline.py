"""
Synchronous Outreach pipeline orchestrator - structural mirror of
Personalization's (M3) pipeline, plus the versioning/approval machinery
this milestone adds. No Celery/Redis/BackgroundTasks/polling worker -
running an outreach request means doing all of this within one
request/response cycle.

Never touches Prospect.relationship_stage, PersonalizationSnapshot, or any
other upstream table - Outreach only ever READS Personalization's output
and ProspectContact for addressing. Approving a draft (a separate action,
not part of this pipeline) is where relationship_stage would eventually
advance - not implemented in M4's generation pipeline itself.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.brand_email_signature import BrandEmailSignature
from app.models.communication_strategy import CommunicationStrategy
from app.models.enums import OutreachDraftStatus, OutreachJobStatus
from app.models.outreach_draft import OutreachDraft
from app.models.outreach_edit import OutreachEdit
from app.models.outreach_evidence import OutreachEvidence
from app.models.outreach_job import OutreachJob
from app.models.outreach_playbook import OutreachPlaybook
from app.models.outreach_request import OutreachRequest
from app.models.outreach_run import OutreachRun
from app.models.personalization_snapshot import PersonalizationSnapshot
from app.models.personalization_strategy import PersonalizationStrategy
from app.models.prompt_version import PromptVersion
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.models.user import User
from app.outreach.channels.base import ChannelRenderOutcome
from app.outreach.channels.registry import get_channel_provider
from app.outreach.context import OutreachContext

# Every registered channel reads its AI-behavior instructions from exactly
# one prompt_key - kept as a simple mapping here (configuration), not a
# column on ChannelProvider (engine logic).
_CHANNEL_PROMPT_KEY = {
    "email": "email_generation",
}


class OutreachConfigError(Exception):
    """Raised when an outreach job can't run because of missing
    configuration (unknown channel_key, no active PromptVersion for this
    channel) - a 400, not a 500. Distinct from a provider returning a
    low-confidence result for "not enough buyer information", which is not
    a config error and must never raise."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_prompt_version(db: Session, company_profile_id, channel_key: str, prompt_key: str) -> PromptVersion:
    # A business-specific active prompt overrides the global system
    # default - same "clone/override a system default" convention as every
    # *Template model, but here the expectation is most prompts stay
    # global (see PromptVersion's docstring).
    business_prompt = db.scalars(
        select(PromptVersion).where(
            PromptVersion.company_profile_id == company_profile_id,
            PromptVersion.channel_key == channel_key,
            PromptVersion.prompt_key == prompt_key,
            PromptVersion.is_active.is_(True),
        )
    ).first()
    if business_prompt is not None:
        return business_prompt

    system_prompt = db.scalars(
        select(PromptVersion).where(
            PromptVersion.company_profile_id.is_(None),
            PromptVersion.channel_key == channel_key,
            PromptVersion.prompt_key == prompt_key,
            PromptVersion.is_active.is_(True),
        )
    ).first()
    if system_prompt is None:
        raise OutreachConfigError(
            f"No active PromptVersion found for channel '{channel_key}' (prompt_key='{prompt_key}') - "
            f"neither a business-specific nor a system-default one exists."
        )
    return system_prompt


def _build_context(db: Session, request: OutreachRequest) -> OutreachContext:
    prospect = db.get(Prospect, request.prospect_id)
    prospect_contact = db.get(ProspectContact, request.prospect_contact_id)
    company_profile = prospect.company_profile
    outreach_playbook = db.get(OutreachPlaybook, request.outreach_playbook_id)

    prompt_key = _CHANNEL_PROMPT_KEY.get(request.channel_key)
    if prompt_key is None:
        raise OutreachConfigError(f"Unknown outreach channel '{request.channel_key}' - no prompt_key mapping registered.")
    prompt_version = _resolve_prompt_version(db, request.company_profile_id, request.channel_key, prompt_key)

    snapshot = db.scalars(
        select(PersonalizationSnapshot).where(
            PersonalizationSnapshot.prospect_id == request.prospect_id,
            PersonalizationSnapshot.is_current.is_(True),
        )
    ).first()
    communication_strategy = None
    strategies: list[PersonalizationStrategy] = []
    if snapshot is not None:
        communication_strategy = db.scalars(
            select(CommunicationStrategy).where(CommunicationStrategy.personalization_snapshot_id == snapshot.id)
        ).first()
        strategies = list(
            db.scalars(
                select(PersonalizationStrategy).where(
                    PersonalizationStrategy.personalization_snapshot_id == snapshot.id
                )
            ).all()
        )

    # Business Branding: read live, not versioned/frozen at this point -
    # freezing happens below, once, into ai_generated_content.assembled at
    # the moment a channel provider actually renders with it.
    business_email_signature = db.scalars(
        select(BrandEmailSignature).where(BrandEmailSignature.company_profile_id == company_profile.id)
    ).first()

    return OutreachContext(
        prospect=prospect,
        prospect_contact=prospect_contact,
        company_profile=company_profile,
        outreach_playbook=outreach_playbook,
        prompt_version=prompt_version,
        personalization_snapshot=snapshot,
        communication_strategy=communication_strategy,
        strategies=strategies,
        business_email_signature=business_email_signature,
    )


def _next_draft_version(db: Session, prospect_contact_id, channel_key: str) -> int:
    return (
        db.scalar(
            select(func.coalesce(func.max(OutreachDraft.version), 0)).where(
                OutreachDraft.prospect_contact_id == prospect_contact_id, OutreachDraft.channel_key == channel_key
            )
        )
        + 1
    )


def _supersede_previous_current_draft(db: Session, prospect_contact_id, channel_key: str) -> None:
    stmt = select(OutreachDraft).where(
        OutreachDraft.prospect_contact_id == prospect_contact_id,
        OutreachDraft.channel_key == channel_key,
        OutreachDraft.is_current.is_(True),
    )
    for draft in db.scalars(stmt).all():
        draft.is_current = False
        # A version that had been approved is explicitly SUPERSEDED (a
        # newer regeneration replaced it), distinct from one that was
        # simply never promoted - see OutreachDraftStatus's docstring.
        if draft.status == OutreachDraftStatus.APPROVED:
            draft.status = OutreachDraftStatus.SUPERSEDED


def run_outreach_request(db: Session, request: OutreachRequest, triggered_by_user: User) -> OutreachJob:
    context = _build_context(db, request)
    snapshot = context.personalization_snapshot
    prompt_version = context.prompt_version
    outreach_playbook = context.outreach_playbook

    job = OutreachJob(
        outreach_request_id=request.id,
        prospect_id=request.prospect_id,
        prospect_contact_id=request.prospect_contact_id,
        company_profile_id=request.company_profile_id,
        personalization_snapshot_id=snapshot.id if snapshot else None,
        prompt_version_id=prompt_version.id,
        status=OutreachJobStatus.RUNNING,
        started_at=_now(),
    )
    db.add(job)
    db.flush()  # need job.id before child rows reference it

    job_log: list[dict] = []

    try:
        provider = get_channel_provider(request.channel_key)
        outcome: ChannelRenderOutcome = provider.render(context)
        job_log.append(
            {"provider": outcome.model_used, "prompt_version": outcome.prompt_version_marker, "status": "completed"}
        )
    except Exception as exc:  # noqa: BLE001 - a genuine provider failure, not "nothing found"
        error_message = str(exc)
        job_log.append({"status": "failed", "error": error_message})
        job.status = OutreachJobStatus.FAILED
        job.finished_at = _now()
        job.error_message = error_message
        job.log = job_log
        request.status = job.status
        db.commit()
        db.refresh(job)
        return job

    # --- OutreachDraft: new version, unset/supersede the previous current --
    _supersede_previous_current_draft(db, request.prospect_contact_id, request.channel_key)
    next_version = _next_draft_version(db, request.prospect_contact_id, request.channel_key)

    ai_generated_content = {
        "blocks": [
            {"block_key": b.block_key, "behavior": b.behavior, "content": b.content, "reasoning": b.reasoning}
            for b in outcome.blocks
        ],
        "assembled": outcome.assembled,
    }

    draft = OutreachDraft(
        outreach_job_id=job.id,
        prospect_id=request.prospect_id,
        prospect_contact_id=request.prospect_contact_id,
        company_profile_id=request.company_profile_id,
        channel_key=request.channel_key,
        outreach_playbook_id=outreach_playbook.id,
        outreach_playbook_version=outreach_playbook.version,
        prompt_version_id=prompt_version.id,
        version=next_version,
        is_current=True,
        rendered_prompt=outcome.rendered_prompt,
        ai_generated_content=ai_generated_content,
        # current_content starts as an independent copy - editing it later
        # never touches ai_generated_content, which stays frozen forever.
        current_content=dict(ai_generated_content),
        reasoning=outcome.reasoning,
        confidence=outcome.confidence,
        status=OutreachDraftStatus.DRAFT,
    )
    db.add(draft)
    db.flush()  # need draft.id for evidence rows

    for ev in outcome.evidence:
        db.add(
            OutreachEvidence(
                outreach_draft_id=draft.id,
                block_key=ev.block_key,
                personalization_strategy_id=ev.personalization_strategy_id,
                signal_id=ev.signal_id,
                recommendation_id=ev.recommendation_id,
                intelligence_snapshot_id=ev.intelligence_snapshot_id,
                excerpt=ev.excerpt,
                confidence_score=ev.confidence_score,
            )
        )

    job.finished_at = _now()
    job.status = OutreachJobStatus.COMPLETED
    job.error_message = None
    job.log = job_log
    request.status = job.status

    run = OutreachRun(
        outreach_request_id=request.id,
        outreach_job_id=job.id,
        prospect_id=request.prospect_id,
        prospect_contact_id=request.prospect_contact_id,
        company_profile_id=request.company_profile_id,
        triggered_by_user_id=triggered_by_user.id,
        triggered_at=job.started_at,
        config_snapshot={
            "outreach_playbook_id": str(outreach_playbook.id),
            "outreach_playbook_name": outreach_playbook.name,
            "outreach_playbook_version": outreach_playbook.version,
            "prompt_version_id": str(prompt_version.id),
            "prompt_version": prompt_version.version,
            "personalization_snapshot_id": str(snapshot.id) if snapshot else None,
            "personalization_snapshot_version": snapshot.version if snapshot else None,
            "channel_key": request.channel_key,
        },
        outreach_draft_version_created=next_version,
    )
    db.add(run)

    db.commit()
    db.refresh(job)
    return job


def approve_outreach_draft(db: Session, draft: OutreachDraft, approved_by_user: User) -> OutreachDraft:
    draft.status = OutreachDraftStatus.APPROVED
    draft.approved_by_user_id = approved_by_user.id
    draft.approved_at = _now()
    db.commit()
    db.refresh(draft)
    return draft


def reject_outreach_draft(db: Session, draft: OutreachDraft, reason: str | None) -> OutreachDraft:
    draft.status = OutreachDraftStatus.REJECTED
    draft.rejected_reason = reason
    db.commit()
    db.refresh(draft)
    return draft


def edit_outreach_draft(
    db: Session, draft: OutreachDraft, new_content: dict, edited_by_user: User, edit_reason: str | None
) -> OutreachDraft:
    """Applies a human edit to current_content, logging the before/after
    snapshot via a child OutreachEdit row. ai_generated_content is never
    touched - this is the whole mechanism by which AI history survives
    edits (see OutreachEdit's docstring)."""
    edit = OutreachEdit(
        outreach_draft_id=draft.id,
        edited_by_user_id=edited_by_user.id,
        edited_at=_now(),
        previous_content=draft.current_content,
        new_content=new_content,
        edit_reason=edit_reason,
    )
    db.add(edit)
    draft.current_content = new_content
    db.commit()
    db.refresh(draft)
    return draft
