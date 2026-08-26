from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import hash_password
from app.core.session_security import session_matches_user
from app.models.platform_permission import PlatformPermission
from app.models.user import User
from app.models.user_platform_permission import UserPlatformPermission


MANAGE_PLATFORM_SETTINGS = "manage_platform_settings"


def bootstrap_platform_settings_user(
    db: Session,
    *,
    email: str | None,
    password: str | None,
) -> User | None:
    """Create or update the optional local Settings bootstrap user."""
    normalized_email = (email or "").strip().lower()
    if not normalized_email or not password:
        return None

    email_matches = func.lower(func.ltrim(func.rtrim(User.email))) == normalized_email
    username_matches = func.lower(func.ltrim(func.rtrim(User.username))) == normalized_email
    user = db.execute(
        select(User)
        .where(or_(email_matches, username_matches))
        .order_by(case((email_matches, 0), else_=1), User.user_id)
    ).scalars().first()

    if user is None:
        user = User(
            username=normalized_email,
            email=normalized_email,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
            local_login_enabled=True,
            session_version=1,
            residential_id=None,
        )
        db.add(user)
        db.flush()
    else:
        if not (user.email or "").strip():
            user.email = normalized_email
        if not (user.role or "").strip():
            user.role = "admin"

    permission = db.execute(
        select(PlatformPermission).where(
            PlatformPermission.key == MANAGE_PLATFORM_SETTINGS,
        )
    ).scalar_one_or_none()
    if permission is None:
        raise RuntimeError("No existe el permiso requerido para Platform Settings.")

    assignment = db.execute(
        select(UserPlatformPermission).where(
            UserPlatformPermission.user_id == user.user_id,
            UserPlatformPermission.permission_id == permission.permission_id,
        )
    ).scalar_one_or_none()
    if assignment is None:
        db.add(
            UserPlatformPermission(
                user_id=user.user_id,
                permission_id=permission.permission_id,
                granted_by_user_id=None,
            )
        )

    return user


def get_optional_current_user(request: Request, db: Session) -> User | None:
    """Return the active local user when a valid session exists, without redirecting."""
    raw_user_id = request.session.get("user_id")
    if raw_user_id is None:
        return None

    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        request.session.clear()
        return None

    if user_id <= 0:
        request.session.clear()
        return None

    user = db.get(User, user_id)
    if not user or not user.is_active or not session_matches_user(request.session, user):
        request.session.clear()
        return None
    return user


def user_permission_keys(db: Session, user: User) -> set[str]:
    statement = (
        select(PlatformPermission.key)
        .join(
            UserPlatformPermission,
            UserPlatformPermission.permission_id == PlatformPermission.permission_id,
        )
        .where(
            UserPlatformPermission.user_id == user.user_id,
            PlatformPermission.is_active == True,  # noqa: E712
        )
    )
    return set(db.execute(statement).scalars().all())


def user_has_platform_permission(db: Session, user: User, permission_key: str) -> bool:
    normalized_key = permission_key.strip()
    if not normalized_key:
        return False
    return normalized_key in user_permission_keys(db, user)


def require_platform_permission(permission_key: str) -> Callable:
    normalized_key = permission_key.strip()
    if not normalized_key:
        raise ValueError("permission_key no puede estar vacío.")

    def dependency(request: Request, db: Session = Depends(get_db)) -> User:
        user = get_optional_current_user(request, db)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                headers={"Location": "/login"},
            )
        if not user_has_platform_permission(db, user, normalized_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado.",
            )
        return user

    return dependency
