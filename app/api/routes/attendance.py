from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import date

from app.db.session import SessionLocal
from app.models.activity_session import ActivitySession
from app.models.activity_code import ActivityCode
from app.models.employee import Employee
from app.schemas.session import SessionCreate, SessionOut

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("", response_model=list[SessionOut])
def list_sessions(from_date: date | None = None, to_date: date | None = None, db: Session = Depends(get_db)):
    stmt = select(ActivitySession)
    if from_date:
        stmt = stmt.where(ActivitySession.session_date >= from_date)
    if to_date:
        stmt = stmt.where(ActivitySession.session_date <= to_date)
    stmt = stmt.order_by(ActivitySession.session_date.desc())
    return list(db.execute(stmt).scalars().all())

@router.post("", response_model=SessionOut)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)):
    # Validar FKs
    code = db.get(ActivityCode, payload.activity_code_id)
    if not code:
        raise HTTPException(status_code=404, detail="activity_code_id no existe")

    emp = db.get(Employee, payload.employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="employee_id no existe")

    obj = ActivitySession(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj