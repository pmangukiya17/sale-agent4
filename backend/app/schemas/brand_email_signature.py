import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BrandEmailSignatureUpdate(BaseModel):
    """
    signature_plain_text is deliberately NOT accepted here - it is always
    server-derived from signature_html (see app/branding/plain_text.py) so
    it can never drift out of sync with what the client actually saved.
    """

    signature_html: str | None = None
    is_active: bool = True


class BrandEmailSignatureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_profile_id: uuid.UUID
    signature_html: str | None
    signature_plain_text: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
