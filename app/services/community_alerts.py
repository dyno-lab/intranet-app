"""Computed fiscal tasks and persistent, individually read Community announcements."""
from collections import defaultdict
from datetime import date
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError

from app.models.community import CPParticipantProgram, CPProgram, _utcnow
from app.models.community_alerts import (
    CPAnnouncement, CPAnnouncementProgram, CPAnnouncementRead, CPAnnouncementRole,
)
from app.services.community_participants import participant_sync_notices

ROLE_LABELS = {"admin": "Administrador", "supervisor": "Supervisor", "user": "Usuario", "viewer": "Consulta"}


def pending_groups(db, context):
    notices = participant_sync_notices(db, context)
    if not notices:
        return []
    programs = {p.program_id: p for p in context.visible_programs}
    # SQL Server has a 2100-parameter limit: filter by the authorized programs,
    # not by an unbounded list of participant identifiers.
    memberships = db.execute(select(CPParticipantProgram.participant_id, CPParticipantProgram.program_id)
        .where(CPParticipantProgram.program_id.in_(context.visible_program_ids)))
    groups = {}
    for participant_id, program_id in memberships:
        notice = notices.get(participant_id)
        if notice is None:
            continue
        years = notice["links"] if notice["kind"] == "pending" else [None]
        for year in years:
            kind = "sync" if year else "unassigned"
            fiscal_id = year["fiscal_year_id"] if year else None
            key = (kind, program_id, fiscal_id)
            if key not in groups:
                params = {"kind": kind, "program_id": program_id}
                if fiscal_id is not None:
                    params["fiscal_year_id"] = fiscal_id
                review = {"program_id": program_id}
                if kind == "sync":
                    review.update(fiscal_year_id=fiscal_id, sync_filter="pending")
                    anchor = "assigned-participants"
                else:
                    review["available_filter"] = "never"
                    anchor = "available-participants"
                groups[key] = {
                    "kind": kind, "program": programs[program_id],
                    "fiscal_year_id": fiscal_id, "fiscal_label": year["label"] if year else None,
                    "title": "Pendientes de sincronización" if year else "Expedientes sin año fiscal asociado",
                    "description": "Hay cambios por actualizar en el año fiscal." if year else
                                   "Revise si corresponde incorporar estos expedientes a un año fiscal.",
                    "participant_ids": set(),
                    "url": "/community/alerts/pending?" + urlencode(params),
                    "review_url": "/community/fiscal-participants?" + urlencode(review) + "#" + anchor
                                  if context.role in {"admin", "supervisor"} else None,
                }
            groups[key]["participant_ids"].add(participant_id)
    result = list(groups.values())
    for group in result:
        group["count"] = len(group["participant_ids"])
    return sorted(result, key=lambda g: (g["kind"] != "sync", g["program"].code, -(g["fiscal_year_id"] or 0)))


def visible_announcements(context, *, today=None):
    today = today or date.today()
    roles = select(CPAnnouncementRole.announcement_id).where(
        CPAnnouncementRole.announcement_id == CPAnnouncement.announcement_id)
    targets = select(CPAnnouncementProgram.announcement_id).where(
        CPAnnouncementProgram.announcement_id == CPAnnouncement.announcement_id)
    return select(CPAnnouncement).where(
        CPAnnouncement.is_active == True, CPAnnouncement.starts_on <= today,
        or_(CPAnnouncement.ends_on.is_(None), CPAnnouncement.ends_on >= today),
        or_(~roles.exists(), roles.where(CPAnnouncementRole.role == context.role).exists()),
        or_(~targets.exists(), targets.where(
            CPAnnouncementProgram.program_id.in_(context.visible_program_ids)).exists()),
    )


def announcements(db, context, *, today=None):
    statement = visible_announcements(context, today=today).add_columns(CPAnnouncementRead.read_at).outerjoin(
        CPAnnouncementRead, and_(CPAnnouncementRead.announcement_id == CPAnnouncement.announcement_id,
                                CPAnnouncementRead.user_id == context.user.user_id))
    return [{"announcement": notice, "unread": read_at is None, "read_at": read_at,
             "url": f"/community/alerts/notices/{notice.announcement_id}"}
            for notice, read_at in db.execute(statement.order_by(
                CPAnnouncement.starts_on.desc(), CPAnnouncement.announcement_id.desc()))]


def alert_feed(db, context):
    tasks = pending_groups(db, context)
    notices = announcements(db, context)
    unread = [row for row in notices if row["unread"]]
    task_items = [{"type": "task", **task} for task in tasks]
    notice_items = [{"type": "notice", **row} for row in unread]
    # Keep each available category represented in the compact home summary.
    preview = []
    for kind in ("sync", "unassigned"):
        first = next((item for item in task_items if item["kind"] == kind), None)
        if first is not None:
            preview.append(first)
    if notice_items:
        preview.append(notice_items[0])
    for item in task_items + notice_items:
        if len(preview) >= 3:
            break
        if item not in preview:
            preview.append(item)
    return {"tasks": tasks, "notices": notices, "unread_count": len(unread),
            "attention_count": len(tasks) + len(unread),
            "preview": preview}


