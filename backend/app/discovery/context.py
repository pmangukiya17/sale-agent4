"""
DiscoveryContext: everything a provider plugin needs to run a search,
assembled once per job and handed uniformly to every enabled provider.
Products are read directly from the CompanyProfile (all active ones) -
there is deliberately no per-search product selection; the ICP is what
governs targeting, the product catalog is a business-level fact.
"""
from dataclasses import dataclass, field

from app.models.company_profile import CompanyProfile
from app.models.icp_criteria import ICPCriteria
from app.models.knowledge_base import KnowledgeBase
from app.models.product import Product


@dataclass
class DiscoveryContext:
    company_profile: CompanyProfile
    icp: ICPCriteria
    products: list[Product] = field(default_factory=list)
    knowledge_base_entries: list[KnowledgeBase] = field(default_factory=list)
