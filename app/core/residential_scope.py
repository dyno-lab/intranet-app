from __future__ import annotations

from urllib.parse import quote

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.platform_permissions import ACCESS_FARO, require_platform_permission
from app.core.roles import can_read_globally, is_viewer
from app.models.residential import Residential
from app.models.user import User
from app.models.user_residential import UserResidential


ACTIVE_RESIDENTIAL_SESSION_KEY = "active_residential_id"
ACTIVE_RESIDENTIAL_NAME_SESSION_KEY = "active_residential_name"
AVAILABLE_RESIDENTIAL_COUNT_SESSION_KEY = "available_residential_count"

_FARO_PERMISSION_DEPENDENCY = require_platform_permission(ACCESS_FARO)


def assigned_residentials(db: Session, user: User) -> list[Residential]:
    statement = (
        select(Residential)
        .join(
            UserResidential,
            UserResidential.residential_id == Residential.residential_id,
        )
        .where(
            Residential.is_active == True,  # noqa: E712
            UserResidential.user_id == user.user_id,
            UserResidential.is_active == True,  # noqa: E712
        )
    )
    return list(db.execute(statement.order_by(Residential.code, Residential.name)).scalars().all())


def clear_active_residential(session) -> None:
    session.pop(ACTIVE_RESIDENTIAL_SESSION_KEY, None)
    session.pop(ACTIVE_RESIDENTIAL_NAME_SESSION_KEY, None)
    session.pop(AVAILABLE_RESIDENTIAL_COUNT_SESSION_KEY, None)


def set_active_residential(session, residential: Residential) -> None:
    session[ACTIVE_RESIDENTIAL_SESSION_KEY] = residential.residential_id
    session[ACTIVE_RESIDENTIAL_NAME_SESSION_KEY] = residential.name


def resolve_active_residential(
    request: Request,
    db: Session,
    user: User,
) -> tuple[Residential | None, list[Residential]]:
    residentials = assigned_residentials(db, user)
    residential_by_id = {residential.residential_id: residential for residential in residentials}
    had_active_residential_context = ACTIVE_RESIDENTIAL_SESSION_KEY in request.session

    try:
        selected_id = int(request.session.get(ACTIVE_RESIDENTIAL_SESSION_KEY))
    except (TypeError, ValueError):
        selected_id = None

    selected = residential_by_id.get(selected_id)
    if selected is not None:
        set_active_residential(request.session, selected)
        request.session[AVAILABLE_RESIDENTIAL_COUNT_SESSION_KEY] = len(residentials)
        return selected, residentials

    clear_active_residential(request.session)
    request.session[AVAILABLE_RESIDENTIAL_COUNT_SESSION_KEY] = len(residentials)
    if had_active_residential_context:
        return None, residentials
    if len(residentials) == 1:
        selected = residentials[0]
        set_active_residential(request.session, selected)
        return selected, residentials
    return None, residentials


def active_record_residential_id(request: Request, user: User) -> int | None:
    try:
        residential_id = int(request.session.get(ACTIVE_RESIDENTIAL_SESSION_KEY))
    except (TypeError, ValueError):
        residential_id = None
    if residential_id and residential_id > 0:
        return residential_id
    return None


def has_global_residential_access(user: User) -> bool:
    return (
        can_read_globally(user)
        and getattr(user, "_active_residential_id", None) is None
    )


def require_record_residential_id(request: Request, user: User) -> int:
    residential_id = active_record_residential_id(request, user)
    if residential_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debe seleccionar un residencial antes de trabajar con registros de Faro.",
        )
    return residential_id


def require_write_residential_id(
    request: Request,
    user: User,
    db: Session,
    requested_residential_id: int | None = None,
) -> int:
    if is_viewer(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El rol viewer tiene acceso de consulta solamente.",
        )
    if not can_read_globally(user):
        return require_record_residential_id(request, user)

    active_residential_id = active_record_residential_id(request, user)
    if active_residential_id is not None:
        if (
            requested_residential_id is not None
            and requested_residential_id != active_residential_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El registro debe guardarse en el residencial activo.",
            )
        requested_residential_id = active_residential_id
    elif requested_residential_id is None or requested_residential_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debe seleccionar el residencial donde se guardará el registro.",
        )

    residential = db.get(Residential, requested_residential_id)
    if residential is None or not residential.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El residencial seleccionado no está disponible.",
        )
    return residential.residential_id


def _enforce_viewer_read_only(request: Request, user: User) -> None:
    if not is_viewer(user):
        return

    path = request.url.path.rstrip("/") or "/"
    if path == "/ui/admin" or path.startswith("/ui/admin/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El rol viewer no tiene acceso a configuraciones.",
        )

    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        if path.startswith("/ui/new-list/") and path.endswith("/edit"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El rol viewer tiene acceso de consulta solamente.",
            )
        return

    if request.method.upper() == "POST" and path == "/ui/reports/notas/pdf":
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="El rol viewer tiene acceso de consulta solamente.",
    )


def require_faro_access(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    user = _FARO_PERMISSION_DEPENDENCY(request=request, db=db)
    _enforce_viewer_read_only(request, user)
    if can_read_globally(user):
        had_active_residential_context = ACTIVE_RESIDENTIAL_SESSION_KEY in request.session
        residentials = assigned_residentials(db, user)
        residential_by_id = {
            residential.residential_id: residential for residential in residentials
        }
        active_residential_id = active_record_residential_id(request, user)
        active_residential = residential_by_id.get(active_residential_id)
        if active_residential is not None:
            set_active_residential(request.session, active_residential)
            request.session[AVAILABLE_RESIDENTIAL_COUNT_SESSION_KEY] = len(residentials) + 1
            setattr(user, "_active_residential_id", active_residential.residential_id)
            return user

        clear_active_residential(request.session)
        request.session[AVAILABLE_RESIDENTIAL_COUNT_SESSION_KEY] = len(residentials) + 1
        if hasattr(user, "_active_residential_id"):
            delattr(user, "_active_residential_id")
        if had_active_residential_context:
            next_path = request.url.path
            if request.url.query:
                next_path = f"{next_path}?{request.url.query}"
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                headers={"Location": f"/login?next={quote(next_path, safe='')}"},
            )
        return user

    had_active_residential_context = ACTIVE_RESIDENTIAL_SESSION_KEY in request.session
    active_residential, residentials = resolve_active_residential(request, db, user)
    if active_residential is not None:
        setattr(user, "_active_residential_id", active_residential.residential_id)
        return user
    if had_active_residential_context:
        next_path = request.url.path
        if request.url.query:
            next_path = f"{next_path}?{request.url.query}"
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": f"/login?next={quote(next_path, safe='')}"},
        )
    if not residentials:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene residenciales activos asignados.",
        )

    next_path = request.url.path
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    raise HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={
            "Location": f"/login?next={quote(next_path, safe='')}"
        },
    )


def user_can_read_record(
    user: User,
    *,
    active_residential_id: int,
    record_residential_id: int,
    created_by_user_id: int,
) -> bool:
    if has_global_residential_access(user):
        return True
    return record_residential_id == active_residential_id
