from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, UUIDPrimaryKeyMixin


class Language(UUIDPrimaryKeyMixin, Base):
    """Reference list of languages (ISO 639-1 codes), seeded via migration data."""

    __tablename__ = "languages"

    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
