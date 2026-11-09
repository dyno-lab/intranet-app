"""Read-only access to a residential stay, without reading the destination profile."""
import json
from datetime import date, timedelta
from math import ceil
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select

from app.core.residential_scope import has_global_residential_access, require_record_residential_id
from app.models.activity_code import ActivityCode
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.participant import Participant
from app.models.participant_transfer import ParticipantTransfer
from app.models.person import Person
from app.models.proposal import Proposal
from app.models.proposal_participant import ProposalParticipant
from app.models.residential import Residential
from app.models.participant_profile_field import ParticipantProfileField
from app.models.participant_profile_field_value import ParticipantProfileFieldValue
from app.services.proposal_participant_sync import get_proposal_participant_update_values


def capture_transfer_snapshot(db, participant):
    fields = db.execute(select(ParticipantProfileField, ParticipantProfileFieldValue.value)
        .join(ParticipantProfileFieldValue, ParticipantProfileFieldValue.participant_profile_field_id == ParticipantProfileField.participant_profile_field_id)
        .where(ParticipantProfileFieldValue.participant_id == participant.participant_id)
        .order_by(ParticipantProfileField.sort_order, ParticipantProfileField.participant_profile_field_id)).all()
    payload = {'version': 1, 'core': get_proposal_participant_update_values(participant),
               'fields': [{'key': field.field_key, 'label': field.label, 'value': value or ''} for field, value in fields]}
    return json.dumps(payload, ensure_ascii=False, default=lambda value: value.isoformat())


def _closed_stays():
    return (select(ParticipantTransfer, ProposalParticipant)
        .join(Person, Person.legacy_participant_id == ParticipantTransfer.participant_id)
        .join(ProposalParticipant, and_(ProposalParticipant.person_id == Person.person_id,
            ProposalParticipant.residential_id == ParticipantTransfer.from_residential_id,
            ProposalParticipant.valid_until == ParticipantTransfer.effective_date)))


def residential_history_page(db, residential_id, *, page=1, per_page=25, expediente='', born_before=None, born_after=None):
    """One archived entry per person; returned residents remain in the current list."""
    empty = {'rows': [], 'total': 0, 'page': 1, 'pages': 1, 'residential': None}
    if not residential_id:
        return empty
    rank = _closed_stays().with_only_columns(
        ParticipantTransfer.transfer_id, ParticipantTransfer.participant_id,
        ProposalParticipant.expediente_num, ProposalParticipant.nombre, ProposalParticipant.apellido_paterno,
        ProposalParticipant.fecha_nacimiento,
        func.row_number().over(partition_by=ParticipantTransfer.participant_id,
            order_by=(ParticipantTransfer.effective_date.desc(), ParticipantTransfer.transfer_id.desc(),
                      ProposalParticipant.proposal_participant_id.desc())).label('position'))
    rank = rank.join(Participant, Participant.participant_id == ParticipantTransfer.participant_id).where(
        ParticipantTransfer.from_residential_id == residential_id,
        or_(Participant.residential_id != residential_id, Participant.residential_id.is_(None))).subquery()
    selected = select(rank.c.transfer_id).where(rank.c.position == 1)
    if expediente:
        selected = selected.where(func.upper(func.ltrim(func.rtrim(rank.c.expediente_num))) == expediente.strip().upper())
    if born_before is not None:
        selected = selected.where(rank.c.fecha_nacimiento <= born_before)
    if born_after is not None:
        selected = selected.where(rank.c.fecha_nacimiento > born_after)
    total = db.scalar(select(func.count()).select_from(selected.subquery())) or 0
    if not total:
        return {**empty, 'residential': db.get(Residential, residential_id)}
    pages = max(1, ceil(total / per_page))
    page = min(max(1, page or 1), pages)
    ids = list(db.scalars(selected.order_by(rank.c.apellido_paterno, rank.c.nombre, rank.c.transfer_id)
                         .offset((page - 1) * per_page).limit(per_page)))
    pairs = db.execute(_closed_stays().where(ParticipantTransfer.transfer_id.in_(ids))
                       .order_by(ProposalParticipant.proposal_participant_id)).all() if ids else []
    chosen = {audit.transfer_id: (audit, snapshot) for audit, snapshot in pairs}
    destinations = {r.residential_id: r for r in db.scalars(select(Residential).where(
        Residential.residential_id.in_({audit.to_residential_id for audit, _ in pairs})))} if pairs else {}
    rows = [{'audit': chosen[identifier][0], 'p': chosen[identifier][1],
             'destination': destinations.get(chosen[identifier][0].to_residential_id)} for identifier in ids]
    return {'rows': rows, 'total': total, 'page': page, 'pages': pages, 'residential': db.get(Residential, residential_id)}


