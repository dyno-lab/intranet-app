from datetime import date
from pydantic import BaseModel, Field

class ParticipantCreate(BaseModel):
    # FASE 1 (estable): expediente manual
    expediente_num: str | None = Field(default=None, min_length=1, max_length=50)

    # FASE 2: componentes del expediente FE-YYYY-XX-#### (generado en backend)
    exp_year: int | None = None
    exp_employee_initials: str | None = Field(default=None, max_length=10)
    exp_seq4: str | None = Field(default=None, max_length=4)

    nombre: str
    inicial: str | None = None
    apellido_paterno: str
    apellido_materno: str | None = None
    genero: str | None = None
    fecha_nacimiento: date | None = None
    edificio: str | None = None
    apart: str | None = None


class ParticipantOut(BaseModel):
    participant_id: int
    expediente_num: str
    nombre: str
    inicial: str | None
    apellido_paterno: str
    apellido_materno: str | None
    genero: str | None
    fecha_nacimiento: date | None
    edificio: str | None
    apart: str | None

    # FASE 2 (opcionales)
    exp_year: int | None = None
    exp_employee_initials: str | None = None
    exp_seq4: str | None = None

    class Config:
        from_attributes = True
