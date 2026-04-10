from datetime import datetime

from pydantic import BaseModel

from app.schemas.person import PersonOut


class ProposalParticipantCreate(BaseModel):
    proposal_id: int
    person_id: int
    created_by_user_id: int | None = None
    exp_year: int | None = None
    exp_employee_initials: str | None = None
    exp_seq4: str | None = None
    expediente_num: str | None = None
    edificio: str | None = None
    apart: str | None = None
    vca: str | None = None
    primera_vez: str | None = None
    composicion_familiar: str | None = None
    estatus: str | None = None
    grupo_familiar: str | None = None
    fuente_ingreso_principal: str | None = None
    rango_ingreso: str | None = None
    is_active: bool = True


class ProposalParticipantOut(BaseModel):
    proposal_participant_id: int
    proposal_id: int
    person_id: int
    created_by_user_id: int | None = None
    exp_year: int | None = None
    exp_employee_initials: str | None = None
    exp_seq4: str | None = None
    expediente_num: str | None = None
    edificio: str | None = None
    apart: str | None = None
    vca: str | None = None
    primera_vez: str | None = None
    composicion_familiar: str | None = None
    estatus: str | None = None
    grupo_familiar: str | None = None
    fuente_ingreso_principal: str | None = None
    rango_ingreso: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProposalParticipantDetailOut(ProposalParticipantOut):
    person: PersonOut | None = None
