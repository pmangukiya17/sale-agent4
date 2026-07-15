import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ProductStatus


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One product a CompanyProfile sells. Unlimited products per business."""

    __tablename__ = "products"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    hs_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Placeholder only - no upload pipeline yet. Holds URLs once one exists.
    image_urls: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        Enum(
            ProductStatus,
            name="product_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ProductStatus.ACTIVE,
        nullable=False,
    )

    # e.g. ["Apparel", "Home Furnishing"] - free tags, not a fixed taxonomy
    applications: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Arbitrary technical key/value data (GSM, width, composition, ...).
    # Deliberately schema-less: unlike buyer types/industries/countries this
    # isn't a fixed enumerable set, it varies per product category.
    specifications: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    packaging: Mapped[str | None] = mapped_column(String(500), nullable=True)
    moq: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lead_time: Mapped[str | None] = mapped_column(String(255), nullable=True)
    production_capacity: Mapped[str | None] = mapped_column(String(500), nullable=True)

    company_profile: Mapped["CompanyProfile"] = relationship(back_populates="products")
