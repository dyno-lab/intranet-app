from sqlalchemy import Boolean, ForeignKey, Integer, String, Unicode, UnicodeText, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class CPCatalogType(Base):
    __tablename__ = "cp_catalog_types"
    catalog_type_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    field_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    defaults_loaded: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)


class CPCatalogOption(Base):
    __tablename__ = "cp_catalog_options"
    __table_args__ = (UniqueConstraint("catalog_type_id", "value", name="UQ_cp_catalog_value"),)
    option_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    catalog_type_id: Mapped[int] = mapped_column(ForeignKey("cp_catalog_types.catalog_type_id"), nullable=False)
    value: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    label: Mapped[str | None] = mapped_column(Unicode(150))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)


class CPProfileField(Base):
    __tablename__ = "cp_profile_fields"
    __table_args__ = (CheckConstraint("field_type IN ('text','email','phone')", name="CK_cp_profile_type"),)
    field_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    field_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)


class CPProfileValue(Base):
    __tablename__ = "cp_profile_values"
    participant_id: Mapped[int] = mapped_column(ForeignKey("cp_participants.participant_id"), primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("cp_profile_fields.field_id"), primary_key=True)
    value: Mapped[str] = mapped_column(UnicodeText, nullable=False)
