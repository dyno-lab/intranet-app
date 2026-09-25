import re
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.community_catalog import CPCatalogType, CPCatalogOption, CPProfileField, CPProfileValue

CATEGORY_FIELDS = {
    "escolaridad_participante": ("Escolaridad", 150), "composicion_familiar": ("Composición familiar", 100),
    "grupo_familiar": ("Grupo familiar", 20), "fuente_ingreso_principal": ("Fuente de ingreso principal", 100),
    "rango_ingreso": ("Rango de ingreso", 30), "relacion_familiar": ("Relación familiar", 100),
    "estatus": ("Estatus", 50), "pueblo": ("Pueblo", 100),
}


def form_catalogs(db: Session, participant_id: int | None = None) -> dict:
    options = {key: [] for key in db.scalars(select(CPCatalogType.field_key))}
    for catalog, option in db.execute(select(CPCatalogType, CPCatalogOption).join(
        CPCatalogOption, CPCatalogOption.catalog_type_id == CPCatalogType.catalog_type_id
    ).where(CPCatalogOption.is_active == True).order_by(CPCatalogOption.value)):  # noqa: E712
        options.setdefault(catalog.field_key, []).append(option.value)
    fields = db.scalars(select(CPProfileField).where(CPProfileField.is_active == True).order_by(  # noqa: E712
        CPProfileField.sort_order, CPProfileField.label)).all()
    values = dict(db.execute(select(CPProfileValue.field_id, CPProfileValue.value).where(
        CPProfileValue.participant_id == participant_id)).all()) if participant_id else {}
    return {"catalog_options": options, "profile_fields": fields, "profile_values": values}


def validate_categories(db: Session, values: dict, participant=None) -> None:
    options = form_catalogs(db)["catalog_options"]
    for key, choices in options.items():
        value = (values.get(key) or "").strip()
        if value and value not in choices and (participant is None or value != getattr(participant, key, None)):
            raise ValueError(f"Seleccione una opción vigente para {CATEGORY_FIELDS[key][0]}.")


def save_profile_values(db: Session, participant_id: int, form) -> None:
    validated = []
    for field in db.scalars(select(CPProfileField).where(CPProfileField.is_active == True)):  # noqa: E712
        value = str(form.get(f"profile_{field.field_id}", "")).strip()
        if field.is_required and not value:
            raise ValueError(f"{field.label} es requerido.")
        if len(value) > 2000:
            raise ValueError(f"{field.label} admite hasta 2000 caracteres.")
        if value and field.field_type == "phone" and not re.fullmatch(r"\(\d{3}\)-\d{3}-\d{4}", value):
            raise ValueError(f"{field.label}: use (XXX)-XXX-XXXX.")
        if value and field.field_type == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError(f"{field.label}: correo inválido.")
        validated.append((field.field_id, value))
    for field_id, value in validated:
        existing = db.get(CPProfileValue, (participant_id, field_id))
        if existing is None:
            db.add(CPProfileValue(participant_id=participant_id, field_id=field_id, value=value))
        else:
            existing.value = value
    db.flush()
