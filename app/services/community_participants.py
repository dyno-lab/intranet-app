"""Read-only registration dashboard and roster, always scoped to visible programs."""
from calendar import monthrange
from collections import defaultdict
from datetime import date
import json
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.models.community import CPFiscalYear, CPParticipant, CPParticipantProgram, CPProgram
from app.models.community_catalog import CPProfileField, CPProfileValue
from app.models.community_fiscal import CPFiscalParticipant, CPFiscalState
from app.services.community_fiscal import build_participant_snapshot


AGE_RANGES = (
    {"value": "lt5", "label": "0–5 años", "min": 0, "max": 5},
    {"value": "6_7", "label": "6–7 años", "min": 6, "max": 7},
    {"value": "8_10", "label": "8–10 años", "min": 8, "max": 10},
    {"value": "11_15", "label": "11–15 años", "min": 11, "max": 15},
    {"value": "16_21", "label": "16–21 años", "min": 16, "max": 21},
    {"value": "22_59", "label": "22–59 años", "min": 22, "max": 59},
    {"value": "60_plus", "label": "60 años en adelante", "min": 60, "max": None},
)


def participant_query(context):
    return select(CPParticipant).where(select(CPParticipantProgram.participant_id).where(
        CPParticipantProgram.participant_id == CPParticipant.participant_id,
        CPParticipantProgram.program_id.in_(context.visible_program_ids),
    ).exists())


