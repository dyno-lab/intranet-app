from datetime import date
from pydantic import BaseModel


class SessionCreate(BaseModel):
    session_date: date
    activity_code_id: int
    employee_id: int
    hours: float | None = None


class SessionOut(BaseModel):
    session_id: int
    session_date: date
    activity_code_id: int
    employee_id: int
    hours: float | None

    class Config:
        from_attributes = True
