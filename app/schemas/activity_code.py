from pydantic import BaseModel, Field

class ActivityCodeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool = True

class ActivityCodeOut(BaseModel):
    activity_code_id: int
    code: str
    description: str | None
    is_active: bool

    class Config:
        from_attributes = True