def participant_history_context(db, request, user, participant_id, transfer_id, *, page=1, proposal_id=None,
                                from_date=None, to_date=None):
    audit = db.get(ParticipantTransfer, transfer_id)
    if audit is None or audit.participant_id != participant_id:
        raise HTTPException(404, 'Historial no encontrado.')
    if not has_global_residential_access(user):
        if require_record_residential_id(request, user) != audit.from_residential_id:
            raise HTTPException(403, 'Este historial pertenece a otro residencial.')
    pairs = db.execute(_closed_stays().where(ParticipantTransfer.transfer_id == transfer_id)
                       .order_by(ProposalParticipant.proposal_participant_id.desc())).all()
    if not pairs:
        raise HTTPException(404, 'No hay una inscripción histórica disponible para este traslado.')
    snapshot = pairs[0][1]
    # Never fall back to current Participant or mutable profile-field values.
    saved = json.loads(audit.profile_snapshot_json) if audit.profile_snapshot_json else None
    core = saved['core'] if saved else get_proposal_participant_update_values(snapshot)
    core = dict(core)
    if isinstance(core.get('fecha_nacimiento'), str):
        core['fecha_nacimiento'] = date.fromisoformat(core['fecha_nacimiento'])
    core.update(participant_id=participant_id, expediente_num=audit.old_expediente_num)
    start = db.scalar(select(func.max(ParticipantTransfer.effective_date)).where(
        ParticipantTransfer.participant_id == participant_id,
        ParticipantTransfer.to_residential_id == audit.from_residential_id,
        ParticipantTransfer.effective_date < audit.effective_date))
    cutoff = audit.effective_date - timedelta(days=1)
    dob = core.get('fecha_nacimiento')
    age = cutoff.year - dob.year - ((cutoff.month, cutoff.day) < (dob.month, dob.day)) if dob else None
    enrollment_ids = select(ProposalParticipant.proposal_participant_id).where(
        ProposalParticipant.person_id == snapshot.person_id)
    conditions = [Attendance.attended == True, ActivitySession.residential_id == audit.from_residential_id,
                  ActivitySession.session_date < audit.effective_date,
                  or_(Attendance.participant_id == participant_id, Attendance.proposal_participant_id.in_(enrollment_ids))]
    if start:
        conditions.append(ActivitySession.session_date >= start)
    sessions = select(ActivitySession.session_id).join(Attendance, Attendance.session_id == ActivitySession.session_id).where(*conditions)
    proposal_options = db.scalars(select(Proposal).where(Proposal.proposal_id.in_(
        select(ActivitySession.proposal_id).where(ActivitySession.session_id.in_(sessions))))
        .order_by(Proposal.code)).all()
    if proposal_id:
        conditions.append(ActivitySession.proposal_id == proposal_id)
    if from_date:
        conditions.append(ActivitySession.session_date >= from_date)
    if to_date:
        conditions.append(ActivitySession.session_date <= to_date)
    records = (select(Attendance, ActivitySession, ActivityCode, Employee, Proposal)
        .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
        .outerjoin(ActivityCode, ActivityCode.activity_code_id == ActivitySession.activity_code_id)
        .outerjoin(Employee, Employee.employee_id == ActivitySession.employee_id)
        .join(Proposal, Proposal.proposal_id == ActivitySession.proposal_id).where(*conditions))
    total = db.scalar(select(func.count()).select_from(records.subquery())) or 0
    pages = max(1, ceil(total / 25)); page = min(max(1, page or 1), pages)
    entries = db.execute(records.order_by(ActivitySession.session_date.desc(), ActivitySession.session_id.desc(), Attendance.attendance_id)
                         .offset((page - 1) * 25).limit(25)).all()
    stays = db.scalars(select(ParticipantTransfer).where(ParticipantTransfer.participant_id == participant_id,
        ParticipantTransfer.from_residential_id == audit.from_residential_id).order_by(ParticipantTransfer.effective_date.desc())).all()
    return {'p': SimpleNamespace(**core), 'audit': audit, 'age': age,
            'source': db.get(Residential, audit.from_residential_id),
            'destination': db.get(Residential, audit.to_residential_id),
            'stay_start': start, 'cutoff': cutoff, 'profile_fields': saved['fields'] if saved else [],
            'has_profile_snapshot': saved is not None, 'stays': stays, 'entries': entries,
            'total': total, 'page': page, 'pages': pages, 'proposal_options': proposal_options,
            'selected_proposal_id': proposal_id, 'from_date': from_date, 'to_date': to_date}
