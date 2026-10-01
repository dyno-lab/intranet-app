"""Fiscal-year administration; closing and operation locks remain shared services."""
from calendar import monthrange
from datetime import date

from sqlalchemy import func, select, union

from app.models.community import CPFiscalYear
from app.models.community_fiscal import CPFiscalEnrollment, CPFiscalParticipant, CPFiscalState
from app.models.community_operations import CPActivitySession, CPGradeReport
from app.models.user import User
from app.services.community import _date, _text
from app.services.community_fiscal import require_fiscal_writable

MONTHS = ('Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto',
          'Septiembre', 'Octubre', 'Noviembre', 'Diciembre')


def used_year_ids(db, fiscal_year_id=None):
    queries = [select(model.fiscal_year_id) for model in
               (CPFiscalParticipant, CPFiscalEnrollment, CPActivitySession, CPGradeReport)]
    if fiscal_year_id is not None:
        queries = [query.where(query.selected_columns.fiscal_year_id == fiscal_year_id) for query in queries]
    return set(db.scalars(union(*queries)))


def closing_months(year, today=None):
    today = today or date.today()
    options = []
    for value in range(year.start_date.year * 12 + year.start_date.month - 1,
                       min(year.end_date, today).year * 12 + min(year.end_date, today).month):
        year_num, zero_month = divmod(value, 12)
        month = zero_month + 1
        last = min(date(year_num, month, monthrange(year_num, month)[1]), year.end_date)
        if last <= today:
            label = f'{MONTHS[zero_month]} {year_num}'
            if last.day != monthrange(year_num, month)[1]:
                label += f' · fin del año fiscal: {last:%d/%m/%Y}'
            options.append({'value': last.isoformat(), 'label': label})
    return options


def fiscal_year_management(db):
    years = db.scalars(select(CPFiscalYear).order_by(CPFiscalYear.start_date.desc())).all()
    states = {state.fiscal_year_id: state for state in db.scalars(select(CPFiscalState))}
    counts = dict(db.execute(select(CPFiscalParticipant.fiscal_year_id, func.count()).group_by(
        CPFiscalParticipant.fiscal_year_id)).all())
    used = used_year_ids(db)
    locked_dates = used | {fyid for fyid, state in states.items() if state.snapshots_frozen or state.locked_through}
    users = dict(db.execute(select(User.user_id, User.username).where(User.user_id.in_(
        select(CPFiscalState.closed_by_user_id).where(CPFiscalState.closed_by_user_id.is_not(None))))).all())
    return {'years': years, 'states': states, 'participant_counts': counts, 'locked_date_ids': locked_dates,
            'closing_users': users, 'month_options': {year.fiscal_year_id: closing_months(year) for year in years}}


def edit_fiscal_year(db, fiscal_year_id, *, code, name, start_date, end_date):
    year = require_fiscal_writable(db, fiscal_year_id)
    code = _text(code, 'Código de año fiscal', 50, required=True).upper()
    name = _text(name, 'Nombre de año fiscal', 150, required=True)
    start_date, end_date = _date(start_date, 'Fecha de inicio'), _date(end_date, 'Fecha de fin')
    if end_date < start_date:
        raise ValueError('La fecha de fin no puede ser anterior a la fecha de inicio.')
    if (start_date, end_date) != (year.start_date, year.end_date):
        state = db.get(CPFiscalState, fiscal_year_id)
        if used_year_ids(db, fiscal_year_id) or (state and (state.snapshots_frozen or state.locked_through)):
            raise ValueError('Las fechas no se pueden cambiar: el año fiscal tiene datos asociados, períodos cerrados o datos congelados.')
    if db.scalar(select(CPFiscalYear.fiscal_year_id).where(CPFiscalYear.code == code,
        CPFiscalYear.fiscal_year_id != fiscal_year_id)) is not None:
        raise ValueError('Ya existe un año fiscal con ese código.')
    year.code, year.name, year.start_date, year.end_date = code, name, start_date, end_date
    db.flush()
    return year
