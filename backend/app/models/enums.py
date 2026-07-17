import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"


class PipelineStage(str, enum.Enum):
    DISCOVERED = "discovered"
    ENRICHED = "enriched"
    VERIFIED = "verified"
    WEBSITE_ANALYZED = "website_analyzed"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"
    CONTACT_FOUND = "contact_found"
    DRAFT_GENERATED = "draft_generated"
    PENDING_APPROVAL = "pending_approval"
    SENT = "sent"
    REPLIED = "replied"
    NO_REPLY = "no_reply"
    FOLLOW_UP_1 = "follow_up_1"
    FOLLOW_UP_2 = "follow_up_2"
    FOLLOW_UP_3 = "follow_up_3"
    WON = "won"
    LOST = "lost"
    NURTURE = "nurture"


class MessageDirection(str, enum.Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class FollowUpStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    CANCELLED = "cancelled"


class ProductStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class SearchDepth(str, enum.Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class SearchFrequency(str, enum.Enum):
    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"


class DateFormat(str, enum.Enum):
    DD_MM_YYYY = "DD/MM/YYYY"
    MM_DD_YYYY = "MM/DD/YYYY"
    YYYY_MM_DD = "YYYY-MM-DD"


class TimeFormat(str, enum.Enum):
    H12 = "12h"
    H24 = "24h"


class DiscoveryJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProspectStatus(str, enum.Enum):
    NEW = "new"
    DUPLICATE_REVIEW = "duplicate_review"
    SCORED = "scored"
    QUALIFIED = "qualified"
    UNQUALIFIED = "unqualified"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class DecisionMakerLevel(str, enum.Enum):
    FINAL_DECISION_MAKER = "final_decision_maker"
    INFLUENCER = "influencer"
    GATEKEEPER = "gatekeeper"
    UNKNOWN = "unknown"


# --- M2: AI Research & Prospect Intelligence --------------------------------
# A separate status enum from DiscoveryJobStatus, even though the values
# start identical - Research is a deliberately independent domain (per the
# approved M2 design) and sharing a Postgres type would couple the two.


class ResearchJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AIAnalysisType(str, enum.Enum):
    COMPANY_PROFILE = "company_profile"
    BUYER_PROFILE = "buyer_profile"
    BUSINESS_SIGNALS = "business_signals"
    SALES_INTELLIGENCE = "sales_intelligence"


class SignalStatus(str, enum.Enum):
    NEW = "new"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"


class SignalImportance(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SignalUrgency(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IMMEDIATE = "immediate"


class RecommendationType(str, enum.Enum):
    PRODUCT_FIT = "product_fit"
    SALES_ANGLE = "sales_angle"
    TALKING_POINT = "talking_point"
    OBJECTION_HANDLING = "objection_handling"
    RISK_MITIGATION = "risk_mitigation"
    # Added in M3 - Personalization writes these when it identifies a good
    # call-to-action; kept in the SAME table/enum as M2's other recommendation
    # types rather than a new "Personalization Recommendation" concept, so
    # there is exactly one canonical "atomic tactical idea" store across
    # M2 and M3.
    CALL_TO_ACTION = "call_to_action"


class RecommendationStatus(str, enum.Enum):
    NEW = "new"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


# --- M3: AI Personalization Engine ------------------------------------------
# Personalization is a pure synthesis domain - it reads what Discovery (M1)
# and Research (M2) already produced and never re-derives facts. A separate
# status enum from ResearchJobStatus/DiscoveryJobStatus, same independent-
# domain precedent as before. No PARTIALLY_COMPLETED value here: unlike
# Discovery/Research there is no provider fan-out to partially fail - a
# single synchronous synthesis pass either completes or fails outright.


class PersonalizationJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BuyerReadinessLevel(str, enum.Enum):
    """AI prediction, recalculated every time Personalization runs - how
    receptive/ready this buyer currently seems, inferred from Signals.
    Deliberately distinct from RelationshipStage (actual sales history)."""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    READY_TO_ENGAGE = "ready_to_engage"


class RelationshipStage(str, enum.Enum):
    """Actual sales history with this buyer - lives on Prospect as a live,
    mutable field (NOT versioned/frozen like BuyerReadinessLevel). M3 only
    ever reads this value; M4-M7 are what advance it as outreach happens."""

    COLD = "cold"
    CONTACTED = "contacted"
    ENGAGED = "engaged"
    QUALIFIED = "qualified"
    NEGOTIATION = "negotiation"


class PersonalizationStrategyRank(str, enum.Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    FALLBACK = "fallback"


class CommunicationFormality(str, enum.Enum):
    CASUAL = "casual"
    NEUTRAL = "neutral"
    FORMAL = "formal"


class CommunicationIntensityLevel(str, enum.Enum):
    """Shared 3-level scale reused across directness/warmth/technical_depth/
    authority/consultative_level/urgency on CommunicationStrategy - these
    are all "how much of this trait" axes, so one enum type serves all six
    columns rather than six near-identical enums."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CommunicationLength(str, enum.Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


# --- M4: AI Outreach Generation Engine ---------------------------------------
# Outreach is a pure consumer of Personalization (M3), same "independent
# domain, own status enum" precedent as Research-vs-Discovery and
# Personalization-vs-Research. No PARTIALLY_COMPLETED value, same reasoning
# as PersonalizationJobStatus: one synchronous render pass, no provider
# fan-out to partially fail.


class PersonalizationScope(str, enum.Enum):
    """Whether a PersonalizationSnapshot's strategy read is for the whole
    account (Prospect) or one specific named stakeholder (ProspectContact).
    M3/M4 only ever produce ACCOUNT-scoped snapshots - CONTACT is added now,
    unused, so a future per-stakeholder personalization upgrade needs no
    schema change. Lives on PersonalizationSnapshot, not here for M4's own
    entities - Outreach never redefines what Personalization already owns."""

    ACCOUNT = "account"
    CONTACT = "contact"


class OutreachJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutreachDraftStatus(str, enum.Enum):
    """Per-draft-version approval lifecycle - deliberately NOT the same
    thing as Prospect.relationship_stage (account-level sales history) or
    the CRM's PipelineStage (dormant until a Prospect->Company import
    exists). SUPERSEDED is distinct from simply "not is_current": it
    records that a specific version was actively replaced by a
    regeneration, vs. one that was just never promoted."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class OutreachBlockBehavior(str, enum.Enum):
    """How a single OutreachBlock is rendered. FIXED content is copied
    verbatim (never reworded by the AI, though a channel provider may still
    reformat its presentation). AI_ASSISTED lightly personalizes existing
    wording. AI_GENERATED is written fresh from ai_guidance + the buyer's
    PersonalizationSnapshot context."""

    FIXED = "fixed"
    AI_ASSISTED = "ai_assisted"
    AI_GENERATED = "ai_generated"
