"""Faro's shared feed: computed tasks and persistent, individually read announcements."""
from collections import defaultdict
from datetime import date
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import and_, extract, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.residential_scope import has_global_residential_access
from app.models.activity_code import ActivityCode
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.notification import (
    FaroAnnouncement, FaroAnnouncementRead, FaroAnnouncementResidential, FaroAnnouncementRole,
)
from app.models.participant_monthly_course import ParticipantMonthlyCourse
from app.models.residential import Residential
from app.services.participant_courses import ACTIVITY_CODE, COURSE_EDITOR_ROLES, MONTHS
from app.services.referral_requirements import pending_referral_groups

ANNOUNCEMENT_ROLES = {"admin": "Administrador", "supervisor": "Supervisor", "user": "Usuario", "viewer": "Consulta"}


def residential_scope(user):
    if has_global_residential_access(user):
        return None
    # This feed is always behind require_faro_access. Never fall back to the
    # legacy residential_id or accept a residential from the browser.
    rid = getattr(user, "_active_residential_id", None)
    if not rid:
        raise HTTPException(403, "Debe seleccionar un residencial autorizado.")
    return rid


def course_notification(db, user, *, today=None):
    if user.role not in COURSE_EDITOR_ROLES:
        return None
    today = today or date.today()
    rid = residential_scope(user)
    year, month = extract("year", ActivitySession.session_date), extract("month", ActivitySession.session_date)
    statement = (
        select(Attendance.participant_id, year.label("year"), month.label("month"),
               Residential.residential_id, Residential.name, ActivitySession.proposal_id)
        .select_from(Attendance)
        .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
        .join(ActivityCode, ActivityCode.activity_code_id == ActivitySession.activity_code_id)
        .join(Residential, Residential.residential_id == ActivitySession.residential_id)
        .outerjoin(ParticipantMonthlyCourse, and_(
            ParticipantMonthlyCourse.participant_id == Attendance.participant_id,
            ParticipantMonthlyCourse.report_year == year,
            ParticipantMonthlyCourse.report_month == month))
        .where(Attendance.attended == True, Attendance.participant_id.is_not(None),  # noqa: E712
               ActivityCode.code == ACTIVITY_CODE, Residential.is_active == True,  # noqa: E712
               ActivitySession.session_date <= today,
               or_(ParticipantMonthlyCourse.course_code.is_(None), ParticipantMonthlyCourse.course_code == ""))
        .distinct()
    )
    if rid is not None:
        statement = statement.where(Residential.residential_id == rid)
    groups = {}
    monthly_assignments = set()
    for row in db.execute(statement):
        key = (row.residential_id, int(row.year), int(row.month))
        group = groups.setdefault(key, {"residential_id": key[0], "residential": row.name,
                                       "year": key[1], "month": key[2], "participants": set(), "proposals": set()})
        group["participants"].add(row.participant_id)
        group["proposals"].add(row.proposal_id)
        monthly_assignments.add((row.participant_id, key[1], key[2]))
    if not groups:
        return None
    details = []
    for group in sorted(groups.values(), key=lambda g: (-g["year"], -g["month"], g["residential"].casefold())):
        proposal_ids = group.pop("proposals")
        proposals = sorted(pid for pid in proposal_ids if pid is not None)
        group["pending_count"] = len(group.pop("participants"))
        group["period"] = f"{dict(MONTHS)[group['month']]} {group['year']}"
        # The existing report accepts at most 50 proposals per request.
        group["actions"] = [{"label": "Completar cursos" if len(proposals) <= 50 else f"Ver propuestas {i + 1}–{min(i + 50, len(proposals))}",
            "url": "/ui/reports/cursos?" + urlencode([
                ("proposal_id", pid) for pid in proposals[i:i + 50]] + [
                ("employee_id", -group["residential_id"]), ("year", group["year"]),
                ("month", group["month"]), ("period_type", "monthly")])}
            for i in range(0, len(proposals), 50)]
        group["needs_proposal"] = None in proposal_ids
        if group["needs_proposal"]:
            group["actions"].append({"label": "Revisar asistencias sin propuesta", "url": "/ui/listado"})
        details.append(group)
    return {"id": "courses:2.b.5", "type": "task", "title": "Cursos 2.b.5 sin completar",
            "message": "Hay asistencias registradas que necesitan el curso de participación.",
            "count_label": "asignación mensual" if len(monthly_assignments) == 1 else "asignaciones mensuales",
            "note": "Selecciona el curso en el reporte y guarda los cambios. Los períodos cerrados conservan sus restricciones.",
            "unread": True, "pending_count": len(monthly_assignments),
            "residential_count": len({key[0] for key in groups}), "groups": details}


