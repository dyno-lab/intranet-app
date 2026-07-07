from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity_code import ActivityCode
from app.models.proposal_activity_code import ProposalActivityCode


def ensure_activity_assigned_to_proposal(
    db: Session,
    activity_code_id: int,
    proposal_id: int | None,
    *,
    is_active: bool = True,
) -> ProposalActivityCode | None:
    if proposal_id is None:
        return None

    assignment = db.execute(
        select(ProposalActivityCode).where(
            ProposalActivityCode.activity_code_id == activity_code_id,
            ProposalActivityCode.proposal_id == proposal_id,
        )
    ).scalar_one_or_none()
    if assignment:
        assignment.is_active = is_active
    else:
        assignment = ProposalActivityCode(
            activity_code_id=activity_code_id,
            proposal_id=proposal_id,
            is_active=is_active,
        )
    db.add(assignment)
    return assignment


def activity_code_assigned_to_proposal(
    db: Session,
    activity_code_id: int,
    proposal_id: int,
    *,
    active_only: bool = True,
) -> bool:
    stmt = select(ProposalActivityCode.proposal_activity_code_id).where(
        ProposalActivityCode.activity_code_id == activity_code_id,
        ProposalActivityCode.proposal_id == proposal_id,
    )
    if active_only:
        stmt = stmt.where(ProposalActivityCode.is_active == True)  # noqa: E712
    return db.execute(stmt).first() is not None


def activity_code_allowed_for_proposal(
    db: Session,
    activity_code: ActivityCode,
    proposal_id: int | None,
) -> bool:
    if proposal_id is None:
        return activity_code.proposal_id is None
    if activity_code.proposal_id is None:
        return True
    if activity_code.proposal_id == proposal_id:
        return True
    return activity_code_assigned_to_proposal(db, activity_code.activity_code_id, proposal_id)


def load_activity_codes_for_proposal(
    db: Session,
    proposal_id: int | None,
    *,
    active_only: bool = True,
) -> list[ActivityCode]:
    stmt = select(ActivityCode)
    if active_only:
        stmt = stmt.where(ActivityCode.is_active == True)  # noqa: E712

    if proposal_id is None:
        stmt = stmt.where(ActivityCode.proposal_id.is_(None))
    else:
        assigned_ids = select(ProposalActivityCode.activity_code_id).where(
            ProposalActivityCode.proposal_id == proposal_id,
            ProposalActivityCode.is_active == True,  # noqa: E712
        )
        stmt = stmt.where(
            (ActivityCode.proposal_id == proposal_id)
            | (ActivityCode.activity_code_id.in_(assigned_ids))
        )

    return list(db.execute(stmt).scalars().all())


def attach_activity_assigned_proposal_ids(db: Session, activity_codes: list[ActivityCode]) -> list[ActivityCode]:
    activity_ids = [activity.activity_code_id for activity in activity_codes]
    assigned_by_activity: dict[int, set[int]] = {activity_id: set() for activity_id in activity_ids}
    if activity_ids:
        rows = db.execute(
            select(ProposalActivityCode.activity_code_id, ProposalActivityCode.proposal_id).where(
                ProposalActivityCode.activity_code_id.in_(activity_ids),
                ProposalActivityCode.is_active == True,  # noqa: E712
            )
        ).all()
        for activity_code_id, proposal_id in rows:
            assigned_by_activity.setdefault(activity_code_id, set()).add(proposal_id)

    for activity in activity_codes:
        if activity.proposal_id:
            assigned_by_activity.setdefault(activity.activity_code_id, set()).add(activity.proposal_id)
        setattr(activity, "assigned_proposal_ids", sorted(assigned_by_activity.get(activity.activity_code_id, set())))

    return activity_codes
