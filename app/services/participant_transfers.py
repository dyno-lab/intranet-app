"""Transactional relocation. Historical enrollment and attendance IDs never change."""
from datetime import date

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm.attributes import set_committed_value

from app.core.period_guard import require_proposal_period_open
from app.core.proposal_guard import is_proposal_finalized
from app.core.record_identifiers import build_expediente_number
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.participant import Participant
from app.models.participant_transfer import ParticipantResidentialNumber, ParticipantTransfer
from app.models.person import Person
from app.models.proposal import Proposal
from app.models.proposal_participant import ProposalParticipant
from app.models.residential import Residential
from app.services.proposal_participant_sync import get_proposal_participant_update_values


def _locked(statement, model):
    return statement.with_hint(model, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")


def require_available_number(db, residential_id, sequence=None, *, participant_id=None, expediente_num=None):
    sequence = (sequence or "").strip()
    expediente_num = (expediente_num or "").strip()
    # The same residential lock is used by creation, edits and transfers.
    db.execute(_locked(select(Residential).where(Residential.residential_id == residential_id), Residential)).scalar_one()
    conditions = []
    if sequence:
        conditions.append(and_(ParticipantResidentialNumber.residential_id == residential_id,
                               ParticipantResidentialNumber.sequence == sequence))
    if expediente_num:
        conditions.append(ParticipantResidentialNumber.expediente_num == expediente_num)
    if not conditions:
        return
    statement = select(ParticipantResidentialNumber.number_id).where(or_(*conditions))
    if participant_id is not None:
        statement = statement.where(ParticipantResidentialNumber.participant_id != participant_id)
    if db.scalar(statement.limit(1)) is not None:
        raise HTTPException(409, "El expediente está reservado por el historial de otro participante. Seleccione otra secuencia.")


def current_transfer_enrollments(db, participant_id):
    return db.execute(select(ProposalParticipant, Proposal)
                      .join(Person, Person.person_id == ProposalParticipant.person_id)
                      .join(Proposal, Proposal.proposal_id == ProposalParticipant.proposal_id)
                      .where(Person.legacy_participant_id == participant_id,
                             ProposalParticipant.valid_until.is_(None))
                      .with_hint(ProposalParticipant, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
                      .order_by(Proposal.proposal_id)).all()


def _destination_number(db, participant, destination, effective_date):
    owned = db.scalar(select(ParticipantResidentialNumber).where(
        ParticipantResidentialNumber.participant_id == participant.participant_id,
        ParticipantResidentialNumber.residential_id == destination.residential_id)
        .order_by(ParticipantResidentialNumber.number_id).limit(1))
    if owned is not None:
        conflict = db.scalar(select(Participant.participant_id).where(
            Participant.participant_id != participant.participant_id,
            or_(Participant.expediente_num == owned.expediente_num,
                and_(owned.sequence is not None, Participant.residential_id == destination.residential_id,
                     Participant.exp_seq4 == owned.sequence))).limit(1))
        if conflict is not None:
            raise HTTPException(409, "El expediente reservado presenta un conflicto. Revise la numeración antes de trasladar.")
        return owned
    occupied = set(db.scalars(select(Participant.exp_seq4).where(Participant.residential_id == destination.residential_id)))
    occupied.update(db.scalars(select(ParticipantResidentialNumber.sequence)
                              .where(ParticipantResidentialNumber.residential_id == destination.residential_id)))
    preferred = participant.exp_seq4
    candidates = ([preferred] if preferred and len(preferred) == 4 and preferred.isdigit() else [])
    candidates.extend(f"{value:04d}" for value in range(1, 10000))
    for sequence in candidates:
        if sequence not in occupied:
            number = build_expediente_number(year=effective_date.year, residential_code=destination.code, sequence=sequence)
            collision = db.scalar(select(Participant.participant_id).where(Participant.expediente_num == number).limit(1))
            historical = db.scalar(select(ParticipantResidentialNumber.number_id)
                                   .where(ParticipantResidentialNumber.expediente_num == number).limit(1))
            if collision is None and historical is None:
                return ParticipantResidentialNumber(participant_id=participant.participant_id,
                    residential_id=destination.residential_id, sequence=sequence,
                    expediente_num=number, exp_year=effective_date.year)
    raise HTTPException(409, "El residencial de destino no tiene secuencias de expediente disponibles.")


def _prepare_transfer(db, *, participant_id, destination_id, effective_date, reason, edificio, apart,
                      actor, expected_residential_id):
    if actor.role not in {"admin", "supervisor"} or getattr(actor, "_active_residential_id", None) is not None:
        raise HTTPException(403, "El traslado requiere administrador o supervisor en acceso general.")
    if not isinstance(effective_date, date) or not date(2000, 1, 1) <= effective_date <= date.today():
        raise HTTPException(422, "Seleccione una fecha efectiva válida, que no sea futura.")
    reason = (reason or "").strip()
    if not reason or len(reason) > 500:
        raise HTTPException(422, "Indique el motivo del traslado (máximo 500 caracteres).")
    if len(edificio or "") > 50 or len(apart or "") > 50:
        raise HTTPException(422, "Edificio y apartamento admiten un máximo de 50 caracteres.")
    if destination_id == expected_residential_id:
        raise HTTPException(409, "Seleccione un residencial diferente al actual.")
    # Stable lock order also protects two transfers targeting the same sequence.
    residentials = {r.residential_id: r for r in db.scalars(_locked(
        select(Residential).where(Residential.residential_id.in_([destination_id, expected_residential_id]))
        .order_by(Residential.residential_id), Residential))}
    destination = residentials.get(destination_id)
    if destination is None or not destination.is_active or not destination.code.strip():
        raise HTTPException(409, "El residencial de destino no está disponible.")
    participant = db.scalar(_locked(select(Participant).where(Participant.participant_id == participant_id)
                                    .execution_options(populate_existing=True), Participant))
    if participant is None:
        raise HTTPException(404, "Participante no encontrado.")
    if participant.residential_id != expected_residential_id:
        raise HTTPException(409, "El participante ya cambió de residencial. Recargue su expediente.")
    previous_date = db.scalar(select(func.max(ParticipantTransfer.effective_date))
                              .where(ParticipantTransfer.participant_id == participant_id))
    if previous_date is not None and effective_date <= previous_date:
        raise HTTPException(409, "La fecha debe ser posterior al último traslado.")
    enrollments = [(record, proposal) for record, proposal in current_transfer_enrollments(db, participant_id)
                   if not is_proposal_finalized(proposal) and proposal.is_active]
    if not enrollments:
        raise HTTPException(409, "El participante debe estar inscrito en una propuesta vigente para trasladarlo.")
    for record, proposal in enrollments:
        if record.residential_id != expected_residential_id:
            raise HTTPException(409, "Una inscripción vigente pertenece a otro residencial. Revísela antes del traslado.")
        if record.valid_from is not None and effective_date <= record.valid_from:
            raise HTTPException(409, "La fecha debe ser posterior al inicio de la inscripción actual.")
        require_proposal_period_open(proposal, effective_date.month, effective_date.year)
    proposal_ids = [proposal.proposal_id for _, proposal in enrollments]
    conflict = db.scalar(select(Attendance.attendance_id).join(ActivitySession)
                         .outerjoin(ProposalParticipant, ProposalParticipant.proposal_participant_id == Attendance.proposal_participant_id)
                         .where(Attendance.attended == True,
                                or_(Attendance.participant_id == participant_id,
                                    ProposalParticipant.person_id == enrollments[0][0].person_id),
                                ActivitySession.proposal_id.in_(proposal_ids),
                                ActivitySession.session_date >= effective_date).limit(1))
    if conflict is not None:
        raise HTTPException(409, "Ya hay asistencias desde esa fecha. Use una fecha posterior para conservarlas en su residencial original.")
    return participant, destination, enrollments, reason


def preview_transfer(db, **values):
    participant, destination, enrollments, reason = _prepare_transfer(db, **values)
    number = _destination_number(db, participant, destination, values["effective_date"])
    return {"expediente_num": number.expediente_num, "proposals": [p for _, p in enrollments]}


def transfer_participant(db, *, expected_expediente_num=None, **values):
    """Caller commits/rolls back the entire unit. No services or attendances are edited."""
    participant, destination, enrollments, reason = _prepare_transfer(db, **values)
    participant_id = participant.participant_id
    destination_id = destination.residential_id
    effective_date = values["effective_date"]
    expected_residential_id = values["expected_residential_id"]
    edificio, apart, actor = values["edificio"], values["apart"], values["actor"]
    new_number = _destination_number(db, participant, destination, effective_date)
    if expected_expediente_num is not None and expected_expediente_num != new_number.expediente_num:
        raise HTTPException(409, "La numeración disponible cambió. Revise y confirme el nuevo expediente.")
    old_number = participant.expediente_num
    reserved = db.scalar(select(ParticipantResidentialNumber)
                          .where(ParticipantResidentialNumber.expediente_num == old_number))
    if reserved is not None and reserved.participant_id != participant_id:
        raise HTTPException(409, "El expediente de origen tiene una reserva de otra persona.")
    if reserved is None:
        db.add(ParticipantResidentialNumber(participant_id=participant_id,
               residential_id=expected_residential_id, sequence=participant.exp_seq4 or None,
               expediente_num=old_number, exp_year=participant.exp_year or effective_date.year))
    db.add(new_number)
    # Core UPDATE avoids SQL Server/NOCOUNT row-count false positives, as in session edits.
    enrollment_table = ProposalParticipant.__table__
    db.execute(enrollment_table.update().where(enrollment_table.c.proposal_participant_id.in_(
        [record.proposal_participant_id for record, _ in enrollments])).values(valid_until=effective_date))
    for record, _ in enrollments:
        set_committed_value(record, "valid_until", effective_date)
    db.flush()  # Close old stays before creating the next current row under the unique index.
    # Household identity is local to the old address and must be reassessed at destination.
    participant_table = Participant.__table__
    db.execute(participant_table.update().where(participant_table.c.participant_id == participant_id).values(
        residential_id=destination_id, expediente_num=new_number.expediente_num,
        exp_year=new_number.exp_year, exp_seq4=new_number.sequence,
        exp_employee_initials=destination.code.strip().upper(), edificio=(edificio or "").strip() or None,
        apart=(apart or "").strip() or None, is_head_of_household=False, grupo_familiar=None))
    db.refresh(participant)
    for record, proposal in enrollments:
        values = get_proposal_participant_update_values(participant)
        # A move must not silently reactivate an inactive proposal enrollment.
        values["is_active"] = record.is_active
        values["estatus"] = record.estatus
        db.add(ProposalParticipant(proposal_id=proposal.proposal_id, person_id=record.person_id,
                                   residential_id=destination_id, created_by_user_id=actor.user_id,
                                   valid_from=effective_date, **values))
    audit = ParticipantTransfer(participant_id=participant_id, from_residential_id=expected_residential_id,
                                to_residential_id=destination_id, effective_date=effective_date,
                                old_expediente_num=old_number, new_expediente_num=new_number.expediente_num,
                                reason=reason, created_by_user_id=actor.user_id,
                                proposal_codes=", ".join(proposal.code for _, proposal in enrollments))
    db.add(audit); db.flush()
    return audit
