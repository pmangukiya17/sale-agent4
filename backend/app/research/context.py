"""
ResearchContext: everything a research provider or the AI Analysis Engine
needs to do its job, assembled once per job and handed uniformly to every
enabled provider/engine - the exact same "assemble once, pass everywhere"
shape as DiscoveryContext (M1). prospect is the one thing Discovery's
context never needed (Discovery searches for prospects; Research always
enriches one specific, already-existing prospect).
"""
from dataclasses import dataclass, field

from app.models.company_profile import CompanyProfile
from app.models.knowledge_base import KnowledgeBase
from app.models.product import Product
from app.models.prospect import Prospect


@dataclass
class ResearchContext:
    prospect: Prospect
    company_profile: CompanyProfile
    products: list[Product] = field(default_factory=list)
    knowledge_base_entries: list[KnowledgeBase] = field(default_factory=list)
