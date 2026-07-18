"""
DeliveryCampaign lifecycle: create (freeze N approved drafts into queue
items), schedule (assign send times), pause/resume/cancel. See
delivery_campaign.py's model docstring for why this is not a
Request->Job->Run pipeline.

KNOWN SCOPE LIMIT, disclosed rather than silently shipped: when
respect_recipient_timezone is True and a campaign's queue items span
several different recipient timezones, daily_limit/hourly_limit are
enforced independently PER TIMEZONE GROUP, not globally across the whole
campaign - two timezone groups on the same SendingProfile could together
exceed that profile's daily_limit even though each group individually
respects it. dispatch_service's rolling-window re-check at actual send
time (see its docstring) is the real backstop against this, not this
function - schedule_campaign only assigns intended send times; it does
not guarantee delivery will happen at exactly that instant.
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone as dt_timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.delivery.scheduler.windows import generate_send_times
from app.delivery.timezone.resolver import local_window_to_utc, resolve_recipient_timezone
from app.models.country import Country
from app.models.delivery_campaign import DeliveryCampaign
from app.models.delivery_event import DeliveryEvent
from app.models.delivery_queue_item import DeliveryQueueItem
from app.models.enums import DeliveryCampaignStatus, DeliveryEventType, DeliveryQueueItemStatus, OutreachDraftStatus
from app.models.outreach_draft import OutreachDraft
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact
from app.models.sending_profile import SendingProfile

_MAX_SCHEDULING_DAYS = 366  # safety cap against a degenerate window looping forever

# Statuses that mean "this draft is already spoken for" - matches the
# partial unique index migration 0008 puts on delivery_queue_items
# (uq_delivery_queue_items_active_draft) exactly. Single source of truth,
# shared by _enqueue_draft's pre-insert guard below and
# api/routes/delivery_campaigns.py's available-drafts picker query, so the
# two can never drift out of sync on what "actively queued" means.
ACTIVELY_QUEUED_STATUSES = [
    DeliveryQueueItemStatus.QUEUED,
    DeliveryQueueItemStatus.SCHEDULED,
    DeliveryQueueItemStatus.SENDING,
    DeliveryQueueItemStatus.RETRY,
]


class CampaignServiceError(Exception):
    """Raised for anything the API layer should turn into a 400 - unknown/
    unapproved draft, missing recipient email, unknown sending profile,
    campaign not found. Not raised for provider/network failures - those
    don't exist at this layer, only at dispatch time."""


def _now() -> datetime:
    return datetime.now(dt_timezone.utc)


def _log_event(db: Session, queue_item_id: uuid.UUID, event_type: DeliveryEventType, detail: dict | None = None) -> None:
    db.add(DeliveryEvent(delivery_queue_item_id=queue_item_id, event_type=event_type, detail=detail))


def _lookup_country_default_timezone(db: Session, country_text: str | None) -> str | None:
    """Best-effort only: Prospect.country is free text (whatever a
    Discovery provider returned), not a foreign key to Country - see
    Prospect's model docstring. Matches case-insensitively against either
    Country.name or Country.code; returns None (falling through to UTC in
    resolve_recipient_timezone) if nothing matches rather than guessing."""
    if not country_text:
        return None
    stmt = select(Country.default_timezone).where(
        or_(func.lower(Country.name) == country_text.strip().lower(), func.lower(Country.code) == country_text.strip().lower())
    )
    return db.scalar(stmt)


@dataclass
class _ResolvedSchedulingConfig:
    window_start: time
    window_end: time
    min_gap_seconds: int
    max_gap_seconds: int
    hourly_limit: int | None
    daily_limit: int | None
    respect_recipient_timezone: bool
    business_timezone: str


def _resolve_scheduling_config(campaign: DeliveryCampaign, sending_profile: SendingProfile) -> _ResolvedSchedulingConfig:
    return _ResolvedSchedulingConfig(
        window_start=campaign.sending_window_start or sending_profile.sending_window_start or time(8, 0),
        window_end=campaign.sending_window_end or sending_profile.sending_window_end or time(18, 0),
        min_gap_seconds=campaign.min_gap_seconds or sending_profile.min_gap_seconds or 60,
        max_gap_seconds=campaign.max_gap_seconds or sending_profile.max_gap_seconds or 300,
        hourly_limit=campaign.hourly_limit or sending_profile.hourly_limit,
        daily_limit=campaign.daily_limit or sending_profile.daily_limit,
        respect_recipient_timezone=campaign.respect_recipient_timezone,
        business_timezone=sending_profile.sending_timezone or "UTC",
    )


