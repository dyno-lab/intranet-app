"""Read-only pre-save matching and session-bound decisions for both registration forms."""
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
import json

from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select

from app.core.config import require_session_secret, settings
from app.models.community_identity import CPIdentityReview
from app.services.community_identity import BasicIdentity, _identity_query, _model, _source_column, normalize_identity_name, record_identity_decision, lock_identity_operations


CONTACTS = {'community': 'gacosta@csifpr.org', 'faro': 'eyrivera@csifpr.org'}
LABELS = {'community': 'Comunidad y Prevención', 'faro': 'Faro'}


@dataclass(frozen=True)
class RegistrationDecision:
    action: str
    candidate_ids: tuple[int, ...]


def draft_identity(fields):
    try:
        birth = date.fromisoformat(str(fields.get('fecha_nacimiento') or '').strip())
    except ValueError:
        return None
    if not normalize_identity_name(fields.get('nombre')) or not normalize_identity_name(fields.get('apellido_paterno')):
        return None
    return BasicIdentity(0, str(fields.get('expediente_num') or 'Número pendiente de guardar'),
        str(fields['nombre']).strip(), str(fields['apellido_paterno']).strip(),
        str(fields.get('apellido_materno') or '').strip(), birth)


def exact_identity(source, candidate):
    return (source.fecha_nacimiento is not None and source.fecha_nacimiento == candidate.fecha_nacimiento
        and all(normalize_identity_name(getattr(source, key)) == normalize_identity_name(getattr(candidate, key))
                for key in ('nombre', 'apellido_paterno')))


def registration_candidates(db, source_module, source):
    """Hold candidate locks until the caller commits registration or returns the prompt."""
    if not settings.COMMUNITY_ENABLED or source is None:
        return [], set()
    lock_identity_operations(db)
    other = 'faro' if source_module == 'community' else 'community'
    model = _model(other)
    query = _identity_query(model).where(model.fecha_nacimiento == source.fecha_nacimiento).order_by(model.participant_id)
    query = query.with_hint(model, 'WITH (UPDLOCK, HOLDLOCK)', dialect_name='mssql')
    matches = [BasicIdentity(*row) for row in db.execute(query)]
    matches = [row for row in matches if exact_identity(source, row)]
    linked = set(db.scalars(select(_source_column(other)).where(
        CPIdentityReview.is_same_person == True,  # noqa: E712
        _source_column(other).in_(select(model.participant_id).where(model.fecha_nacimiento == source.fecha_nacimiento))))) if matches else set()
    return matches, linked


def _proof_data(source_module, source, candidates, linked, actor_user_id, csrf):
    payload = [source_module, asdict(source), [asdict(item) for item in candidates], sorted(linked), actor_user_id, csrf]
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def prepare_registration_identity(db, source_module, fields, form, *, actor_user_id, csrf):
    """Return (prompt, decision). Neither branch creates a participant or review."""
    if not settings.COMMUNITY_ENABLED:
        return None, None
    source = draft_identity(fields)
    candidates, linked = registration_candidates(db, source_module, source)
    if not candidates:
        if form.get('identity_decision') == 'yes':
            raise ValueError('La coincidencia dejó de corresponder a los datos actuales. Revise el formulario antes de guardar.')
        return None, None
    serializer = URLSafeTimedSerializer(require_session_secret(), salt='cross-module-identity-registration')
    expected = _proof_data(source_module, source, candidates, linked, actor_user_id, csrf)
    valid = False
    try:
        valid = serializer.loads(str(form.get('identity_confirmation') or ''), max_age=900) == expected
    except BadSignature:
        pass
    action = form.get('identity_decision')
    error = None
    if valid and action in ('yes', 'no', 'pending'):
        if action == 'yes':
            try:
                candidate_id = int(form.get('identity_candidate_id', ''))
            except (ValueError, TypeError):
                candidate_id = None
            if candidate_id in {row.participant_id for row in candidates} and candidate_id not in linked:
                return None, RegistrationDecision('yes', (candidate_id,))
            error = 'Seleccione un expediente disponible para vincular. Los vínculos existentes requieren revisión.'
        elif action == 'no':
            return None, RegistrationDecision('no', tuple(row.participant_id for row in candidates))
        else:
            return None, RegistrationDecision('pending', ())
    elif form.get('identity_confirmation'):
        error = 'Revise nuevamente la coincidencia: los datos cambiaron o la confirmación venció.'
    other = 'faro' if source_module == 'community' else 'community'
    return {'source_module': source_module, 'source': source, 'source_label': LABELS[source_module],
            'other_label': LABELS[other], 'contact': CONTACTS[source_module], 'candidates': candidates,
            'linked_ids': linked, 'confirmation': serializer.dumps(expected), 'error': error}, None


def save_registration_identity(db, source_module, participant_id, decision, *, actor_user_id):
    """Use only a decision returned by prepare_registration_identity in this transaction."""
    if decision is None or decision.action == 'pending':
        return
    for candidate_id in decision.candidate_ids:
        cp_id, faro_id = (participant_id, candidate_id) if source_module == 'community' else (candidate_id, participant_id)
        record_identity_decision(db, cp_id, faro_id, decision.action == 'yes', source_module, actor_user_id)
    db.flush()