def _integer(params, key, default=None, minimum=0, maximum=130):
    raw = params.get(key, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise HTTPException(422, f"El filtro {key} debe ser un número entero.")
    if not minimum <= value <= maximum:
        raise HTTPException(422, f"El filtro {key} está fuera del rango permitido.")
    return value


def roster_filters(params, context):
    program_id = _integer(params, "program_id", minimum=1, maximum=2147483647)
    if program_id is not None and program_id not in context.visible_program_ids:
        raise HTTPException(403, "Programa no autorizado en este contexto de Comunidad.")
    age_range = params.get("age_range", "").strip()
    selected = next((row for row in AGE_RANGES if row["value"] == age_range), None)
    if age_range and selected is None:
        raise HTTPException(422, "Rango de edad no válido.")
    age_min = _integer(params, "age_min", default=selected["min"] if selected else None)
    age_max = _integer(params, "age_max", default=selected["max"] if selected else None)
    if age_min is not None and age_max is not None and age_min > age_max:
        raise HTTPException(422, "La edad desde no puede ser mayor que la edad hasta.")
    return {"q": params.get("q", "").strip()[:150],
            "expediente_num": params.get("expediente_num", "").strip().upper()[:80],
            "program_id": program_id, "age_range": age_range, "age_min": age_min, "age_max": age_max,
            "per_page": _integer(params, "per_page", default=25, minimum=1, maximum=100)}


def filtered_query(context, filters, *, today=None):
    query = participant_query(context)
    if filters["program_id"] is not None:
        query = query.where(select(CPParticipantProgram.participant_id).where(
            CPParticipantProgram.participant_id == CPParticipant.participant_id,
            CPParticipantProgram.program_id == filters["program_id"],
        ).exists())
    if filters["q"]:
        query = query.where(or_(*[field.contains(filters["q"], autoescape=True) for field in (
            CPParticipant.expediente_num, CPParticipant.nombre, CPParticipant.apellido_paterno, CPParticipant.apellido_materno)]))
    if filters["expediente_num"]:
        query = query.where(func.upper(CPParticipant.expediente_num) == filters["expediente_num"])
    today = today or date.today()

    def cutoff(years):
        year = today.year - years
        return date(year, today.month, min(today.day, monthrange(year, today.month)[1]))

    if filters["age_min"] is not None:
        query = query.where(CPParticipant.fecha_nacimiento <= cutoff(filters["age_min"]))
    if filters["age_max"] is not None:
        query = query.where(CPParticipant.fecha_nacimiento > cutoff(filters["age_max"] + 1))
    return query


def program_links(db, context, participant_ids):
    links = defaultdict(list)
    if participant_ids:
        for association, program in db.execute(select(CPParticipantProgram, CPProgram).join(
            CPProgram, CPProgram.program_id == CPParticipantProgram.program_id
        ).where(CPParticipantProgram.participant_id.in_(participant_ids),
                CPParticipantProgram.program_id.in_(context.visible_program_ids)).order_by(CPProgram.code)):
            links[association.participant_id].append({"code": program.code, "name": program.name,
                                                     "record_number": association.record_number})
    return links


def registration_dashboard(db, context):
    scoped = participant_query(context)
    visible_ids = scoped.with_only_columns(CPParticipant.participant_id)
    people = {p.participant_id: p for p in db.scalars(scoped)}
    profiles = defaultdict(list)
    for field, value in db.execute(select(CPProfileField, CPProfileValue).join(
        CPProfileValue, CPProfileValue.field_id == CPProfileField.field_id
    ).where(CPProfileValue.participant_id.in_(visible_ids))):
        profiles[value.participant_id].append((field, value))
    assigned, pending = set(), set()
    current = {}
    for snapshot, frozen in db.execute(select(CPFiscalParticipant, CPFiscalState.snapshots_frozen).join(
        CPFiscalYear, CPFiscalYear.fiscal_year_id == CPFiscalParticipant.fiscal_year_id
    ).outerjoin(CPFiscalState, CPFiscalState.fiscal_year_id == CPFiscalParticipant.fiscal_year_id).where(
        CPFiscalParticipant.participant_id.in_(visible_ids),
        CPFiscalYear.is_active == True, CPFiscalYear.status == "active",  # noqa: E712
    )):
        pid = snapshot.participant_id
        assigned.add(pid)
        if frozen:
            continue
        if pid not in current:
            current[pid] = build_participant_snapshot(db, people[pid], profile_rows=profiles[pid])
        historical = json.loads(snapshot.snapshot_json)
        # VCA was retired from Community; old snapshots must not appear changed
        # solely because they retain this legacy key. Never rewrite history here.
        historical.pop("vca", None)
        if historical != current[pid]:
            pending.add(pid)
    program_people = defaultdict(set)
    for pid, program_id in db.execute(select(CPParticipantProgram.participant_id, CPParticipantProgram.program_id).where(
        CPParticipantProgram.program_id.in_(context.visible_program_ids))):
        program_people[program_id].add(pid)

    def counts(ids):
        return {"registered_count": len(ids), "assigned_count": len(ids & assigned),
                "pending_sync_count": len(ids & pending)}

    return {"totals": counts(set(people)), "program_rows": [
        {"program_id": p.program_id, "label": f"{p.code} · {p.name}", **counts(program_people[p.program_id])}
        for p in context.visible_programs]}


def roster_page(db, context, params):
    filters = roster_filters(params, context)
    query = filtered_query(context, filters)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    total_pages = max(1, (total + filters["per_page"] - 1) // filters["per_page"])
    page = min(_integer(params, "page", default=1, minimum=1, maximum=2147483647), total_pages)
    people = db.scalars(query.order_by(CPParticipant.participant_id.desc()).offset(
        (page - 1) * filters["per_page"]).limit(filters["per_page"])).all()
    query_string = urlencode({key: value for key, value in filters.items() if value is not None and value != ""})
    page_links = {key: f"/community/participants?{query_string}&page={number}#participants-table-card" for key, number in (
        ("first", 1), ("prev", max(1, page - 1)), ("next", min(total_pages, page + 1)), ("last", total_pages))}
    return {"participants": people, "total": total, "page": page, "total_pages": total_pages,
            "filters": filters, "age_ranges": AGE_RANGES, "query_string": query_string, "page_links": page_links,
            "participant_programs": program_links(db, context, [p.participant_id for p in people])}
