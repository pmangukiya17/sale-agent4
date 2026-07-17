"""
PersonalizationContext: everything the PersonalizationEngine needs to
synthesize a strategy, assembled once per job. Unlike DiscoveryContext/
ResearchContext, this context contains NO external-provider inputs -
Personalization discovers nothing new. Every field here is something
Discovery (M1) or Research (M2) already produced; Personalization only
reads.
"""
from dataclasses import dataclass, field

from app.models.company_profile import CompanyProfile
from app.models.icp_criteria import ICPCriteria
from app.models.intelligence_snapshot import IntelligenceSnapshot
from app.models.knowledge_base import KnowledgeBase
from app.models.product import Product
from app.models.prospect import Prospect
from app.models.recommendation import Recommendation
from app.models.signal import Signal


@dataclass
class PersonalizationContext:
    prospect: Prospect
    company_profile: CompanyProfile
    # None if Research has never run for this prospect - the engine must
    # handle this gracefully (low confidence, not an exception).
    intelligence_snapshot: IntelligenceSnapshot | None
    signals: list[Signal] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    products: list[Product] = field(default_factory=list)
    icp: ICPCriteria | None = None
    knowledge_base_entries: list[KnowledgeBase] = field(default_factory=list)
