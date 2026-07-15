import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DateFormat, TimeFormat


class WorkspaceSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Account-level defaults, one row per user. Sits above any individual
    CompanyProfile (a user can own several businesses) - these are just the
    defaults a new CompanyProfile is pre-filled from, not a hard constraint
    on it. owner_user_id is unique now (one settings row per user); if a
    real multi-user "Organization" entity is introduced later, this FK can
    be repointed there instead of redesigning the table.
    """

    __tablename__ = "workspace_settings"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    default_timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    default_language_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("languages.id", ondelete="SET NULL"), nullable=True
    )
    default_currency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("currencies.id", ondelete="SET NULL"), nullable=True
    )
    date_format: Mapped[DateFormat] = mapped_column(
        Enum(
            DateFormat,
            name="date_format",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=DateFormat.YYYY_MM_DD,
        nullable=False,
    )
    time_format: Mapped[TimeFormat] = mapped_column(
        Enum(
            TimeFormat,
            name="time_format",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=TimeFormat.H24,
        nullable=False,
    )

    default_language: Mapped["Language | None"] = relationship(foreign_keys=[default_language_id])
    default_currency: Mapped["Currency | None"] = relationship(foreign_keys=[default_currency_id])
