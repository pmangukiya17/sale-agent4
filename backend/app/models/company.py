from sqlalchemy import Enum, Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PipelineStage


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Where this lead was discovered, e.g. 'manual', 'trade_data'"
    )
    legitimacy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    icp_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    stage: Mapped[PipelineStage] = mapped_column(
        Enum(
            PipelineStage,
            name="pipeline_stage",
            # Same fix as User.role: bind the enum's lowercase VALUE, not
            # its uppercase NAME, to match the Postgres type from migration 0001.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=PipelineStage.DISCOVERED,
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    contacts: Mapped[list["Contact"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    website_findings: Mapped[list["WebsiteFinding"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    threads: Mapped[list["Thread"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    followups: Mapped[list["FollowUp"]] = relationship(back_populates="company", cascade="all, delete-orphan")
