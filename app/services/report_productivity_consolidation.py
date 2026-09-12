"""Consolidate read-only productivity inputs without changing goal arithmetic."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException


def consolidate_productivity_inputs(goal_rows, count_rows, period_count_rows):
    goals_by_activity = {}
    for row in goal_rows:
        goals_by_activity.setdefault(row[0].activity_code_id, []).append(row)

    consolidated_goals = []
    canonical_proposals = {}
    for activity_id, rows in goals_by_activity.items():
        rows = sorted(rows, key=lambda row: row[0].proposal_id)
        goal, _, _, activity_code, activity_description = rows[0]
        signature = (goal.goal_type, goal.goal_value, goal.period_goal_value)
        if any((row[0].goal_type, row[0].goal_value, row[0].period_goal_value) != signature for row in rows):
            raise HTTPException(
                status_code=422,
                detail=(f"La actividad {activity_code} tiene metas diferentes entre las propuestas "
                        "seleccionadas. No se puede consolidar productividad con metas diferentes."),
            )
        canonical_proposals[activity_id] = goal.proposal_id
        consolidated_goals.append((
            SimpleNamespace(
                proposal_id=goal.proposal_id, activity_code_id=activity_id,
                goal_type=goal.goal_type, goal_value=goal.goal_value,
                period_goal_value=goal.period_goal_value,
            ),
            " / ".join(dict.fromkeys(row[1] for row in rows if row[1])),
            " / ".join(dict.fromkeys(row[2] for row in rows if row[2])),
            activity_code, activity_description,
        ))

    # Activities without configured goals still retain their counts. Use the
    # same representative proposal in both count collections for join keys.
    unconfigured_proposals = {}
    for row in [*count_rows, *period_count_rows]:
        if row.activity_code_id not in canonical_proposals:
            unconfigured_proposals.setdefault(row.activity_code_id, []).append(row.proposal_id)
    canonical_proposals.update({activity_id: min(ids) for activity_id, ids in unconfigured_proposals.items()})

    counts = {}
    for row in count_rows:
        key = (row.activity_code_id, row.residential_id)
        if key not in counts:
            counts[key] = SimpleNamespace(
                proposal_id=canonical_proposals[row.activity_code_id],
                activity_code_id=row.activity_code_id, residential_id=row.residential_id,
                residential_name=row.residential_name, executed_count=0,
            )
        counts[key].executed_count += int(row.executed_count or 0)

    period_counts = {}
    for row in period_count_rows:
        if row.activity_code_id not in period_counts:
            period_counts[row.activity_code_id] = SimpleNamespace(
                proposal_id=canonical_proposals[row.activity_code_id],
                activity_code_id=row.activity_code_id, executed_count=0,
            )
        period_counts[row.activity_code_id].executed_count += int(row.executed_count or 0)

    return consolidated_goals, list(counts.values()), list(period_counts.values())
