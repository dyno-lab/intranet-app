from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_db
from app.core.auth import get_current_user, is_admin_or_supervisor
from app.models.attendance import Attendance
from app.models.activity_session import ActivitySession
from app.models.user import User

router = APIRouter()


@router.get("")
def list_attendance(
    session_id: int | None = None,
    proposal_participant_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Attendance)
    if not is_admin_or_supervisor(current_user):
        stmt = stmt.join(ActivitySession, ActivitySession.session_id == Attendance.session_id).where(
            ActivitySession.created_by_user_id == current_user.user_id
        )
    if session_id:
        stmt = stmt.where(Attendance.session_id == session_id)
    if proposal_participant_id:
        stmt = stmt.where(Attendance.proposal_participant_id == proposal_participant_id)
    return list(db.execute(stmt).scalars().all())
