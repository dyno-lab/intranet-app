from datetime import date, datetime

from pydantic import BaseModel


class PersonCreate(BaseModel):
    nombre: str
    inicial: str | None = None
    apellido_paterno: str
    apellido_materno: str | None = None
    genero: str | None = None
    fecha_nacimiento: date | None = None


class PersonOut(BaseModel):
    person_id: int
    nombre: str
    inicial: str | None = None
    apellido_paterno: str
    apellido_materno: str | None = None
    genero: str | None = None
    fecha_nacimiento: date | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
