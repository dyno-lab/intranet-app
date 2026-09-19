"""Distinct residential coverage for the complete report's recruitment rows.

Recruitment is a residential reached through confirmed attendance in a program
and population. The cumulative value is a union of residential IDs, not a sum
or maximum of monthly totals. Existing activity/participant metrics are untouched.
"""
from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date
import re
import unicodedata

from sqlalchemy import func, select

from app.core.auth import require_admin
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.residential import Residential
from app.services.report_programs import resolve_effective_program_population_blocks


def recruitment_code(program_code, population_label, rows=()):
    """Printed row identifiers from the template; never create activity codes."""
    code = re.sub(r"[^A-Z0-9]", "", str(program_code).upper())
    label = "".join(character for character in unicodedata.normalize("NFKD", str(population_label))
                    if not unicodedata.combining(character)).casefold().strip()
    label = re.sub(r"^" + re.escape(code.casefold()) + r"\s+", "", label)
    reference = {
        ("1A", "ninos"): "1.a.1", ("1A", "jovenes"): "1.a.8",
        ("2B", "jovenes y adultos"): "2.b.1",
        ("3C", "ninos"): "3.c.1", ("3C", "jovenes"): "3.c.9",
        ("3C", "adultos"): "3.c.19", ("4D", "adulto mayor"): "4.d.1",
    }
    default = reference.get((code, label), "")
    known_codes = {value for (program, _), value in reference.items() if program == code}
    configured = [str(row.get("activity_code", "")).strip().casefold() for row in rows
                  if str(row.get("activity_code", "")).strip().casefold() in known_codes]
    # The configured activity keeps its identity if its population is renamed.
    # Labels only supply a printed identifier when the recruitment row is absent.
    return default if default in configured else configured[0] if configured else default


def _empty():
    return {"monthly": set(), "cumulative": set()}


def _counts(bucket):
    return {
        "monthly_count": len(bucket["monthly"]),
        "cumulative_count": len(bucket["cumulative"]),
        "monthly_residential_ids": sorted(bucket["monthly"]),
        "cumulative_residential_ids": sorted(bucket["cumulative"]),
    }


def build_recruitment_data(db, current_user, proposal_ids, month, year):
    """Read coverage for filters already validated by the full report builder.

    Keep activity assignments attached to their proposal before consolidating
    matching program/population headings. A globally shared activity ID may be
    assigned to a different population in another proposal. Location comes from
    the session, including historical inactive locations; an unassigned location
    is not a residential. Neither participant ages nor their home addresses
    define this measure.
    """
    require_admin(current_user)
    month_start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    with db.no_autoflush:
        structures = {identifier: resolve_effective_program_population_blocks(db, identifier)
                      for identifier in proposal_ids}
        assignments = defaultdict(set)
        by_proposal = {}
        combined = {}
        for identifier, blocks in structures.items():
            groups = {}
            for block in blocks:
                for population in block["population_blocks"]:
                    key = (block["program"].code, population["population_label"])
                    groups.setdefault(key, _empty())
                    combined.setdefault(key, _empty())
                    for row in population["rows"]:
                        assignments[(identifier, row["activity_code_id"])].add(key)
            by_proposal[identifier] = {"groups": groups, "program_blocks": blocks,
                                       "start_date": None, "end_date": end}

        # MIN/MAX summarizes all history per location/activity without expanding
        # session or participant ID lists into SQL Server parameters. Because
        # dates end at report_end, MAX >= month_start means attended this month.
        confirmed = select(Attendance.attendance_id).where(
            Attendance.session_id == ActivitySession.session_id,
            Attendance.attended == True,  # noqa: E712
        ).exists()
        stmt = (
            select(ActivitySession.proposal_id, ActivitySession.activity_code_id,
                   ActivitySession.residential_id, Residential.name,
                   func.min(ActivitySession.session_date), func.max(ActivitySession.session_date))
            .outerjoin(Residential, Residential.residential_id == ActivitySession.residential_id)
            .where(ActivitySession.proposal_id.in_(proposal_ids),
                   ActivitySession.session_date <= end, confirmed)
            .group_by(ActivitySession.proposal_id, ActivitySession.activity_code_id,
                      ActivitySession.residential_id, Residential.name)
        )
        global_coverage = _empty()
        names = {}
        for identifier, activity_id, residential_id, name, first, last in db.execute(stmt).all():
            proposal = by_proposal[identifier]
            proposal["start_date"] = min(proposal["start_date"], first) if proposal["start_date"] else first
            if residential_id is None:
                continue
            names[residential_id] = name or str(residential_id)
            monthly = last >= month_start
            global_coverage["cumulative"].add(residential_id)
            if monthly:
                global_coverage["monthly"].add(residential_id)
            for key in assignments[(identifier, activity_id)]:
                for bucket in (proposal["groups"][key], combined[key]):
                    bucket["cumulative"].add(residential_id)
                    if monthly:
                        bucket["monthly"].add(residential_id)

    return {
        **_counts(global_coverage), "residential_names": names,
        "groups": {key: _counts(value) for key, value in combined.items()},
        "by_proposal": {
            identifier: {**proposal, "groups": {key: _counts(value) for key, value in proposal["groups"].items()}}
            for identifier, proposal in by_proposal.items()
        },
    }
