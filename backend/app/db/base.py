"""
Import every model here so that Alembic's autogenerate can discover them
via Base.metadata, without each module needing to know about the others.
"""
from app.db.base_class import Base  # noqa
from app.models.user import User  # noqa
from app.models.associations import (  # noqa
    company_profile_industries,
    icp_criteria_excluded_countries,
    icp_criteria_languages,
    icp_criteria_target_buyer_types,
    icp_criteria_target_markets,
)
from app.models.buyer_type import BuyerType  # noqa
from app.models.industry import Industry  # noqa
from app.models.country import Country  # noqa
from app.models.language import Language  # noqa
from app.models.currency import Currency  # noqa
from app.models.company_profile import CompanyProfile  # noqa
from app.models.product import Product  # noqa
from app.models.company import Company  # noqa
from app.models.contact import Contact  # noqa
from app.models.website_finding import WebsiteFinding  # noqa
from app.models.icp_criteria import ICPCriteria  # noqa
from app.models.knowledge_base import KnowledgeBase  # noqa
from app.models.workspace_settings import WorkspaceSettings  # noqa
from app.models.thread import Thread  # noqa
from app.models.message import Message  # noqa
from app.models.followup import FollowUp  # noqa
from app.models.audit_log import AuditLog  # noqa
from app.models.search_template import SearchTemplate  # noqa
from app.models.discovery_search import DiscoverySearch  # noqa
from app.models.discovery_job import DiscoveryJob  # noqa
from app.models.discovery_job_provider_run import DiscoveryJobProviderRun  # noqa
from app.models.discovery_provider_result import DiscoveryProviderResult  # noqa
from app.models.discovery_run import DiscoveryRun  # noqa
from app.models.prospect import Prospect  # noqa
from app.models.prospect_contact import ProspectContact  # noqa
from app.models.prospect_source import ProspectSource  # noqa
from app.models.prospect_timeline_event import ProspectTimelineEvent  # noqa
