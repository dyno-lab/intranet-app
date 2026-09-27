"""Advisory matches within Community; never merges or changes existing records."""
from datetime import date

from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select

from app.core.config import require_session_secret
from app.models.community import CPParticipant
from app.services.community_identity import BasicIdentity, normalize_identity_name


def _demographics(fields):
    name = normalize_identity_name(fields.get('nombre'))
    surname = normalize_identity_name(fields.get('apellido_paterno'))
    try:
        birth = date.fromisoformat(str(fields.get('fecha_nacimiento') or '').strip())
    except ValueError:
        return None  # The existing registration validator reports invalid dates.
    return [name, surname, birth.isoformat()] if name and surname else None


def duplicate_participants(db, fields):
    identity = _demographics(fields)
    if identity is None:
        return []
    # Basic identity is already available through the cross-program lookup. Fetch
    # only same-birthday candidates, without contact, program or historical data.
    candidates = db.execute(select(
        CPParticipant.participant_id, CPParticipant.expediente_num, CPParticipant.nombre,
        CPParticipant.apellido_paterno, CPParticipant.apellido_materno, CPParticipant.fecha_nacimiento,
    ).where(CPParticipant.fecha_nacimiento == date.fromisoformat(identity[2]))
      .order_by(CPParticipant.participant_id)).all()
    return [BasicIdentity(*row) for row in candidates
            if normalize_identity_name(row.nombre) == identity[0]
            and normalize_identity_name(row.apellido_paterno) == identity[1]]


def _serializer():
    return URLSafeTimedSerializer(require_session_secret(), salt='community-duplicate-registration')


def _confirmation_data(fields, matches, user_id, csrf):
    return [user_id, csrf, _demographics(fields),
            [[match.participant_id, match.expediente_num] for match in matches]]


def duplicate_confirmation(fields, matches, *, user_id, csrf):
    return _serializer().dumps(_confirmation_data(fields, matches, user_id, csrf))


def confirmed_duplicate(submitted, fields, matches, *, user_id, csrf):
    if not submitted:
        return False
    try:
        confirmed = _serializer().loads(submitted, max_age=900)
    except BadSignature:
        return False
    # Recheck the identity and all current matches on each submission. A changed
    # identity, another session, or a newly created match requires a fresh warning.
    return confirmed == _confirmation_data(fields, matches, user_id, csrf)
