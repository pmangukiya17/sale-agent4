"""
OutreachContext: everything a ChannelProvider needs to render one draft,
assembled once per job. Outreach is a pure consumer of Personalization
(M3) - it never re-derives buyer_persona/buyer_readiness/communication
strategy/ranked strategies, only reads the current PersonalizationSnapshot
and its children. It also never touches raw Research evidence
(RawDocument) directly, and never touches CRM Company/Contact/Thread -
addressing is via the existing (M1) ProspectContact only.
"""
from dataclasses import dataclass, field

from app.models.brand_email_signature import BrandEmailSignature
from app.models.communication_strategy import CommunicationStrategy
from app.models.company_profile import CompanyProfile
from app.models.outreach_playbook import OutreachPlaybook
from app.models.personalization_snapshot import PersonalizationSnapshot
from app.models.personalization_strategy import PersonalizationStrategy
from app.models.prompt_version import PromptVersion
from app.models.prospect import Prospect
from app.models.prospect_contact import ProspectContact


@dataclass
class OutreachContext:
    prospect: Prospect
    prospect_contact: ProspectContact
    company_profile: CompanyProfile
    outreach_playbook: OutreachPlaybook
    prompt_version: PromptVersion
    # None if Personalization has never run for this prospect - the
    # provider must handle this gracefully (low confidence, generic
    # fallback content), same "no exception for insufficient information"
    # contract as PersonalizationEngine.synthesize.
    personalization_snapshot: PersonalizationSnapshot | None
    communication_strategy: CommunicationStrategy | None = None
    strategies: list[PersonalizationStrategy] = field(default_factory=list)
    # Business Branding: the business's own signature, read live (this row
    # is mutable-in-place, never versioned - see BrandEmailSignature's
    # docstring). A channel provider decides for itself whether/how to use
    # this - it is never forced into the rendered body. None if the
    # business has no signature configured yet.
    business_email_signature: BrandEmailSignature | None = None
