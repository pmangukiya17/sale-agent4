from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, UUIDPrimaryKeyMixin


class Industry(UUIDPrimaryKeyMixin, Base):
    """Reference list of industries a business operates in.

    A plain reference table rather than a hardcoded Python enum, so adding a
    new industry is a data change (INSERT), not a code deploy.
    """

    __tablename__ = "industries"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
