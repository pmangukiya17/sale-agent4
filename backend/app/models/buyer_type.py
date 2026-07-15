from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, UUIDPrimaryKeyMixin


class BuyerType(UUIDPrimaryKeyMixin, Base):
    """Reference list of buyer categories (Importers, Distributors, ...).

    A plain reference table rather than a hardcoded Python enum, so adding a
    new buyer type is a data change (INSERT), not a code deploy.
    """

    __tablename__ = "buyer_types"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
