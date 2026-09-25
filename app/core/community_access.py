"""Community authorization uses its own role and program assignments."""
from __future__ import annotations

from dataclasses import dataclass
import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.platform_permissions import ACCESS_COMMUNITY, require_platform_permission
from app.models.community import CPProgram, CPUserAccess, CPUserProgram
from app.models.user import User

CONTEXT_KEY = "community_program_context"
CSRF_KEY = "community_csrf"
COMMUNITY_ROLES = frozenset({"admin", "supervisor", "viewer", "user"})
_permission = require_platform_permission(ACCESS_COMMUNITY)


@dataclass(frozen=True)
class CommunityContext:
    user: User
    role: str
    programs: tuple[CPProgram, ...]
    selected_program_id: int | None = None

    @property
    def program_ids(self) -> set[int]:
        return {program.program_id for program in self.programs}

    @property
    def visible_programs(self) -> tuple[CPProgram, ...]:
        if self.selected_program_id is None:
            return self.programs
        return tuple(p for p in self.programs if p.program_id == self.selected_program_id)

    @property
    def visible_program_ids(self) -> set[int]:
        return {program.program_id for program in self.visible_programs}

    @property
    def label(self) -> str:
        if self.selected_program_id is not None:
            return next(p.name for p in self.programs if p.program_id == self.selected_program_id)
        return "Todos mis programas" if self.role == "user" else "Administración general"


def require_community_access(request: Request, db: Session = Depends(get_db)) -> CommunityContext:
    if not settings.COMMUNITY_ENABLED:
        raise HTTPException(404, "Módulo no disponible.")
    user = _permission(request=request, db=db)
    access = db.get(CPUserAccess, user.user_id)
    if access is None or access.role not in COMMUNITY_ROLES:
        raise HTTPException(403, "No tiene un rol asignado en Comunidad y Prevención.")
    statement = select(CPProgram).where(CPProgram.is_active == True)  # noqa: E712
    if access.role == "user":
        statement = statement.join(CPUserProgram, CPUserProgram.program_id == CPProgram.program_id).where(
            CPUserProgram.user_id == user.user_id
        )
    programs = tuple(db.scalars(statement.order_by(CPProgram.code)).all())
    if access.role == "user" and not programs:
        raise HTTPException(403, "No tiene programas activos asignados en Comunidad.")
    return CommunityContext(user, access.role, programs)


def require_community_context(
    request: Request,
    access: CommunityContext = Depends(require_community_access),
) -> CommunityContext:
    selected = request.session.get(CONTEXT_KEY)
    if selected == "all":
        return access
    if isinstance(selected, int) and not isinstance(selected, bool) and selected in access.program_ids:
        return CommunityContext(access.user, access.role, access.programs, selected)
    request.session.pop(CONTEXT_KEY, None)
    raise HTTPException(303, headers={"Location": "/community/login"})


def require_community_writer(
    context: CommunityContext = Depends(require_community_context),
) -> CommunityContext:
    if context.role == "viewer":
        raise HTTPException(403, "El rol Viewer de Comunidad permite consulta solamente.")
    return context


def require_community_admin(
    context: CommunityContext = Depends(require_community_context),
) -> CommunityContext:
    if context.role != "admin":
        raise HTTPException(403, "Esta configuración requiere administración de Comunidad.")
    return context


def require_community_supervisor(
    context: CommunityContext = Depends(require_community_context),
) -> CommunityContext:
    if context.role not in {"admin", "supervisor"}:
        raise HTTPException(403, "Los datos personales comunes requieren Supervisor o Administrador de Comunidad.")
    return context


def csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_KEY] = token
    return token


def validate_csrf(request: Request, submitted: str) -> None:
    expected = request.session.get(CSRF_KEY)
    if not isinstance(expected, str) or not expected or not secrets.compare_digest(expected, submitted):
        raise HTTPException(403, "Solicitud inválida. Recargue la página e intente nuevamente.")


def require_programs(context: CommunityContext, program_ids: list[int]) -> None:
    if not program_ids or not set(program_ids).issubset(context.visible_program_ids):
        raise HTTPException(403, "Seleccione únicamente programas disponibles en su contexto de Comunidad.")
