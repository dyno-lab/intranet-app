from pydantic import BaseModel, Field


class AttendanceMark(BaseModel):
    session_id: int
    participant_id: int | None = None
    proposal_participant_id: int | None = None
    attended: bool = True
    marked_by: str | None = Field(default=None, max_length=100)


class AttendanceBulk(BaseModel):
    session_id: int
    participant_ids: list[int] = []
    proposal_participant_ids: list[int] = []
    attended: bool = True
    marked_by: str | None = Field(default=None, max_length=100)