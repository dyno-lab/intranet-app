from __future__ import annotations

import os
import unittest
from datetime import date
from types import SimpleNamespace

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, event
from sqlalchemy.types import NullType
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.residential import Residential
from app.models.visit_activity_mapping import VisitActivityMapping
from app.models.visit_report import VisitReport
from app.models.visit_report_referral import VisitReportReferral
from app.services.visits import build_visits_report_payload


class VisitsMultiProposalTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        metadata = MetaData()
        self.tables = {}
        for model in (ActivitySession, Attendance, Employee, Residential,
                      VisitActivityMapping, VisitReport, VisitReportReferral):
            self.tables[model] = Table(model.__tablename__, metadata, *[
                Column(c.name, Integer() if isinstance(c.type, NullType) else c.type,
                       primary_key=c.primary_key, nullable=True)
                for c in model.__table__.columns
            ])
        metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        self.parameter_counts = []

        def check_parameters(state):
            compiled = state.statement.compile(
                dialect=mssql.dialect(), compile_kwargs={"render_postcompile": True},
            )
            self.parameter_counts.append(len(compiled.params))
            self.assertLessEqual(len(compiled.params), 2100)

        event.listen(self.db, "do_orm_execute", check_parameters)
        self.insert(Employee, [{"employee_id": 1, "full_name": "Employee"}])
        self.insert(Residential, [{"residential_id": 7, "name": "A"}, {"residential_id": 8, "name": "B"}])
        self.insert(VisitActivityMapping, [
            {"proposal_id": 1, "activity_code_id": 10, "is_active": True},
            {"proposal_id": 2, "activity_code_id": 10, "is_active": True},
            {"proposal_id": 2, "activity_code_id": 20, "is_active": True},
            {"proposal_id": 1, "activity_code_id": 30, "is_active": False},
        ])

    def insert(self, model, rows):
        with self.engine.begin() as connection:
            connection.execute(self.tables[model].insert(), rows)

    def session(self, session_id, proposal_id=1, activity_code_id=10, residential_id=7, day=1):
        return dict(session_id=session_id, proposal_id=proposal_id, activity_code_id=activity_code_id,
                    residential_id=residential_id, employee_id=1, hours=0.5, session_date=date(2026, 9, day))

    def payload(self, proposals, is_global=True, custom=True):
        return build_visits_report_payload(
            self.db, proposal_id=proposals,
            period={"month": 9, "year": 2026, "is_custom": custom},
            selected_user=None if is_global else SimpleNamespace(residential_id=7),
            is_global=is_global, user_residential_map={7: "A", 8: "B"},
            residential_name_resolver=lambda user: "A",
            apply_period_filter=lambda stmt, period: stmt.where(ActivitySession.session_date <= date(2026, 9, 11)),
        )

    def test_consolidation_preserves_mapping_period_residential_and_attendance_semantics(self):
        self.insert(ActivitySession, [
            self.session(1), self.session(2, 2), self.session(3, 2, 20),
            self.session(4, 1, 20),  # Same activity is mapped only in the other proposal.
            self.session(5, 3), self.session(6, 1, 30),
            self.session(7, 2, day=12), self.session(8, 2, residential_id=8),
        ])
        self.insert(Attendance, [
            {"session_id": i, "participant_id": 100, "attended": True} for i in range(1, 9)
        ] + [{"session_id": 1, "participant_id": 101, "attended": False}])
        global_payload = self.payload([1, 2])
        self.assertEqual(global_payload["summary"], {"visits": 4, "attendances": 4, "hours": 2.0})
        self.assertEqual(len(global_payload["rows"]), 2)
        self.assertEqual(self.payload([1, 2], False)["summary"], {"visits": 3, "attendances": 3, "hours": 1.5})
        self.assertEqual(self.payload(1)["summary"], {"visits": 1, "attendances": 1, "hours": 0.5})
        self.assertEqual(self.payload(1), self.payload([1]))

    def test_monthly_referrals_merge_only_selected_proposals_and_residential(self):
        self.insert(VisitReport, [
            {"report_id": i, "proposal_id": p, "residential_id": r, "report_month": 9, "report_year": 2026}
            for i, p, r in [(1, 1, 7), (2, 2, 7), (3, 2, 8), (4, 3, 7)]
        ])
        self.insert(VisitReportReferral, [
            {"report_id": i, "referral_type": "Externo", "agency": str(i), "sort_order": 0}
            for i in range(1, 5)
        ])
        merged = self.payload([1, 2], custom=False)
        self.assertEqual(merged["referral_count"], 3)
        scoped = self.payload([1, 2], False, False)
        self.assertEqual([r["agency"] for r in scoped["referral_rows"]], ["1", "2"])
        self.assertTrue(all("residential_name" not in r for r in scoped["referral_rows"]))
        self.assertIsNone(scoped["visit_report"])
        single = self.payload([1], False, False)
        self.assertEqual(single["visit_report"].report_id, 1)
        self.assertEqual(single["referral_count"], 1)

    def test_large_consolidated_period_keeps_sql_server_parameter_budget(self):
        self.insert(ActivitySession, [self.session(i, 1 if i % 2 else 2) for i in range(1, 4502)])
        self.insert(Attendance, [{"session_id": i, "participant_id": 100, "attended": True} for i in range(1, 4502)])
        self.assertEqual(self.payload([1, 2])["summary"], {"visits": 4501, "attendances": 4501, "hours": 2250.5})
        self.assertLessEqual(max(self.parameter_counts), 1000)
