from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.participant import Participant
from app.models.participant_profile_field import ParticipantProfileField
from app.models.participant_profile_field_value import ParticipantProfileFieldValue

VALID_FIELD_TYPES = {"text", "email", "phone"}
PHONE_REGEX = re.compile(r"^\(\d{3}\)-\d{3}-\d{4}$")
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_profile_field_key(value: str | None) -> str:
    text = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return "_".join(part for part in text.split("_") if part)


def load_active_new_list_fields(db: Session) -> list[ParticipantProfileField]:
    return db.execute(
        select(ParticipantProfileField)
        .where(
            ParticipantProfileField.applies_to_new_list == True,  # noqa: E712
            ParticipantProfileField.is_active == True,  # noqa: E712
        )
        .order_by(ParticipantProfileField.sort_order, ParticipantProfileField.label)
    ).scalars().all()


def load_all_profile_fields(db: Session) -> list[ParticipantProfileField]:
    return db.execute(
        select(ParticipantProfileField)
        .order_by(ParticipantProfileField.sort_order, ParticipantProfileField.label)
    ).scalars().all()


def load_participant_profile_values(db: Session, participant_id: int) -> dict[int, ParticipantProfileFieldValue]:
    rows = db.execute(
        select(ParticipantProfileFieldValue).where(ParticipantProfileFieldValue.participant_id == participant_id)
    ).scalars().all()
    return {row.participant_profile_field_id: row for row in rows}


def load_profile_field_presence_by_participants(
    db: Session,
    participant_ids: list[int],
    field_keys: list[str],
) -> dict[int, dict[str, bool]]:
    result = {
        participant_id: {field_key: False for field_key in field_keys}
        for participant_id in participant_ids
    }
    if not participant_ids or not field_keys:
        return result

    rows = db.execute(
        select(
            ParticipantProfileFieldValue.participant_id,
            ParticipantProfileField.field_key,
            ParticipantProfileFieldValue.value,
        )
        .join(
            ParticipantProfileField,
            ParticipantProfileField.participant_profile_field_id == ParticipantProfileFieldValue.participant_profile_field_id,
        )
        .where(
            ParticipantProfileFieldValue.participant_id.in_(participant_ids),
            ParticipantProfileField.field_key.in_(field_keys),
        )
    ).all()

    for participant_id, field_key, value in rows:
        if participant_id in result and field_key in result[participant_id]:
            result[participant_id][field_key] = bool((value or "").strip())

    return result


def build_profile_field_form_values(
    fields: list[ParticipantProfileField],
    stored_values: dict[int, ParticipantProfileFieldValue] | None = None,
) -> dict[int, str]:
    result: dict[int, str] = {}
    stored_values = stored_values or {}
    for field in fields:
        result[field.participant_profile_field_id] = (stored_values.get(field.participant_profile_field_id).value if stored_values.get(field.participant_profile_field_id) else "") or ""
    return result


def extract_profile_field_inputs(form_data: Any, fields: list[ParticipantProfileField]) -> dict[int, str]:
    values: dict[int, str] = {}
    for field in fields:
        raw_value = form_data.get(f"profile_field_{field.participant_profile_field_id}", "")
        values[field.participant_profile_field_id] = (raw_value or "").strip()
    return values


def validate_profile_field_inputs(fields: list[ParticipantProfileField], values: dict[int, str]) -> list[str]:
    errors: list[str] = []
    for field in fields:
        value = (values.get(field.participant_profile_field_id) or "").strip()
        if field.is_required and not value:
            errors.append(f"Error: El campo {field.label} es requerido.")
            continue
        if not value:
            continue

        field_type = (field.field_type or "text").strip().lower()
        if field_type == "phone" and not PHONE_REGEX.fullmatch(value):
            errors.append(f"Error: El campo {field.label} debe usar el formato (XXX)-XXX-XXXX.")
            continue
        if field_type == "email" and not EMAIL_REGEX.fullmatch(value):
            errors.append(f"Error: El campo {field.label} debe contener un email válido.")
            continue

        pattern = (field.validation_pattern or "").strip()
        if pattern:
            try:
                if not re.fullmatch(pattern, value):
                    errors.append(f"Error: El campo {field.label} no cumple el formato requerido.")
            except re.error:
                errors.append(f"Error: El patrón configurado para {field.label} no es válido.")
    return errors


def save_profile_field_values(
    db: Session,
    participant: Participant,
    fields: list[ParticipantProfileField],
    values: dict[int, str],
) -> None:
    existing = load_participant_profile_values(db, participant.participant_id)
    for field in fields:
        normalized_value = (values.get(field.participant_profile_field_id) or "").strip() or None
        current = existing.get(field.participant_profile_field_id)
        if current:
            current.value = normalized_value
            db.add(current)
        else:
            db.add(
                ParticipantProfileFieldValue(
                    participant_id=participant.participant_id,
                    participant_profile_field_id=field.participant_profile_field_id,
                    value=normalized_value,
                )
            )


def normalize_profile_field_type(value: str | None) -> str:
    normalized = (value or "text").strip().lower()
    return normalized if normalized in VALID_FIELD_TYPES else "text"
