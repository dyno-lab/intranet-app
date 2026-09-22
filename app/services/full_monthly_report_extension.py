"""Consolidate the 005/006 extension within the complete report only.

Monthly counts keep the existing multi-proposal report's activity IDs and
participant identity. Confirmed cumulative sessions span both proposals;
goals and elapsed months belong to the shared plan and are applied once.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import distinct, func, select

from app.helpers.sql_batches import query_rows_by_id_batches
from app.models.activity_productivity_goal import ActivityProductivityGoal
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.services import hoja_cotejo_admin_service as admin
from app.services.full_monthly_report_targets import selected_extension


def consolidate_extension_checklists(db, user, proposals, contexts, recruitment, monthly, month, year):
    extension = selected_extension(proposals)
    if not extension:
        return contexts
    ids = [proposal.proposal_id for proposal in extension]
    sources = [context for context in contexts if context["selected_proposal_id"] in ids]
    # An unrelated selected proposal must never enter the extension checklist.
    if len(proposals) != len(extension):
        from app.api.routes.reports import _build_hoja_cotejo_context
        monthly = _build_hoja_cotejo_context(db, user, ids, month, year, 0)
    structure = monthly["program_blocks"]
    activity_ids = {row["activity_code_id"] for block in structure
                    for population in block["population_blocks"] for row in population["rows"]}
    goals = {}
    goal_rows = query_rows_by_id_batches(
        db, select(ActivityProductivityGoal).where(
            ActivityProductivityGoal.proposal_id.in_(ids),
            ActivityProductivityGoal.is_active == True,  # noqa: E712
        ), ActivityProductivityGoal.activity_code_id, sorted(activity_ids), scalars=True,
    )
    def signature(item):
        return item.goal_type, item.goal_value, item.period_goal_value
    for goal in goal_rows:
        previous = goals.get(goal.activity_code_id)
        if previous is not None and signature(previous) != signature(goal):
            code = next(row["activity_code"] for block in structure for population in block["population_blocks"]
                        for row in population["rows"] if row["activity_code_id"] == goal.activity_code_id)
            raise HTTPException(422, f"La actividad {code} tiene metas diferentes en 005 y 006. Revisa su configuración antes de consolidar la extensión.")
        goals[goal.activity_code_id] = goal

    first_dates = [recruitment["by_proposal"][identifier]["start_date"] for identifier in ids
                   if recruitment["by_proposal"][identifier]["start_date"]]
    first = min(first_dates) if first_dates else None
    end = admin._report_end_date(period_type="monthly", month=month, year=year, end_date=None)
    elapsed = admin._inclusive_months(first, end)
    # Query the shared activity scope once, including earlier attendance even
    # if an activity is now configured in only one part of the extension.
    cumulative_stmt = (
        select(ActivitySession.activity_code_id, func.count(distinct(ActivitySession.session_id)))
        .join(Attendance, Attendance.session_id == ActivitySession.session_id)
        .where(ActivitySession.proposal_id.in_(ids), ActivitySession.session_date <= end,
               Attendance.attended == True)  # noqa: E712
        .group_by(ActivitySession.activity_code_id)
    )
    cumulative = dict(query_rows_by_id_batches(db, cumulative_stmt, ActivitySession.activity_code_id, sorted(activity_ids)))
    residential_count = sources[0]["active_residential_count"]
    totals = {"activities_count": 0, "duplicados": 0, "met": 0, "not_met": 0, "rows": 0}
    programs = []
    for block in structure:
        seen, rows = set(), []
        for population in block["population_blocks"]:
            for source_row in population["rows"]:
                activity_id = source_row["activity_code_id"]
                if activity_id in seen:
                    continue
                seen.add(activity_id)
                count, duplicated = source_row["activities_count"], source_row["duplicados"]
                goal = goals.get(activity_id)
                target = admin._target_for_goal(goal, residential_count)
                cumulative_target = admin._cumulative_target_for_goal(goal, residential_count, elapsed)
                executed = cumulative.get(activity_id, 0)
                met = target is not None and count >= target
                rows.append({
                    **source_row,
                    "achievement_text": admin._format_achievement_text(count, duplicated),
                    "goal_summary": admin._goal_summary(goal), "goal_target": target,
                    "monthly_percent": admin._percent(count, target), "met": met,
                    "cumulative_activities": executed, "cumulative_target": cumulative_target,
                    "cumulative_ratio": admin._format_cumulative_ratio(executed, cumulative_target),
                    "percent": admin._percent(executed, cumulative_target),
                    "cumulative_met": cumulative_target is not None and executed >= cumulative_target,
                })
                totals["activities_count"] += count
                totals["duplicados"] += duplicated
                totals["rows"] += 1
                if target is not None:
                    totals["met" if met else "not_met"] += 1
        programs.append({
            "program": block["program"], "program_code": block["program"].code,
            "program_display_name": block["program_display_name"], "rows": rows,
            "program_activities_count": sum(row["activities_count"] for row in rows),
            "program_duplicados": sum(row["duplicados"] for row in rows),
        })

    groups = {}
    for identifier in ids:
        for key, values in recruitment["by_proposal"][identifier]["groups"].items():
            group = groups.setdefault(key, {"monthly_residential_ids": set(), "cumulative_residential_ids": set()})
            for field in group:
                group[field].update(values[field])
    group_counts = {
        key: {"monthly_count": len(values["monthly_residential_ids"]),
              "cumulative_count": len(values["cumulative_residential_ids"]),
              **{field: sorted(ids) for field, ids in values.items()}}
        for key, values in groups.items()
    }
    combined = {
        **sources[0], "selected_proposal_ids": ids,
        "proposal_label": " / ".join(f"{p.code} - {p.name}" for p in extension) + " (extensión)",
        "program_blocks": programs, "totals": totals,
        "first_attendance_date": first, "elapsed_months": elapsed,
        "recruitment": {"program_blocks": structure, "groups": group_counts},
    }
    result, added = [], False
    for context in contexts:
        if context["selected_proposal_id"] not in ids:
            result.append(context)
        elif not added:
            result.append(combined)
            added = True
    return result
