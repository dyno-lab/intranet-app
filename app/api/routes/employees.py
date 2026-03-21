from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.employee import Employee
from app.schemas.employee import EmployeeCreate, EmployeeOut

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("", response_model=list[EmployeeOut])
def list_employees(active_only: bool = True, db: Session = Depends(get_db)):
    stmt = select(Employee)
    if active_only:
        stmt = stmt.where(Employee.is_active == True)  # noqa
    return list(db.execute(stmt).scalars().all())

@router.post("", response_model=EmployeeOut)
def create_employee(payload: EmployeeCreate, db: Session = Depends(get_db)):
    if payload.employee_code:
        existing = db.execute(select(Employee).where(Employee.employee_code == payload.employee_code)).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="employee_code ya existe")

    obj = Employee(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj