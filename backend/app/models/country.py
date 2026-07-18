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

    # Added in M5. Prospect/ProspectContact.timezone are IANA strings but
    # are almost always null in practice - nothing before M5 ever populates
    # them. default_timezone is the fallback the Delivery timezone resolver
    # uses when a contact has no explicit timezone: this country's single
    # most common IANA zone (e.g. "Europe/Berlin" for DE). timezone_note
    # documents the caveat in plain text for multi-timezone countries (e.g.
    # US, RU, AU, BR) where one default is necessarily an approximation -
    # kept as a note rather than a structured region-timezone table, since
    # nothing today resolves finer than country-level anyway.
    default_timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timezone_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
