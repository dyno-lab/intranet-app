"""Read model for a Community record; historical attendance keeps program scope."""
from collections import defaultdict
from datetime import date
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import extract, func, or_, select

from app.models.community import CPFiscalYear, CPProgram
from app.models.community_activity import CPActivity
from app.models.community_fiscal import CPFiscalEnrollment, CPFiscalParticipant, CPEnrollmentPeriod
from app.models.community_operations import CPActivitySession, CPAttendance
from app.models.user import User

MONTHS = ('Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic')


def _number(params, key, default=None):
    raw = params.get(key, '').strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise HTTPException(422, f'El filtro {key} debe ser un número entero.')
    if not 1 <= value <= 2147483647:
        raise HTTPException(422, f'El filtro {key} no es válido.')
    return value


def _date(params, key):
    raw = params.get(key, '').strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(422, 'Revise las fechas del historial.')


def participant_record(db, context, participant_id, params):
    today = date.today()
    years = db.scalars(select(CPFiscalYear).join(CPFiscalParticipant,
        CPFiscalParticipant.fiscal_year_id == CPFiscalYear.fiscal_year_id).where(
        CPFiscalParticipant.participant_id == participant_id).order_by(CPFiscalYear.start_date.desc())).all()
    year_id, program_id = _number(params, 'fiscal_year_id'), _number(params, 'program_id')
    selected_year = next((y for y in years if y.fiscal_year_id == year_id), None)
    if year_id is not None and selected_year is None:
        raise HTTPException(404, 'Año fiscal no asociado al expediente.')
    if program_id is not None and program_id not in context.visible_program_ids:
        raise HTTPException(403, 'Programa no autorizado en este contexto de Comunidad.')
    from_date, to_date = _date(params, 'from_date'), _date(params, 'to_date')
    if from_date and to_date and from_date > to_date:
        raise HTTPException(422, 'La fecha desde no puede ser posterior a la fecha hasta.')
    activity = params.get('activity', '').strip()[:255]
    filters = {'fiscal_year_id': year_id, 'program_id': program_id, 'from_date': from_date,
               'to_date': to_date, 'activity': activity}

    # One row per confirmed session. No current enrollment or fiscal-status filter:
    # a subsequent discharge or closing the year never removes historical attendance.
    base = select(CPActivitySession).join(CPAttendance, CPAttendance.session_id == CPActivitySession.session_id).where(
        CPAttendance.participant_id == participant_id, CPAttendance.is_present == True,  # noqa: E712
        CPActivitySession.program_id.in_(context.visible_program_ids))
    metrics = db.execute(base.with_only_columns(func.count(CPActivitySession.session_id),
                                                func.max(CPActivitySession.session_date))).one()
    filtered = base.join(CPActivity, CPActivity.activity_id == CPActivitySession.activity_id)
    if year_id is not None:
        filtered = filtered.where(CPActivitySession.fiscal_year_id == year_id)
    if program_id is not None:
        filtered = filtered.where(CPActivitySession.program_id == program_id)
    if from_date:
        filtered = filtered.where(CPActivitySession.session_date >= from_date)
    if to_date:
        filtered = filtered.where(CPActivitySession.session_date <= to_date)
    if activity:
        filtered = filtered.where(or_(CPActivity.code.contains(activity, autoescape=True),
                                       CPActivity.description.contains(activity, autoescape=True)))
    history_total = db.scalar(filtered.with_only_columns(func.count(CPActivitySession.session_id))) or 0
    pages = max(1, (history_total + 24) // 25)
    page = min(_number(params, 'history_page', 1), pages)
    history_rows = db.execute(filtered.add_columns(CPActivity, CPProgram, CPFiscalYear, User.username).join(
        CPProgram, CPProgram.program_id == CPActivitySession.program_id).join(
        CPFiscalYear, CPFiscalYear.fiscal_year_id == CPActivitySession.fiscal_year_id).join(
        User, User.user_id == CPActivitySession.created_by_user_id).order_by(
        CPActivitySession.session_date.desc(), CPActivitySession.session_id.desc()).offset((page - 1) * 25).limit(25)).all()

    # Match Faro's monthly trend: at most twelve months ending at the selected end.
    chart_end = to_date or (min(today, selected_year.end_date) if selected_year else today)
    end_month = chart_end.year * 12 + chart_end.month - 1
    start_month = max(12, end_month - 11)
    starts = [value for value in (from_date, selected_year.start_date if selected_year else None) if value]
    for value in starts:
        start_month = max(start_month, value.year * 12 + value.month - 1)
    chart_rows = []
    if start_month <= end_month:
        chart_start = date(start_month // 12, start_month % 12 + 1, 1)
        year_expr, month_expr = extract('year', CPActivitySession.session_date), extract('month', CPActivitySession.session_date)
        monthly = db.execute(filtered.with_only_columns(year_expr, month_expr, func.count(CPActivitySession.session_id)).where(
            CPActivitySession.session_date >= chart_start, CPActivitySession.session_date <= chart_end
        ).group_by(year_expr, month_expr)).all()
        counts = {(int(year), int(month)): count for year, month, count in monthly}
        peak = max(counts.values(), default=0)
        for month_index in range(start_month, end_month + 1):
            year, month = month_index // 12, month_index % 12 + 1
            count = counts.get((year, month), 0)
            chart_rows.append({'label': f'{MONTHS[month - 1]} {year}', 'value': count,
                               'percentage': round(count * 100 / peak) if peak else 0})

    enrollment_query = select(CPFiscalEnrollment).where(CPFiscalEnrollment.participant_id == participant_id,
        CPFiscalEnrollment.program_id.in_(context.visible_program_ids))
    enrollments = db.execute(enrollment_query.add_columns(CPProgram).join(
        CPProgram, CPProgram.program_id == CPFiscalEnrollment.program_id)).all()
    periods = defaultdict(list)
    for period in db.scalars(select(CPEnrollmentPeriod).where(CPEnrollmentPeriod.enrollment_id.in_(
        enrollment_query.with_only_columns(CPFiscalEnrollment.enrollment_id)))):
        periods[period.enrollment_id].append(period)
    fiscal_rows = []
    for year in years:
        matching = [(enrollment, program) for enrollment, program in enrollments if enrollment.fiscal_year_id == year.fiscal_year_id]
        if not matching:
            fiscal_rows.append({'year': year, 'program': None, 'status': 'Sin alta en sus programas'})
        for enrollment, program in matching:
            effective_date = min(today, year.end_date)
            intervals = periods[enrollment.enrollment_id]
            active = any(period.start_date <= effective_date and (period.end_date is None or period.end_date > effective_date)
                         for period in intervals)
            status = 'Activo en este año' if active else ('Baja' if intervals else 'Sin alta')
            fiscal_rows.append({'year': year, 'program': program, 'status': status})
    query = urlencode({key: value for key, value in filters.items() if value is not None and value != ''})
    links = {key: f'/community/participants/{participant_id}?{query}&history_page={number}#historial'
             for key, number in [('first', 1), ('prev', max(1, page - 1)), ('next', min(pages, page + 1)), ('last', pages)]}
    return {'fiscal_years': years, 'fiscal_rows': fiscal_rows, 'participation_total': metrics[0] or 0,
            'last_participation_date': metrics[1], 'history_total': history_total,
            'history_rows': [dict(session=s, activity=a, program=p, year=y, employee=u) for s, a, p, y, u in history_rows],
            'history_page': page, 'history_pages': pages, 'history_links': links, 'filters': filters,
            'chart_rows': chart_rows, 'chart_total': sum(row['value'] for row in chart_rows),
            'chart_period': f"{chart_rows[0]['label']} – {chart_rows[-1]['label']}" if chart_rows else ''}