def referral_notification(db, user, *, today=None):
    if user.role not in COURSE_EDITOR_ROLES:
        return None
    groups = pending_referral_groups(db, residential_id=residential_scope(user), today=today)
    if not groups:
        return None
    return {"id": "referrals:visits", "type": "task", "title": "Referidos y visitas a agencias sin completar",
            "message": "Hay actividades con asistencia confirmada que requieren información en el reporte de Visitas.",
            "count_label": "informe mensual pendiente" if len(groups) == 1 else "informes mensuales pendientes",
            "note": "Guarda al menos un referido completo (interno, externo o visita a agencia) por propuesta, residencial y mes. Los períodos cerrados conservan sus restricciones.",
            "unread": True, "pending_count": len(groups),
            "residential_count": len({group['residential_id'] for group in groups}), "groups": groups}


def visible_announcements(user, *, today=None):
    today = today or date.today()
    rid = residential_scope(user)
    role_target = select(FaroAnnouncementRole.announcement_id).where(
        FaroAnnouncementRole.announcement_id == FaroAnnouncement.announcement_id)
    residential_target = select(FaroAnnouncementResidential.announcement_id).where(
        FaroAnnouncementResidential.announcement_id == FaroAnnouncement.announcement_id)
    allowed_residential = residential_target.join(Residential, Residential.residential_id == FaroAnnouncementResidential.residential_id).where(
        Residential.is_active == True)  # noqa: E712
    if rid is not None:
        allowed_residential = allowed_residential.where(FaroAnnouncementResidential.residential_id == rid)
    return select(FaroAnnouncement).where(
        FaroAnnouncement.is_active == True, FaroAnnouncement.starts_on <= today,  # noqa: E712
        or_(FaroAnnouncement.ends_on.is_(None), FaroAnnouncement.ends_on >= today),
        or_(~role_target.exists(), role_target.where(FaroAnnouncementRole.role == user.role).exists()),
        or_(~residential_target.exists(), allowed_residential.exists()),
    )


def announcement_notifications(db, user, *, today=None):
    statement = visible_announcements(user, today=today).add_columns(FaroAnnouncementRead.read_at).outerjoin(
        FaroAnnouncementRead, and_(FaroAnnouncementRead.announcement_id == FaroAnnouncement.announcement_id,
                                   FaroAnnouncementRead.user_id == user.user_id))
    result = []
    for announcement, read_at in db.execute(statement.order_by(FaroAnnouncement.starts_on.desc(), FaroAnnouncement.announcement_id.desc())):
        result.append({"id": f"announcement:{announcement.announcement_id}", "announcement_id": announcement.announcement_id,
                       "type": "announcement", "title": announcement.title, "message": announcement.message,
                       "published_on": announcement.starts_on.isoformat(), "unread": read_at is None})
    return result


TASK_PROVIDERS = (course_notification, referral_notification)


def notification_feed(db, user, *, today=None):
    items = [item for provider in TASK_PROVIDERS if (item := provider(db, user, today=today))]
    items.extend(announcement_notifications(db, user, today=today))
    return {"items": items, "attention_count": sum(item["unread"] for item in items)}


