"""Additional participant tables for the complete report's supplied layouts.

Existing reports remain responsible for snapshot selection, participant identity,
current-age semantics and cumulative unique counts. The four age bands below
only regroup those same monthly participants for the new target comparison.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.helpers.report_proposals import proposal_ids as normalize_proposal_ids
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.participant import Participant
from app.models.person import Person
from app.models.proposal import Proposal
from app.models.proposal_participant import ProposalParticipant


def _population_counts(pairs, selected_ids):
    from app.api.routes import reports

    counts = {key: {"f": 0, "m": 0, "total": 0}
              for key in ("children", "youth", "adults", "older")}
    for participant in reports._report_participant_views(pairs, selected_ids):
        age = reports._calc_age(participant.fecha_nacimiento)
        if age is None or age < 0:
            continue
        key = "children" if age <= 12 else "youth" if age <= 18 else "adults" if age <= 59 else "older"
        gender = reports._normalize_text(participant.genero).upper()
        if gender.startswith("F"):
            counts[key]["f"] += 1
        elif gender.startswith("M"):
            counts[key]["m"] += 1
        counts[key]["total"] += 1
    return counts


def build_supplemental_data(
    db: Session,
    current_user,
    proposal_ids: list[int],
    month: int,
    year: int,
    residentials: list[dict],
) -> dict:
    """Return monthly age/sex rows and cumulative uniques, using only SELECT.

    ``residentials`` is the complete report's existing list of residential
    contexts. Its active-location scope controls individual rows; global totals
    still include historical inactive and unassigned locations, as before.

    ``target_cumulative`` exposes date objects in ``start_date``, ``end_date``
    and ``proposal_starts`` (None for proposals without confirmed attendance by
    the report's end). Participants are unique across all selected proposals,
    never the sum of monthly, residential or proposal unique counts.
    """
    require_admin(current_user)
    selected_ids = normalize_proposal_ids(proposal_ids)
    if not selected_ids:
        raise HTTPException(422, "Selecciona al menos una propuesta.")
    try:
        month_start = date(year, month, 1)
        report_end = date(year, month, monthrange(year, month)[1])
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Selecciona un mes y año válidos.") from exc

    from app.api.routes import reports
    from app.services.full_monthly_report_data import _GlobalReportUser

    report_user = _GlobalReportUser(current_user)
    residential_ids = list(dict.fromkeys(int(row["residential_id"]) for row in residentials))
    with db.no_autoflush:
        existing_ids = set(db.scalars(select(Proposal.proposal_id).where(
            Proposal.proposal_id.in_(selected_ids)
        )).all())
        if existing_ids != set(selected_ids):
            raise HTTPException(422, "Una de las propuestas seleccionadas no existe.")

        # Preserve the same Participant -> Person -> proposal snapshot join as
        # No Duplicado. Carry the session's location to group in one read.
        monthly_stmt = (
            select(Participant, ProposalParticipant, ActivitySession.residential_id)
            .select_from(Participant)
            .join(Attendance, Attendance.participant_id == Participant.participant_id)
            .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
            .outerjoin(Person, Person.legacy_participant_id == Participant.participant_id)
            .outerjoin(ProposalParticipant, and_(
                ProposalParticipant.person_id == Person.person_id,
                ProposalParticipant.proposal_id == ActivitySession.proposal_id,
            ))
            .where(
                Attendance.attended == True,  # noqa: E712
                ActivitySession.proposal_id.in_(selected_ids),
                ActivitySession.session_date >= month_start,
                ActivitySession.session_date <= report_end,
            ).distinct()
        )
        global_pairs = {}
        residential_pairs = {identifier: {} for identifier in residential_ids}
        for participant, snapshot, residential_id in db.execute(monthly_stmt).all():
            # The SQL DISTINCT also includes location. Remove only that extra
            # dimension globally before applying the original snapshot helper.
            pair_key = (participant.participant_id,
                        snapshot.proposal_participant_id if snapshot is not None else None)
            pair = (participant, snapshot)
            global_pairs[pair_key] = pair
            if residential_id in residential_pairs:
                residential_pairs[residential_id][pair_key] = pair
        population_rows = {
            identifier: _population_counts(list(pairs.values()), selected_ids)
            for identifier, pairs in residential_pairs.items()
        }
        population_rows["global"] = _population_counts(list(global_pairs.values()), selected_ids)

        starts_stmt = (
            select(ActivitySession.proposal_id, func.min(ActivitySession.session_date))
            .join(Attendance, Attendance.session_id == ActivitySession.session_id)
            .where(
                ActivitySession.proposal_id.in_(selected_ids),
                ActivitySession.session_date <= report_end,
                Attendance.attended == True,  # noqa: E712
            ).group_by(ActivitySession.proposal_id)
        )
        proposal_starts = {identifier: None for identifier in selected_ids}
        proposal_starts.update(dict(db.execute(starts_stmt).all()))
        first_dates = [value for value in proposal_starts.values() if value is not None]
        cumulative_start = min(first_dates) if first_dates else None

        if cumulative_start is None or cumulative_start >= month_start:
            # The first month has exactly the same eligible participants. This
            # also avoids executing one cumulative context per empty location.
            by_residential = {identifier: sum(row["total"] for row in population_rows[identifier].values())
                              for identifier in residential_ids}
            total_all = sum(row["total"] for row in population_rows["global"].values())
        else:
            common = dict(db=db, current_user=report_user, proposal_id=selected_ids,
                          month=month, year=year, period_type="custom",
                          start_date=cumulative_start, end_date=report_end)
            # No selected proposal has a confirmed attendance before its own
            # first date; the earliest selected start therefore preserves every
            # proposal's full history without admitting another proposal.
            total_all = reports._build_no_duplicado_context(**common, employee_id=0)["total_all"]
            by_residential = {
                identifier: reports._build_no_duplicado_context(**common, employee_id=-identifier)["total_all"]
                for identifier in residential_ids
            }

    return {
        "target_population_rows": population_rows,
        "target_cumulative": {
            "period_label": (f"{cumulative_start:%d/%m/%Y} al {report_end:%d/%m/%Y}" if cumulative_start
                             else f"Sin asistencias confirmadas hasta {report_end:%d/%m/%Y}"),
            "start_date": cumulative_start,
            "end_date": report_end,
            "proposal_starts": proposal_starts,
            "by_residential": by_residential,
            "total_all": total_all,
        },
    }