def create_campaign(
    db: Session,
    *,
    company_profile_id: uuid.UUID,
    sending_profile_id: uuid.UUID,
    name: str,
    description: str | None,
    outreach_draft_ids: list[uuid.UUID],
    created_by_user_id: uuid.UUID | None,
    **overrides,
) -> DeliveryCampaign:
    sending_profile = db.get(SendingProfile, sending_profile_id)
    if sending_profile is None or sending_profile.company_profile_id != company_profile_id:
        raise CampaignServiceError(f"SendingProfile {sending_profile_id} not found for this business")
    if not outreach_draft_ids:
        raise CampaignServiceError("A campaign needs at least one approved OutreachDraft")

    campaign = DeliveryCampaign(
        company_profile_id=company_profile_id,
        sending_profile_id=sending_profile_id,
        name=name,
        description=description,
        created_by_user_id=created_by_user_id,
        **overrides,
    )
    db.add(campaign)
    db.flush()

    for draft_id in outreach_draft_ids:
        _enqueue_draft(db, campaign, draft_id)

    db.commit()
    db.refresh(campaign)
    return campaign


def _enqueue_draft(db: Session, campaign: DeliveryCampaign, draft_id: uuid.UUID) -> DeliveryQueueItem:
    draft = db.get(OutreachDraft, draft_id)
    if draft is None or draft.company_profile_id != campaign.company_profile_id:
        raise CampaignServiceError(f"OutreachDraft {draft_id} not found for this business")
    if draft.status != OutreachDraftStatus.APPROVED:
        raise CampaignServiceError(f"OutreachDraft {draft_id} is not approved (status={draft.status.value})")
    if not draft.is_current:
        raise CampaignServiceError(f"OutreachDraft {draft_id} is not the current version - regenerate/re-approve first")

    # Confirmed root cause (M5 Layer 7 verification): without this check,
    # a draft that's already actively queued elsewhere hits
    # delivery_queue_items' partial unique index
    # (uq_delivery_queue_items_active_draft) purely at db.flush() time
    # below, raising a bare IntegrityError - which is not a
    # CampaignServiceError, so the route's `except CampaignServiceError`
    # never catches it and FastAPI returns a raw 500 instead of a clean
    # 400. The available-drafts endpoint's own docstring already promised
    # this would surface as "create_campaign reject[ing] it with a 400" -
    # that guard was simply never written. Checking explicitly here, before
    # attempting the insert, turns the exact same condition into the
    # CampaignServiceError -> 400 every other validation failure in this
    # function already produces.
    already_queued = db.scalar(
        select(DeliveryQueueItem.id).where(
            DeliveryQueueItem.outreach_draft_id == draft_id,
            DeliveryQueueItem.status.in_(ACTIVELY_QUEUED_STATUSES),
        )
    )
    if already_queued is not None:
        raise CampaignServiceError(f"OutreachDraft {draft_id} already has an active delivery queue item - it can't be queued twice")

    contact = db.get(ProspectContact, draft.prospect_contact_id)
    if contact is None or not contact.email:
        raise CampaignServiceError(f"ProspectContact for draft {draft_id} has no email address to send to")
    prospect = db.get(Prospect, draft.prospect_id)

    country_tz = _lookup_country_default_timezone(db, prospect.country if prospect else None)
    recipient_timezone = resolve_recipient_timezone(
        explicit_timezone=contact.timezone or (prospect.timezone if prospect else None),
        country_default_timezone=country_tz,
    )

    queue_item = DeliveryQueueItem(
        delivery_campaign_id=campaign.id,
        outreach_draft_id=draft.id,
        prospect_id=draft.prospect_id,
        prospect_contact_id=draft.prospect_contact_id,
        company_profile_id=campaign.company_profile_id,
        sending_profile_id=campaign.sending_profile_id,
        channel_key=draft.channel_key,
        frozen_content=draft.current_content,
        frozen_draft_version=draft.version,
        recipient_email=contact.email,
        recipient_timezone=recipient_timezone,
        status=DeliveryQueueItemStatus.QUEUED,
        max_attempts=settings.DELIVERY_DEFAULT_MAX_ATTEMPTS,
    )
    db.add(queue_item)
    db.flush()
    _log_event(db, queue_item.id, DeliveryEventType.QUEUED, detail={"frozen_draft_version": draft.version})
    return queue_item


def schedule_campaign(db: Session, campaign_id: uuid.UUID) -> DeliveryCampaign:
    campaign = db.get(DeliveryCampaign, campaign_id)
    if campaign is None:
        raise CampaignServiceError(f"DeliveryCampaign {campaign_id} not found")
    sending_profile = campaign.sending_profile
    config = _resolve_scheduling_config(campaign, sending_profile)

    queued_items = list(
        db.scalars(
            select(DeliveryQueueItem)
            .where(DeliveryQueueItem.delivery_campaign_id == campaign.id, DeliveryQueueItem.status == DeliveryQueueItemStatus.QUEUED)
            .order_by(DeliveryQueueItem.created_at.asc())
        ).all()
    )
    if not queued_items:
        return campaign

    groups: dict[str, list[DeliveryQueueItem]] = {}
    for item in queued_items:
        group_key = item.recipient_timezone if config.respect_recipient_timezone else config.business_timezone
        groups.setdefault(group_key or "UTC", []).append(item)

    for tz_name, items in groups.items():
        _schedule_group(db, items, tz_name, config)

    if campaign.status == DeliveryCampaignStatus.DRAFT:
        campaign.status = DeliveryCampaignStatus.ACTIVE
    db.commit()
    db.refresh(campaign)
    return campaign