def mark_announcement_read(db, user, announcement_id):
    visible = db.scalar(visible_announcements(user).where(FaroAnnouncement.announcement_id == announcement_id))
    if visible is None:
        raise HTTPException(404, "El anuncio no está disponible.")
    key = (announcement_id, user.user_id)
    if db.get(FaroAnnouncementRead, key) is not None:
        return
    db.add(FaroAnnouncementRead(announcement_id=announcement_id, user_id=user.user_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Concurrent reads in different tabs are idempotent. Other errors are
        # not swallowed (e.g. a deleted user or database failure).
        if db.get(FaroAnnouncementRead, key) is None:
            raise


def create_announcement(db, user, values):
    if user.role != "admin":
        raise HTTPException(403, "Solo el administrador puede publicar anuncios.")
    title, message = values.get("title", "").strip(), values.get("message", "").strip()
    # NVARCHAR limits (and HTML maxlength) count UTF-16 units, including emoji.
    if not 1 <= len(title.encode("utf-16-le")) // 2 <= 160 or not 1 <= len(message.encode("utf-16-le")) // 2 <= 4000:
        raise HTTPException(422, "Escribe un título (hasta 160 caracteres) y un mensaje (hasta 4,000).")
    try:
        start = date.fromisoformat(values.get("starts_on", ""))
        end = date.fromisoformat(values["ends_on"]) if values.get("ends_on") else None
    except ValueError as exc:
        raise HTTPException(422, "Revisa las fechas de vigencia.") from exc
    if start.year < 2000 or start.year > 2100 or (end and (end < start or end.year > 2100)):
        raise HTTPException(422, "La fecha final debe ser igual o posterior al inicio (años 2000–2100).")
    roles = set(values.get("roles", []))
    try:
        residential_ids = {int(value) for value in values.get("residential_ids", [])}
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Residenciales inválidos.") from exc
    for mode, selected in ((values.get("role_scope"), roles), (values.get("residential_scope"), residential_ids)):
        if mode not in {"all", "selected"} or (mode == "selected" and not selected) or (mode == "all" and selected):
            raise HTTPException(422, "Revisa los destinatarios: elige todos o selecciona al menos uno.")
    if not roles <= ANNOUNCEMENT_ROLES.keys():
        raise HTTPException(422, "Rol inválido.")
    if len(residential_ids) > 500:
        raise HTTPException(422, "Selecciona hasta 500 residenciales por anuncio.")
    if residential_ids:
        valid = set(db.scalars(select(Residential.residential_id).where(
            Residential.is_active == True, Residential.residential_id.in_(residential_ids))))  # noqa: E712
        if valid != residential_ids:
            raise HTTPException(422, "Algún residencial ya no está activo. Revisa los destinatarios.")
    announcement = FaroAnnouncement(title=title, message=message, starts_on=start, ends_on=end,
                                    created_by_user_id=user.user_id)
    db.add(announcement)
    db.flush()
    db.add_all([FaroAnnouncementRole(announcement_id=announcement.announcement_id, role=role) for role in roles])
    db.add_all([FaroAnnouncementResidential(announcement_id=announcement.announcement_id, residential_id=rid) for rid in residential_ids])
    db.commit()
    return announcement


def admin_announcements(db, *, limit=50):
    announcements = list(db.scalars(select(FaroAnnouncement).order_by(FaroAnnouncement.announcement_id.desc()).limit(limit)))
    if not announcements:
        return []
    ids = [row.announcement_id for row in announcements]
    roles, residentials = defaultdict(list), defaultdict(list)
    for aid, role in db.execute(select(FaroAnnouncementRole.announcement_id, FaroAnnouncementRole.role).where(FaroAnnouncementRole.announcement_id.in_(ids))):
        roles[aid].append(ANNOUNCEMENT_ROLES.get(role, role))
    for aid, name in db.execute(select(FaroAnnouncementResidential.announcement_id, Residential.name).join(
            Residential, Residential.residential_id == FaroAnnouncementResidential.residential_id).where(FaroAnnouncementResidential.announcement_id.in_(ids))):
        residentials[aid].append(name)
    return [{"announcement": row, "roles": ", ".join(sorted(roles[row.announcement_id])) or "Todos los roles",
             "residentials": ", ".join(sorted(residentials[row.announcement_id])) or "Todos los residenciales"} for row in announcements]
