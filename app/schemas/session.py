from datetime import date
from pydantic import BaseModel, Field

class SessionCreate(BaseModel):
    session_date: date
    activity_code_id: int
    employee_id: int
    hours: float | None = None
    notes: str | None = Field(default=None, max_length=255)

class SessionOut(BaseModel):
    session_id: int
    session_date: date
    activity_code_id: int
    employee_id: int
    hours: float | None
    notes: str | None

    class Config:
        from_attributes = True