def _schedule_group(db: Session, items: list[DeliveryQueueItem], tz_name: str, config: _ResolvedSchedulingConfig) -> None:
    remaining = list(items)
    current_date = datetime.now(dt_timezone.utc).astimezone(dt_timezone.utc).date()
    days_tried = 0

    while remaining and days_tried < _MAX_SCHEDULING_DAYS:
        days_tried += 1
        window_start_utc, window_end_utc = local_window_to_utc(current_date, config.window_start, config.window_end, tz_name)

        effective_start = max(window_start_utc, _now())
        if effective_start < window_end_utc:
            day_quota = config.daily_limit if config.daily_limit is not None else len(remaining)
            count_for_day = min(len(remaining), day_quota)
            times = generate_send_times(
                effective_start,
                window_end_utc,
                count_for_day,
                config.min_gap_seconds,
                config.max_gap_seconds,
                hourly_limit=config.hourly_limit,
            )
            for item, send_at in zip(remaining, times):
                item.status = DeliveryQueueItemStatus.SCHEDULED
                item.scheduled_send_at = send_at
                _log_event(db, item.id, DeliveryEventType.SCHEDULED, detail={"scheduled_send_at": send_at.isoformat(), "timezone_group": tz_name})
            remaining = remaining[len(times):]

        current_date = current_date + timedelta(days=1)


def pause_campaign(db: Session, campaign_id: uuid.UUID) -> DeliveryCampaign:
    campaign = _get_campaign_or_raise(db, campaign_id)
    campaign.status = DeliveryCampaignStatus.PAUSED
    db.commit()
    db.refresh(campaign)
    return campaign


def resume_campaign(db: Session, campaign_id: uuid.UUID) -> DeliveryCampaign:
    campaign = _get_campaign_or_raise(db, campaign_id)
    campaign.status = DeliveryCampaignStatus.ACTIVE
    db.commit()
    db.refresh(campaign)
    return campaign


def cancel_campaign(db: Session, campaign_id: uuid.UUID) -> DeliveryCampaign:
    campaign = _get_campaign_or_raise(db, campaign_id)
    active_items = db.scalars(
        select(DeliveryQueueItem).where(
            DeliveryQueueItem.delivery_campaign_id == campaign.id,
            DeliveryQueueItem.status.in_(
                [DeliveryQueueItemStatus.QUEUED, DeliveryQueueItemStatus.SCHEDULED, DeliveryQueueItemStatus.RETRY]
            ),
        )
    ).all()
    for item in active_items:
        item.status = DeliveryQueueItemStatus.CANCELLED
        item.cancelled_reason = "Campaign cancelled"
        _log_event(db, item.id, DeliveryEventType.CANCELLED, detail={"reason": "campaign_cancelled"})
    campaign.status = DeliveryCampaignStatus.CANCELLED
    db.commit()
    db.refresh(campaign)
    return campaign


def maybe_mark_completed(db: Session, campaign_id: uuid.UUID) -> None:
    """Called by dispatch_service after a queue item reaches a terminal
    state - if every sibling item is now terminal too, flips the campaign
    to COMPLETED so the UI reflects real state without a human having to
    notice and mark it manually."""
    campaign = db.get(DeliveryCampaign, campaign_id)
    if campaign is None or campaign.status in (DeliveryCampaignStatus.COMPLETED, DeliveryCampaignStatus.CANCELLED):
        return
    non_terminal_count = db.scalar(
        select(func.count()).select_from(DeliveryQueueItem).where(
            DeliveryQueueItem.delivery_campaign_id == campaign_id,
            DeliveryQueueItem.status.in_(
                [DeliveryQueueItemStatus.QUEUED, DeliveryQueueItemStatus.SCHEDULED, DeliveryQueueItemStatus.SENDING, DeliveryQueueItemStatus.RETRY]
            ),
        )
    )
    if non_terminal_count == 0:
        campaign.status = DeliveryCampaignStatus.COMPLETED
        db.commit()


def _get_campaign_or_raise(db: Session, campaign_id: uuid.UUID) -> DeliveryCampaign:
    campaign = db.get(DeliveryCampaign, campaign_id)
    if campaign is None:
        raise CampaignServiceError(f"DeliveryCampaign {campaign_id} not found")
    return campaign
