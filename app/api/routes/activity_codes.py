from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_db
from app.models.activity_code import ActivityCode
from app.schemas.activity_code import ActivityCodeCreate, ActivityCodeOut

router = APIRouter()

@router.get("", response_model=list[ActivityCodeOut])
def list_codes(active_only: bool = True, db: Session = Depends(get_db)):
    stmt = select(ActivityCode)
    if active_only:
        stmt = stmt.where(ActivityCode.is_active == True)  # noqa
    return list(db.execute(stmt).scalars().all())

@router.post("", response_model=ActivityCodeOut)
def create_code(payload: ActivityCodeCreate, db: Session = Depends(get_db)):
    existing = db.execute(select(ActivityCode).where(ActivityCode.code == payload.code)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Código ya existe")
    obj = ActivityCode(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj