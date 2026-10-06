"""VCA registry and participation summary, without changing the participant list."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models.participant import Participant
from app.models.person import Person
from app.models.proposal_participant import ProposalParticipant


VCA_AGE_BANDS = ((0, 4, "0 A 4 años"), (5, 8, "5 a 8 años"),
                 (9, 13, "9 A 13 años"), (14, 17, "14 A 17 años"),
                 (18, 61, "18 A 61 años"), (62, None, "62 años en adelante"))


def registered_vca_by_person(db, proposal_ids, residential_id=None):
    """Active proposal records count even without attendance; one person per selection.

    Registration belongs to the proposal snapshot. Legacy ownership only fills a
    missing residential. When selected snapshots differ, prefer the newest
    qualifying proposal, as the existing consolidated participant view does.
    """
    location = func.coalesce(ProposalParticipant.residential_id, Participant.residential_id)
    statement = (
        select(ProposalParticipant.person_id, location)
        .select_from(ProposalParticipant)
        .outerjoin(Person, Person.person_id == ProposalParticipant.person_id)
        .outerjoin(Participant, Participant.participant_id == Person.legacy_participant_id)
        .where(ProposalParticipant.proposal_id.in_(proposal_ids),
               ProposalParticipant.is_active == True,  # noqa: E712
               func.upper(func.ltrim(func.rtrim(ProposalParticipant.vca))) == "SI")
        .order_by(ProposalParticipant.proposal_id.desc(), ProposalParticipant.proposal_participant_id.desc())
    )
    if residential_id is not None:
        statement = statement.where(location == residential_id)
    people = {}
    for person_id, registered_residential_id in db.execute(statement).all():
        people.setdefault(person_id, registered_residential_id)
    return people


def build_vca_summary(*, registered_people, rows, columns, participant_details,
                      residential_names, residential_ids=()):
    column_ids = [column.vca_column_id for column in columns]

    def empty_row(residential_id, name):
        return {"residential_id": residential_id, "residential_name": name,
                "registered": 0, "served": 0, "f": 0, "m": 0,
                "ages": [{"f": 0, "m": 0} for _ in VCA_AGE_BANDS],
                "services": {column_id: 0 for column_id in column_ids},
                "unknown_age": 0, "unknown_gender": 0}

    locations = {}

    def location_row(residential_id):
        if residential_id not in locations:
            locations[residential_id] = empty_row(
                residential_id, residential_names.get(residential_id) or "Sin residencial")
        return locations[residential_id]

    for residential_id in residential_ids:
        location_row(residential_id)
    for residential_id in registered_people.values():
        location_row(residential_id)["registered"] += 1
    for row in rows:
        detail = participant_details[row["participant_id"]]
        target = location_row(detail["residential_id"])
        target["served"] += 1
        gender = (row["genero"] or "").strip().lower()
        age = detail["age"]
        age_index = next((i for i, (start, end, _) in enumerate(VCA_AGE_BANDS)
                          if age is not None and age >= start and (end is None or age <= end)), None)
        if gender in ("f", "m"):
            target[gender] += 1
            if age_index is not None:
                target["ages"][age_index][gender] += 1
        else:
            target["unknown_gender"] += 1
        if age_index is None:
            target["unknown_age"] += 1
        for column_id in column_ids:
            target["services"][column_id] += row["column_values"].get(column_id) or 0

    summary_rows = sorted(locations.values(), key=lambda row: (
        row["residential_name"] == "Sin residencial", row["residential_name"].strip().casefold()))
    total = empty_row(None, "Total")
    for row in summary_rows:
        for key in ("registered", "served", "f", "m", "unknown_age", "unknown_gender"):
            total[key] += row[key]
        for index in range(len(VCA_AGE_BANDS)):
            for gender in ("f", "m"):
                total["ages"][index][gender] += row["ages"][index][gender]
        for column_id in column_ids:
            total["services"][column_id] += row["services"][column_id]
    return {"rows": summary_rows, "total": total, "age_bands": VCA_AGE_BANDS}