def get_announcement(db, context, announcement_id):
    notice = db.scalar(visible_announcements(context).where(
        CPAnnouncement.announcement_id == announcement_id))
    if notice is None:
        raise HTTPException(404, "El aviso no está disponible para sus programas y rol.")
    return notice


def mark_read(db, context, announcement_id):
    get_announcement(db, context, announcement_id)
    key = (announcement_id, context.user.user_id)
    if db.get(CPAnnouncementRead, key) is not None:
        return
    db.add(CPAnnouncementRead(announcement_id=announcement_id, user_id=context.user.user_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.get(CPAnnouncementRead, key) is None:
            raise


def create_announcement(db, context, values):
    if context.role != "admin":
        raise HTTPException(403, "Solo Administración de Comunidad puede publicar avisos.")
    title, message = values.get("title", "").strip(), values.get("message", "").strip()
    if not 1 <= len(title.encode("utf-16-le")) // 2 <= 160 or not 1 <= len(message.encode("utf-16-le")) // 2 <= 4000:
        raise HTTPException(422, "Escriba un título de hasta 160 caracteres y un mensaje de hasta 4,000.")
    try:
        start = date.fromisoformat(values.get("starts_on", ""))
        end = date.fromisoformat(values["ends_on"]) if values.get("ends_on") else None
    except (TypeError, ValueError):
        raise HTTPException(422, "Revise las fechas de vigencia.")
    if not 2000 <= start.year <= 2100 or (end and (end < start or not 2000 <= end.year <= 2100)):
        raise HTTPException(422, "La fecha final debe ser igual o posterior al inicio (años 2000–2100).")
    roles = set(values.get("roles", []))
    try:
        program_ids = {int(value) for value in values.get("program_ids", [])}
    except (TypeError, ValueError):
        raise HTTPException(422, "Seleccione programas válidos.")
    for mode, chosen in ((values.get("role_scope"), roles), (values.get("program_scope"), program_ids)):
        if mode not in {"all", "selected"} or (mode == "selected" and not chosen) or (mode == "all" and chosen):
            raise HTTPException(422, "Elija todos los destinatarios o seleccione al menos uno.")
    if not roles <= ROLE_LABELS.keys():
        raise HTTPException(422, "Rol de Comunidad inválido.")
    if len(program_ids) > 500 or not program_ids <= context.program_ids:
        raise HTTPException(422, "Seleccione únicamente programas autorizados.")
    if program_ids:
        valid = set(db.scalars(select(CPProgram.program_id).where(
            CPProgram.is_active == True, CPProgram.program_id.in_(program_ids))))
        if valid != program_ids:
            raise HTTPException(422, "Algún programa ya no está activo. Revise los destinatarios.")
    notice = CPAnnouncement(title=title, message=message, starts_on=start, ends_on=end,
                            created_by_user_id=context.user.user_id)
    db.add(notice)
    db.flush()
    db.add_all([CPAnnouncementRole(announcement_id=notice.announcement_id, role=role) for role in roles])
    db.add_all([CPAnnouncementProgram(announcement_id=notice.announcement_id, program_id=pid) for pid in program_ids])
    db.commit()
    return notice


def withdraw_announcement(db, context, announcement_id):
    if context.role != "admin":
        raise HTTPException(403, "Solo Administración de Comunidad puede retirar avisos.")
    notice = db.get(CPAnnouncement, announcement_id)
    if notice is None:
        raise HTTPException(404, "Aviso no encontrado.")
    if notice.is_active:
        notice.is_active = False
        notice.withdrawn_by_user_id = context.user.user_id
        notice.withdrawn_at = _utcnow()
        db.commit()


def managed_announcements(db, *, page=1):
    from sqlalchemy import func
    total = db.scalar(select(func.count()).select_from(CPAnnouncement)) or 0
    pages = max(1, (total + 19) // 20)
    page = min(page, pages)
    notices = list(db.scalars(select(CPAnnouncement).order_by(CPAnnouncement.announcement_id.desc())
                             .offset((page - 1) * 20).limit(20)))
    ids = [row.announcement_id for row in notices]
    roles, programs = defaultdict(list), defaultdict(list)
    for aid, role in db.execute(select(CPAnnouncementRole.announcement_id, CPAnnouncementRole.role)
                                .where(CPAnnouncementRole.announcement_id.in_(ids))):
        roles[aid].append(ROLE_LABELS[role])
    for aid, code in db.execute(select(CPAnnouncementProgram.announcement_id, CPProgram.code)
        .join(CPProgram, CPProgram.program_id == CPAnnouncementProgram.program_id)
        .where(CPAnnouncementProgram.announcement_id.in_(ids))):
        programs[aid].append(code)
    today = date.today()
    return {"managed_notices": [{"notice": row, "roles": ", ".join(sorted(roles[row.announcement_id])) or "Todos",
            "programs": ", ".join(sorted(programs[row.announcement_id])) or "Todos",
            "status": "Retirado" if not row.is_active else "Programado" if row.starts_on > today else
                      "Vencido" if row.ends_on and row.ends_on < today else "Vigente"} for row in notices],
            "page": page, "pages": pages, "total": total}
