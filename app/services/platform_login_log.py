from datetime import timedelta, timezone

from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.orm import Session

from app.models.platform_login_event import PlatformLoginEvent
from app.models.user import User


OUTCOMES = {
    "success": "Ingreso exitoso",
    "google_pending": "Sin respuesta de Google",
    "unknown_account": "Cuenta no registrada",
    "denied_domain": "Dominio de Google Workspace no autorizado",
    "inactive": "Cuenta inactiva",
    "local_disabled": "Acceso local deshabilitado",
    "invalid_password": "Credenciales incorrectas",
    "identity_conflict": "Vinculación de cuenta no válida",
    "unverified": "Identidad no comprobada",
}
PAGE_SIZE = 50


def start_google_login_event(db: Session) -> int:
    event_id = db.execute(
        insert(PlatformLoginEvent)
        .values(method="google", outcome="google_pending")
        .returning(PlatformLoginEvent.event_id)
    ).scalar_one()
    db.commit()
    return event_id


def record_login_event(
    db: Session, method: str, outcome: str, identifier: str | None, user_id: int | None = None,
    *, pending_google_id: int | None = None,
) -> None:
    """Commit the login decision and any pending first-time Google link together."""
    identifier = (identifier or "").strip()
    if len(identifier) > 320 or not identifier.isprintable() or len(identifier.encode("utf-16-le")) > 640:
        identifier = ""
    if pending_google_id is None:
        db.add(PlatformLoginEvent(method=method, outcome=outcome, identifier=identifier or None, user_id=user_id))
    else:
        # Atomically finalize this attempt once; a repeated callback cannot replace a final result.
        db.execute(
            update(PlatformLoginEvent)
            .where(PlatformLoginEvent.event_id == pending_google_id,
                   PlatformLoginEvent.method == "google", PlatformLoginEvent.outcome == "google_pending")
            .values(outcome=outcome, identifier=identifier or None, user_id=user_id, occurred_at=func.sysutcdatetime())
        )
    db.commit()


def last_success_by_user(db: Session, *, user_id: int | None = None):
    stmt = select(PlatformLoginEvent.user_id, func.max(PlatformLoginEvent.occurred_at)).where(
        PlatformLoginEvent.outcome == "success", PlatformLoginEvent.user_id.is_not(None),
    )
    if user_id is not None:
        stmt = stmt.where(PlatformLoginEvent.user_id == user_id)
    return dict(db.execute(stmt.group_by(PlatformLoginEvent.user_id)).all())


def _account_matches(term: str):
    return or_(
        func.lower(func.ltrim(func.rtrim(User.username))) == term,
        func.lower(func.ltrim(func.rtrim(User.email))) == term,
    )


def find_history_account(db: Session, account: str):
    # A username can also be the address of a different account. Only label an unambiguous match.
    users = db.scalars(select(User).where(_account_matches(account.lower())).limit(2)).all()
    return users[0] if len(users) == 1 else None


def access_history(db: Session, *, result: str, account: str, user_id: int | None, before: int | None):
    event = PlatformLoginEvent
    stmt = select(event, User.username).outerjoin(User, User.user_id == event.user_id)
    if user_id is not None:
        stmt = stmt.where(event.user_id == user_id)
    if account:
        term = account.lower()
        stmt = stmt.where(or_(
            func.lower(event.identifier) == term,
            _account_matches(term),
        ))
    if result == "exitosos":
        stmt = stmt.where(event.outcome == "success")
    elif result == "denegados":
        stmt = stmt.where(event.outcome.not_in(("success", "google_pending")))
    elif result == "sin-respuesta":
        stmt = stmt.where(event.outcome == "google_pending")
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
