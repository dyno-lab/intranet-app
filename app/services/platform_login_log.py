from datetime import timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.platform_login_event import PlatformLoginEvent
from app.models.user import User


OUTCOMES = {
    "success": "Ingreso exitoso",
    "unknown_account": "Cuenta no registrada",
    "denied_domain": "Dominio de Google Workspace no autorizado",
    "inactive": "Cuenta inactiva",
    "local_disabled": "Acceso local deshabilitado",
    "invalid_password": "Credenciales incorrectas",
    "identity_conflict": "Vinculación de cuenta no válida",
    "unverified": "Identidad no comprobada",
}
PAGE_SIZE = 50


def record_login_event(
    db: Session, method: str, outcome: str, identifier: str | None, user_id: int | None = None,
) -> None:
    """Commit the login decision and any pending first-time Google link together."""
    identifier = (identifier or "").strip()
    if len(identifier) > 320 or not identifier.isprintable() or len(identifier.encode("utf-16-le")) > 640:
        identifier = ""
    db.add(PlatformLoginEvent(method=method, outcome=outcome, identifier=identifier or None, user_id=user_id))
    db.commit()


def last_success_by_user(db: Session):
    rows = db.execute(
        select(PlatformLoginEvent.user_id, func.max(PlatformLoginEvent.occurred_at))
        .where(PlatformLoginEvent.outcome == "success", PlatformLoginEvent.user_id.is_not(None))
        .group_by(PlatformLoginEvent.user_id)
    ).all()
    return dict(rows)


def access_history(db: Session, *, result: str, account: str, user_id: int | None, before: int | None):
    event = PlatformLoginEvent
    stmt = select(event, User.username).outerjoin(User, User.user_id == event.user_id)
    if user_id is not None:
        stmt = stmt.where(event.user_id == user_id)
    if account:
        term = account.lower()
        stmt = stmt.where(or_(
            func.lower(event.identifier) == term,
            func.lower(User.username) == term,
            func.lower(User.email) == term,
        ))
    if result == "exitosos":
        stmt = stmt.where(event.outcome == "success")
    elif result == "denegados":
        stmt = stmt.where(event.outcome != "success")
    elif result == "no-autorizados":
        stmt = stmt.where(event.outcome.in_(("unknown_account", "denied_domain")))
    if before is not None:
        stmt = stmt.where(event.event_id < before)
    rows = db.execute(stmt.order_by(event.event_id.desc()).limit(PAGE_SIZE + 1)).all()
    page = rows[:PAGE_SIZE]
    next_cursor = page[-1][0].event_id if len(rows) > PAGE_SIZE else None
    return page, next_cursor


def puerto_rico_time(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone(timedelta(hours=-4))).strftime("%d/%m/%Y %I:%M %p")
