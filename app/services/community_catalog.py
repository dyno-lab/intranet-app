import re
import unicodedata
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.puerto_rico import MUNICIPALITIES
from app.models.catalog_type import CatalogType
from app.models.catalog_option import CatalogOption
from app.models.community_catalog import CPCatalogType, CPCatalogOption, CPProfileField, CPProfileValue

CATEGORY_FIELDS = {
    "escolaridad_participante": ("Escolaridad", 150), "composicion_familiar": ("Composición familiar", 100),
    "grupo_familiar": ("Grupo familiar", 20), "fuente_ingreso_principal": ("Fuente de ingreso principal", 100),
    "rango_ingreso": ("Rango de ingreso", 30), "relacion_familiar": ("Relación familiar", 100),
    "estatus": ("Estatus", 50), "pueblo": ("Pueblo", 100),
}


def _catalog_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.strip().lower().replace(" ", "_").replace("-", "_"))
    return "_".join(part for part in "".join(ch for ch in value if not unicodedata.combining(ch)).split("_") if part)


def seed_community_catalogs(db: Session) -> None:
    """Copy Faro's active choices once; never overwrite CP changes on restart.

    Called after both schemas exist, inside the schema caller's transaction.
    Existing CP options (including disabled choices) and saved values survive.
    """
    catalogs = {item.field_key: item for item in db.scalars(select(CPCatalogType).with_hint(
        CPCatalogType, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql"))}
    pending = [key for key in CATEGORY_FIELDS if key not in catalogs or not catalogs[key].defaults_loaded]
    if not pending:
        return
    source = {}
    for category, option in db.execute(select(CatalogType, CatalogOption).join(CatalogOption).where(
        CatalogType.is_active == True, CatalogOption.is_active == True,  # noqa: E712
    ).order_by(CatalogOption.sort_order, CatalogOption.label, CatalogOption.catalog_option_id)):
        source.setdefault(_catalog_key(category.key), []).append((option.value, option.label, option.sort_order))
    for key in pending:
        category = catalogs.get(key)
        if category is None:
            category = CPCatalogType(field_key=key, label=CATEGORY_FIELDS[key][0])
            db.add(category)
            db.flush()
        choices = ([(town, town, position) for position, town in enumerate(MUNICIPALITIES)]
                   if key == "pueblo" else source.get("estatus_participante" if key == "estatus" else key, []))
        existing = {option.value.casefold(): option for option in db.scalars(select(CPCatalogOption).where(
            CPCatalogOption.catalog_type_id == category.catalog_type_id))}
        for value, label, sort_order in choices:
            if value.casefold() not in existing:
                option = CPCatalogOption(catalog_type_id=category.catalog_type_id, value=value, label=label, sort_order=sort_order)
                db.add(option)
                existing[value.casefold()] = option
            elif existing[value.casefold()].label is None:
                # Upgrade pre-label CP options without reactivating them.
                existing[value.casefold()].label = label
                existing[value.casefold()].sort_order = sort_order
        category.defaults_loaded = True
    db.flush()


def form_catalogs(db: Session, participant_id: int | None = None) -> dict:
    options = {key: [] for key in db.scalars(select(CPCatalogType.field_key))}
    labels = {}
    for catalog, option in db.execute(select(CPCatalogType, CPCatalogOption).join(
        CPCatalogOption, CPCatalogOption.catalog_type_id == CPCatalogType.catalog_type_id
    ).where(CPCatalogOption.is_active == True).order_by(  # noqa: E712
        CPCatalogOption.sort_order, func.coalesce(CPCatalogOption.label, CPCatalogOption.value))):
        options.setdefault(catalog.field_key, []).append(option.value)
        labels.setdefault(catalog.field_key, {})[option.value] = option.label or option.value
    options.setdefault("pueblo", list(MUNICIPALITIES))
    fields = db.scalars(select(CPProfileField).where(CPProfileField.is_active == True).order_by(  # noqa: E712
        CPProfileField.sort_order, CPProfileField.label)).all()
    values = dict(db.execute(select(CPProfileValue.field_id, CPProfileValue.value).where(
        CPProfileValue.participant_id == participant_id)).all()) if participant_id else {}
    return {"catalog_options": options, "catalog_labels": labels, "profile_fields": fields, "profile_values": values}


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
