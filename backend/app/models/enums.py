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
