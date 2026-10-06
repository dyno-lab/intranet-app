"""Frequencies approved from agosto 2026.docx for the complete-report checklist.

Targets are global plan values, not values per residential. Historical outcomes
from the Word are deliberately excluded. The caller selects the applicable plan;
this module only formats current counts against its monthly and full-period goals.
"""
from __future__ import annotations

from app.services.hoja_cotejo_admin_service import _percent, _format_cumulative_ratio


# Monthly target, full proposal-period target. Recruitment has one distinct-
# residential coverage goal for the period; it does not multiply by three.
FIXED_TARGETS = {
    "1.a.1": (18, 18), "1.a.4": (180, 540), "1.a.5": (12, 36),
    "1.a.7": (18, 54), "1.a.8": (6, 6), "1.a.11": (60, 180),
    "1.a.12": (4, 12), "1.a.14": (18, 54), "2.b.1": (18, 18),
    "3.c.1": (18, 18), "3.c.4": (12, 36), "3.c.5": (12, 36),
    "3.c.7": (12, 36), "3.c.9": (18, 18), "3.c.12": (12, 36),
    "3.c.13": (12, 36), "3.c.14": (6, 18), "3.c.19": (18, 18),
    "3.c.23": (6, 18), "3.c.24": (12, 36), "3.c.25": (12, 36),
    "4.d.1": (18, 18), "4.d.5": (6, 18), "4.d.6": (12, 36),
    "4.d.12": (1, 1),
}
AS_NEEDED = frozenset("""
    1.a.2 1.a.3 1.b.3 1.c.3 1.d.3 1.a.6 1.a.9 1.a.10 1.b.10 1.c.10
    1.d.10 1.a.13 1.a.15
    2.b.2 2.a.3 2.b.3 2.c.3 2.d.3 2.e.3 2.f.3 2.a.4 2.b.4 2.c.4 2.b.5
    2.b.6 2.a.7 2.b.7 2.b.8 2.b.9
    3.c.2 3.a.3 3.b.3 3.c.3 3.d.3 3.a.6 3.b.6 3.a.7 3.b.7 3.d.7
    3.a.8 3.b.8 3.c.8 3.c.10 3.a.11 3.b.11 3.c.11 3.d.11 3.c.15
    3.a.16 3.b.16 3.a.17 3.b.17 3.c.17 3.d.17 3.a.18 3.b.18 3.c.18
    3.c.20 3.a.21 3.b.21 3.c.21 3.d.21 3.e.21 3.f.21 3.g.21 3.a.22
    3.b.22 3.c.22 3.d.22 3.e.22 3.f.22 3.c.26 3.c.27 3.a.28 3.b.28
    3.a.29 3.b.29 3.c.29 3.d.29 3.a.30 3.b.30 3.c.30 3.a.31 3.b.31 3.c.32
    4.d.2 4.a.3 4.b.3 4.c.3 4.d.3 4.e.3 4.f.3 4.g.3 4.a.4 4.b.4
    4.c.4 4.d.4 4.e.4 4.f.4 4.d.7 4.a.8 4.b.8 4.a.9 4.b.9 4.c.9
    4.d.9 4.a.10 4.b.10 4.c.10 4.a.11 4.b.11
""".split())


def reference_plan_multiplier(context):
    proposal = context.get("proposal")
    if proposal is None or (proposal.code.strip(), proposal.name.strip()) not in {
        ("005", "2025-000094-B"), ("006", "2025-000094-C"),
    }:
        return 0
    return len(set(context.get("selected_proposal_ids") or [context["selected_proposal_id"]]))


def has_reference_frequency(code):
    code = code.strip().casefold()
    return code in FIXED_TARGETS or code in AS_NEEDED


def apply_frequency(row, multiplier):
    """Return a display row; never mutate source metrics or configured DB goals."""
    code = row["activity_code"].strip().casefold()
    as_needed = code in AS_NEEDED
    if code not in FIXED_TARGETS and not as_needed:
        return row
    monthly_target, period_target = FIXED_TARGETS.get(code, (1, 1))
    if not as_needed:
        monthly_target *= multiplier
        period_target *= multiplier
    monthly = row["activities_count"]
    cumulative = row["cumulative_activities"]
    if as_needed:
        label = "Según Necesidad"
    elif code == "4.d.12":
        label = "1 Actividad" if multiplier == 1 else f"{multiplier} Actividades"
    else:
        label = f"{monthly_target} Mensual"
    return {
        **row,
        "goal_summary": label,
        "goal_target": monthly_target,
        "monthly_percent": _percent(monthly, monthly_target),
        "met": monthly >= monthly_target,
        "cumulative_target": period_target,
        "cumulative_ratio": str(cumulative) if as_needed else _format_cumulative_ratio(cumulative, period_target),
        "percent": _percent(cumulative, period_target),
        "cumulative_met": cumulative >= period_target,
    }
