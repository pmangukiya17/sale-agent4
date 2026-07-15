"""
Import every model here so that Alembic's autogenerate can discover them
via Base.metadata, without each module needing to know about the others.
"""
from app.db.base_class import Base  # noqa
from app.models.user import User  # noqa
from app.models.company import Company  # noqa
from app.models.contact import Contact  # noqa
from app.models.website_finding import WebsiteFinding  # noqa
from app.models.icp_criteria import ICPCriteria  # noqa
from app.models.thread import Thread  # noqa
from app.models.message import Message  # noqa
from app.models.followup import FollowUp  # noqa
from app.models.audit_log import AuditLog  # noqa
