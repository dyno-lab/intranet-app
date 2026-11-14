"""Read-only FaroGPT projection of monthly attendance confirmations."""
from datetime import date

from fastapi import HTTPException

from app.models.residential import Residential
from app.services import monthly_attendance


def _metric(key, label, value, definition, aliases=()):
    return {'key': key, 'label': label, 'value': value,
            'definition': definition, 'aliases': list(aliases)}


def build(db, user, proposal_ids, months, year, residential_id, *, today=None):
    """Count obligations by proposal/residential/month without creating periods."""
    if getattr(user, 'role', None) not in {'admin', 'supervisor'}:
        raise HTTPException(403, 'Las consultas de seguimiento requieren administración o supervisión.')
    active_residential = monthly_attendance.scope_id(user)
    if (active_residential is not None and residential_id is not None
            and residential_id != active_residential):
        raise HTTPException(403, 'El residencial no corresponde a tu contexto autorizado.')
    months = sorted(set(months))
    if not 2000 <= year <= 2100 or not months or any(month not in range(1, 13) for month in months):
        raise HTTPException(422, 'Selecciona un año válido y uno o varios meses.')
    today = today or date.today()
    rows, source_links = [], []
    residential_ids = set()
    unconfirmed = review = overdue = 0
    with db.no_autoflush:
        if residential_id is not None and db.get(Residential, residential_id) is None:
            raise HTTPException(422, 'El residencial no está disponible.')
        for proposal_id in dict.fromkeys(proposal_ids):
            for month in months:
                data = monthly_attendance.build_month(db, user, proposal_id, year, month, today=today)
                proposal_name, label = data['proposal'].name, data['label']
                url = data['url']
                source_links.append({'label': f'Seguimiento · {proposal_name} · {label}', 'url': url})
                for row in data['rows']:
                    residential = row['residential']
                    if residential_id is not None and residential.residential_id != residential_id:
                        continue
                    if row['status'] not in {'pending', 'review'}:
                        continue
                    residential_ids.add(residential.residential_id)
                    is_review = row['status'] == 'review'
                    unconfirmed += not is_review
                    review += is_review
                    overdue += data['due_on'] < today
                    rows.append([
                        residential.name, proposal_name, label,
                        'Requiere nueva confirmación' if is_review else 'Sin confirmar',
                        data['due_on'].strftime('%d/%m/%Y'),
                        row['sessions'], row['participations'],
                        {'text': 'Ver seguimiento', 'url': url},
                    ])
    note = ('Una confirmación pendiente corresponde a una propuesta, residencial y mes. '
            'Los cambios posteriores a una confirmación requieren confirmar nuevamente. '
            'Un mes sin actividades deja de estar pendiente cuando el residencial lo confirma expresamente. '
            'Los períodos sin configuración usan los residenciales activos y la fecha límite del día 10 del mes siguiente. '
            'La consulta no confirma meses ni envía recordatorios.')
    if residential_id is not None and active_residential is None:
        note += (' Los enlaces de seguimiento abren la propuesta y el mes completos; '
                 'el resultado del chat conserva el residencial seleccionado.')
    return {
        'title': 'Confirmaciones mensuales pendientes', 'primary': 'pending',
        'metrics': [
            _metric('pending', 'Confirmaciones pendientes', len(rows),
                    'Obligaciones por propuesta, residencial y mes sin confirmar o que requieren nueva confirmación.'),
            _metric('residentials', 'Residenciales pendientes', len(residential_ids),
                    'Residenciales distintos con al menos una confirmación pendiente en el alcance seleccionado.'),
            _metric('unconfirmed', 'Sin confirmar', int(unconfirmed),
                    'Obligaciones que todavía no tienen una confirmación registrada.'),
            _metric('review', 'Requieren nueva confirmación', int(review),
                    'Obligaciones cuya confirmación dejó de estar vigente después de cambios en las asistencias.'),
            _metric('overdue', 'Confirmaciones vencidas', int(overdue),
                    'Confirmaciones pendientes cuya fecha límite es anterior al día de consulta.'),
        ],
        'tables': [{'title': 'Seguimiento pendiente por residencial',
                    'columns': ['Residencial', 'Propuesta', 'Mes', 'Estado', 'Fecha límite',
                                'Actividades', 'Participaciones confirmadas', 'Acción'],
                    'rows': rows}],
        'source_title': 'Confirmación mensual de asistencias',
        'source_links': source_links, 'note': note,
    }
