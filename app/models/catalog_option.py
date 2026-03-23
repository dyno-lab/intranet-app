from sqlalchemy import String, Boolean, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CatalogOption(Base):
    __tablename__ = "catalog_options"

    catalog_option_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    catalog_type_id: Mapped[int] = mapped_column(ForeignKey("catalog_types.catalog_type_id"), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(150), nullable=False)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
