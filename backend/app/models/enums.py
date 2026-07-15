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
