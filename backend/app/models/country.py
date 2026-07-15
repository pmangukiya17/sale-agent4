from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, UUIDPrimaryKeyMixin


class Country(UUIDPrimaryKeyMixin, Base):
    """Reference list of countries, seeded via migration data (not hardcoded
    in application code) so new regions/countries are a data change, not a
    code deploy. Used by ICP target markets / excluded countries.
    """

    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String(4), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
