from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.roles import ADMIN_ROLE, SUPERVISOR_ROLE, VIEWER_ROLE
from app.core.session_security import session_matches_user
from app.models.user import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    Para UI:
    - Si no hay sesión: redirige a /home
    - Si usuario no existe/inactivo: limpia sesión y redirige a /home
    """
    user_id = request.session.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/home"},
        )

    user = db.get(User, user_id)

    if not user or not user.is_active or not session_matches_user(request.session, user):
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/home"},
        )

    return user


def is_admin(user: User) -> bool:
    return user.role == ADMIN_ROLE


def is_supervisor(user: User) -> bool:
    return user.role == SUPERVISOR_ROLE


def is_viewer(user: User) -> bool:
    return user.role == VIEWER_ROLE


def is_admin_or_supervisor(user: User) -> bool:
    return user.role in {ADMIN_ROLE, SUPERVISOR_ROLE}


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not is_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado.")
    return user


def require_admin_or_supervisor(user: User = Depends(get_current_user)) -> User:
    if not is_admin_or_supervisor(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado.")
    return user
