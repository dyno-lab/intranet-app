from pydantic import BaseModel, Field

class EmployeeCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    employee_code: str | None = Field(default=None, max_length=50)
    is_active: bool = True

class EmployeeOut(BaseModel):
    employee_id: int
    full_name: str
    employee_code: str | None
    is_active: bool

    class Config:
        from_attributes = True