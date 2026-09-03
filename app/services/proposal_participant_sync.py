from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.participant import Participant
    from app.models.proposal_participant import ProposalParticipant


PROPOSAL_PARTICIPANT_SYNC_FIELDS: tuple[str, ...] = (
    "nombre",
    "inicial",
    "apellido_paterno",
    "apellido_materno",
    "genero",
    "fecha_nacimiento",
    "exp_year",
    "exp_employee_initials",
    "exp_seq4",
    "expediente_num",
    "edificio",
    "apart",
    "vca",
    "primera_vez",
    "escolaridad_participante",
    "composicion_familiar",
    "relacion_familiar",
    "estatus",
    "grupo_familiar",
    "fuente_ingreso_principal",
    "rango_ingreso",
    "is_head_of_household",
    "is_active",
)

_BOOLEAN_SYNC_FIELDS = frozenset({"is_head_of_household", "is_active"})


def _core_update_value(field_name: str, value: object) -> object | None:
    if field_name in _BOOLEAN_SYNC_FIELDS:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if field_name == "fecha_nacimiento" and isinstance(value, datetime):
        return value.date()
    return value


def _normalized_comparison_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def get_proposal_participant_update_values(
    participant: Participant,
) -> dict[str, object | None]:
    """Build normalized values suitable for a ProposalParticipant Core UPDATE."""
    return {
        field_name: _core_update_value(field_name, getattr(participant, field_name))
        for field_name in PROPOSAL_PARTICIPANT_SYNC_FIELDS
    }


def get_different_proposal_participant_fields(
    proposal_participant: ProposalParticipant,
    participant: Participant,
) -> list[str]:
    """Return snapshot fields whose values differ from the Participant source."""
    source_values = get_proposal_participant_update_values(participant)
    return [
        field_name
        for field_name in PROPOSAL_PARTICIPANT_SYNC_FIELDS
        if _normalized_comparison_value(getattr(proposal_participant, field_name))
        != _normalized_comparison_value(source_values[field_name])
    ]
