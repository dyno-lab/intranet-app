from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from app.models.user import User


SESSION_USER_ID_KEY = "user_id"
SESSION_VERSION_KEY = "session_version"


def establish_authenticated_session(session: MutableMapping[str, Any], user: User) -> None:
    session.clear()
    session[SESSION_USER_ID_KEY] = user.user_id
    session[SESSION_VERSION_KEY] = user.session_version


def session_matches_user(session: MutableMapping[str, Any], user: User) -> bool:
    try:
        session_version = int(session.get(SESSION_VERSION_KEY))
        user_version = int(user.session_version)
    except (TypeError, ValueError):
        return False
    return session_version == user_version
