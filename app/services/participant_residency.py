"""Stable historical joins and date eligibility for residential stays."""
from sqlalchemy import and_, or_, select, extract
from sqlalchemy.orm import aliased
from fastapi import HTTPException

from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.person import Person
from app.models.participant import Participant
from app.models.proposal_participant import ProposalParticipant
from app.models.residential import Residential


def stay_on_date(day, model=ProposalParticipant):
    return and_(or_(model.valid_from.is_(None), model.valid_from <= day),
                or_(model.valid_until.is_(None), day < model.valid_until))


def eligible_on_date(record, day):
    start, end = getattr(record, "valid_from", None), getattr(record, "valid_until", None)
    return (start is None or start <= day) and (end is None or day < end)


def lock_residential(db, residential_id):
    if residential_id is not None:
        db.execute(select(Residential.residential_id).where(Residential.residential_id == residential_id)
                   .with_hint(Residential, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")).scalar_one()


def require_session_stay_compatibility(db, session, day, proposal_id):
    """Changing a session must not move its attendance across a residential stay."""
    lock_residential(db, session.residential_id)
    records = db.scalars(select(ProposalParticipant).select_from(Attendance).join(ActivitySession)
        .outerjoin(Person, Person.legacy_participant_id == Attendance.participant_id)
        .join(ProposalParticipant, session_snapshot_join())
        .where(Attendance.session_id == session.session_id, Attendance.attended == True)).all()
    if any(not eligible_on_date(record, day) or record.proposal_id != proposal_id for record in records):
        raise HTTPException(409, "La fecha o propuesta no corresponde a la inscripción de una asistencia existente. "
                            "El cambio afectaría su historial; revise las asistencias antes de editar la sesión.")


def session_snapshot_join(person_id=None):
    person_id = Person.person_id if person_id is None else person_id
    return and_(
        ProposalParticipant.proposal_id == ActivitySession.proposal_id,
        or_(
            ProposalParticipant.proposal_participant_id == Attendance.proposal_participant_id,
            and_(Attendance.proposal_participant_id.is_(None),
                 ProposalParticipant.person_id == person_id,
                 stay_on_date(ActivitySession.session_date),
                 or_(ProposalParticipant.residential_id == ActivitySession.residential_id,
                     ProposalParticipant.residential_id.is_(None), ActivitySession.residential_id.is_(None))),
        ),
    )


def monthly_snapshot_join(proposal_id, residential_id, year, month):
    """One snapshot per person/report, including a departure during the month."""
    candidate = aliased(ProposalParticipant)
    ordinal = year * 12 + month
    arrival = extract("year", candidate.valid_from) * 12 + extract("month", candidate.valid_from)
    departure = extract("year", candidate.valid_until) * 12 + extract("month", candidate.valid_until)
    chosen = (select(candidate.proposal_participant_id)
              .where(candidate.person_id == Person.person_id, candidate.proposal_id == proposal_id,
                     or_(candidate.residential_id == residential_id, candidate.residential_id.is_(None),
                         residential_id == None),  # noqa: E711 - supports SQL columns and legacy NULL reports
                     or_(candidate.valid_from.is_(None), arrival <= ordinal),
                     or_(candidate.valid_until.is_(None), departure > ordinal,
                         and_(departure == ordinal, extract("day", candidate.valid_until) > 1)))
              .order_by(candidate.valid_from.desc(), candidate.proposal_participant_id.desc())
              .limit(1).correlate_except(candidate).scalar_subquery())
    return and_(ProposalParticipant.person_id == Person.person_id,
                ProposalParticipant.proposal_id == proposal_id,
                ProposalParticipant.proposal_participant_id == chosen)


def monthly_participants(db, report, participant_id=None):
    from app.services.proposal_participant_snapshots import participant_snapshot_view
    matched = ProposalParticipant.proposal_participant_id.is_not(None)
    enrollment = aliased(ProposalParticipant)
    has_enrollment = select(enrollment.proposal_participant_id).where(
        enrollment.person_id == Person.person_id, enrollment.proposal_id == report.proposal_id
    ).exists()
    statement = (select(Participant, ProposalParticipant)
                 .outerjoin(Person, Person.legacy_participant_id == Participant.participant_id)
                 .outerjoin(ProposalParticipant, monthly_snapshot_join(report.proposal_id, report.residential_id,
                                                                       report.report_year, report.report_month))
                 .where(or_(and_(matched, ProposalParticipant.is_active == True),
                            and_(~matched, ~has_enrollment, Participant.is_active == True,
                                 or_(Participant.residential_id == report.residential_id,
                                     report.residential_id is None))))
                 .order_by(Participant.apellido_paterno, Participant.nombre))
    if participant_id is not None:
        statement = statement.where(Participant.participant_id == participant_id)
    return [participant_snapshot_view(p, snapshot) for p, snapshot in db.execute(statement).all()]
