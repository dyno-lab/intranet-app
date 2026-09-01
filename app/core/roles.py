from __future__ import annotations

from typing import Any


ADMIN_ROLE = "admin"
SUPERVISOR_ROLE = "supervisor"
USER_ROLE = "user"
VIEWER_ROLE = "viewer"

VALID_USER_ROLES = frozenset({
    ADMIN_ROLE,
    SUPERVISOR_ROLE,
    USER_ROLE,
    VIEWER_ROLE,
})
GLOBAL_READ_ROLES = frozenset({
    ADMIN_ROLE,
    SUPERVISOR_ROLE,
    VIEWER_ROLE,
})
VIEWER_AUTHORIZED_NAME = "Usuario no autorizado"


def is_viewer(user: Any) -> bool:
    return getattr(user, "role", None) == VIEWER_ROLE


def can_read_globally(user: Any) -> bool:
    return getattr(user, "role", None) in GLOBAL_READ_ROLES


def report_authorized_name(user: Any, value: str | None) -> str:
    if is_viewer(user):
        return VIEWER_AUTHORIZED_NAME
    return (value or "").strip()
