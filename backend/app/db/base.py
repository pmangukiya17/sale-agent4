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
from app.models.research_template import ResearchTemplate  # noqa
from app.models.research_request import ResearchRequest  # noqa
from app.models.research_job import ResearchJob  # noqa
from app.models.research_job_provider_run import ResearchJobProviderRun  # noqa
from app.models.research_source import ResearchSource  # noqa
from app.models.raw_document import RawDocument  # noqa
from app.models.research_associations import ai_analysis_source_documents  # noqa
from app.models.ai_analysis import AIAnalysis  # noqa
from app.models.intelligence_snapshot import IntelligenceSnapshot  # noqa
from app.models.signal import Signal  # noqa
from app.models.signal_evidence import SignalEvidence  # noqa
from app.models.recommendation import Recommendation  # noqa
from app.models.recommendation_evidence import RecommendationEvidence  # noqa
from app.models.research_report import ResearchReport  # noqa
from app.models.research_run import ResearchRun  # noqa
from app.models.personalization_template import PersonalizationTemplate  # noqa
from app.models.personalization_request import PersonalizationRequest  # noqa
from app.models.personalization_job import PersonalizationJob  # noqa
from app.models.personalization_run import PersonalizationRun  # noqa
from app.models.personalization_snapshot import PersonalizationSnapshot  # noqa
from app.models.communication_strategy import CommunicationStrategy  # noqa
from app.models.personalization_strategy import PersonalizationStrategy  # noqa
from app.models.personalization_evidence import PersonalizationEvidence  # noqa
from app.models.outreach_playbook import OutreachPlaybook  # noqa
from app.models.outreach_block import OutreachBlock  # noqa
from app.models.prompt_version import PromptVersion  # noqa
from app.models.outreach_request import OutreachRequest  # noqa
from app.models.outreach_job import OutreachJob  # noqa
from app.models.outreach_run import OutreachRun  # noqa
from app.models.outreach_draft import OutreachDraft  # noqa
from app.models.outreach_edit import OutreachEdit  # noqa
from app.models.outreach_evidence import OutreachEvidence  # noqa
from app.models.brand_email_signature import BrandEmailSignature  # noqa
from app.models.provider_connection import ProviderConnection  # noqa
from app.models.provider_credential import ProviderCredential  # noqa
from app.models.sending_profile import SendingProfile  # noqa
from app.models.delivery_campaign import DeliveryCampaign  # noqa
from app.models.delivery_queue_item import DeliveryQueueItem  # noqa
from app.models.delivery_event import DeliveryEvent  # noqa
from app.models.conversation import Conversation  # noqa
from app.models.email_message import EmailMessage  # noqa
from app.models.conversation_participant import ConversationParticipant  # noqa
from app.models.mailbox_sync_state import MailboxSyncState  # noqa
from app.models.attachment import Attachment  # noqa
from app.models.workflow_event import Event  # noqa
from app.models.workflow_definition import WorkflowDefinition  # noqa
from app.models.workflow_instance import WorkflowInstance  # noqa
from app.models.workflow_step_invocation import WorkflowStepInvocation  # noqa
from app.models.event_consumption import EventConsumption  # noqa
from app.models.notification import Notification, NotificationDispatch  # noqa
from app.models.task import Task  # noqa
from app.models.opportunity import Opportunity  # noqa
from app.models.opportunity_stage_history import OpportunityStageHistory  # noqa
from app.models.mailbox_brief import MailboxBrief  # noqa
from app.models.ai_request_log import AIRequestLog  # noqa
from app.models.ai_provider_config import AIProviderConfig  # noqa
from app.models.ai_provider_config_audit import AIProviderConfigAudit  # noqa
