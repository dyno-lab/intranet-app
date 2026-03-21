from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_db
from app.models.attendance import Attendance

router = APIRouter()


@router.get("")
def list_attendance(session_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Attendance)
    if session_id:
        stmt = stmt.where(Attendance.session_id == session_id)
    return list(db.execute(stmt).scalars().all())
