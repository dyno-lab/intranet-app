from __future__ import annotations

import os
import unittest
from datetime import date
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from app.api.routes import participants as participant_routes  # noqa: E402
from app.core.record_identifiers import (  # noqa: E402
    build_expediente_number,
    build_session_control_number,
)
from app.core.residential_scope import (  # noqa: E402
    ACTIVE_RESIDENTIAL_SESSION_KEY,
    require_write_residential_id,
)
from app.db.schema import (  # noqa: E402
    PHASE1_PROPOSALS_SQL,
    RECORD_RESIDENTIAL_COLUMNS_SQL,
    RECORD_RESIDENTIAL_SNAPSHOT_SQL,
    RECORD_RESIDENTIAL_UNIQUENESS_SQL,
)
from app.helpers.report_context import resolve_reporting_scope  # noqa: E402
from app.models.residential import Residential  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.visit_report import VisitReport  # noqa: E402
from app.schemas.participant import ParticipantCreate  # noqa: E402
from app.services.visits import (  # noqa: E402
    calculate_visits_rows_and_summary,
    get_or_create_visit_report,
)


class _Request:
    def __init__(self, residential_id: int):
        self.session = {ACTIVE_RESIDENTIAL_SESSION_KEY: residential_id}


class _Result:
    def __init__(self, *, scalar=None, values=None):
        self.scalar_value = scalar
        self.values = list(values or [])

    def scalar_one_or_none(self):
        return self.scalar_value

    def scalars(self):
        return self

    def all(self):
        return self.values


class _Database:
    def __init__(self, *, objects=None, results=None, flush_error=None):
        self.objects = objects or {}
        self.results = list(results or [])
        self.flush_error = flush_error
        self.statements = []
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    def get(self, model, object_id):
        return self.objects.get((model, object_id))

    def execute(self, statement):
        self.statements.append(statement)
        if not self.results:
            raise AssertionError("Unexpected database query")
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        self.flushes += 1
        if self.flush_error is not None:
            error = self.flush_error
            self.flush_error = None
            raise error

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, value):
        return None


def _residential(residential_id: int, code: str, name: str) -> Residential:
    residential = Residential(
        code=code,
        name=name,
        municipality="Ponce",
        rq_code=f"RQ-{code}",
        is_active=True,
    )
    residential.residential_id = residential_id
    return residential


def _user(user_id: int, *, role: str = "user", residential_id: int | None = None) -> User:
    user = User(
        username=f"user{user_id}@csifpr.org",
        email=f"user{user_id}@csifpr.org",
        password_hash="not-rendered",
        role=role,
        residential_id=residential_id,
        is_active=True,
        local_login_enabled=False,
        session_version=1,
    )
    user.user_id = user_id
    return user


class ResidentialOwnershipTests(unittest.TestCase):
    def test_record_identifiers_use_residential_code(self):
        self.assertEqual(
            build_expediente_number(
                year=2026,
                residential_code=" ac ",
                sequence="0001",
            ),
            "FE-2026-AC-0001",
        )
        self.assertEqual(
            build_session_control_number(
                residential_code=" ac ",
                session_id=45,
                session_date=date(2026, 8, 27),
            ),
            "AC452026",
        )

    def test_api_ignores_client_initials_and_expediente(self):
        residential = _residential(1, "AC", "Aristides Chavier")
        user = _user(11, residential_id=1)
        db = _Database(
            objects={(Residential, 1): residential},
            results=[_Result(), _Result()],
        )
        payload = ParticipantCreate(
            expediente_num="FE-2026-EMAIL-9999",
            exp_year=2026,
            exp_employee_initials="EMAIL",
            exp_seq4="0001",
            nombre="Ana",
            apellido_paterno="Pérez",
        )

        with patch.object(participant_routes.settings, "PHASE2_EXPEDIENTE_ENABLED", True):
            participant = participant_routes.create_participant(
                payload=payload,
                request=_Request(1),
                db=db,
                current_user=user,
            )

        self.assertEqual(participant.residential_id, 1)
        self.assertEqual(participant.created_by_user_id, 11)
        self.assertEqual(participant.exp_employee_initials, "AC")
        self.assertEqual(participant.exp_seq4, "0001")
        self.assertEqual(participant.expediente_num, "FE-2026-AC-0001")
        sequence_statement = db.statements[0]
        self.assertIn("participants.residential_id", str(sequence_statement))
        self.assertIn(1, sequence_statement.compile().params.values())

    def test_privileged_writes_require_explicit_residential(self):
        residential = _residential(1, "AC", "Aristides Chavier")
        db = _Database(objects={(Residential, 1): residential})
        admin = _user(90, role="admin", residential_id=2)

        with self.assertRaises(Exception) as context:
            require_write_residential_id(_Request(2), admin, db)
        self.assertEqual(context.exception.status_code, 403)

        self.assertEqual(
            require_write_residential_id(_Request(2), admin, db, 1),
            1,
        )
        regular = _user(11, residential_id=1)
        self.assertEqual(
            require_write_residential_id(_Request(1), regular, db, 999),
            1,
        )

    def test_reporting_scope_uses_residential_not_user(self):
        aristides = _residential(1, "AC", "Aristides Chavier")
        brisas = _residential(2, "BDM", "Brisas del Mar")
        legacy_user = _user(77, residential_id=1)
        db = _Database(
            objects={
                (Residential, 1): aristides,
                (Residential, 2): brisas,
                (User, 77): legacy_user,
            }
        )

        admin_scope = resolve_reporting_scope(
            _user(90, role="admin"),
            -2,
            db,
        )
        self.assertEqual(admin_scope["residential_id"], 2)
        self.assertEqual(admin_scope["employee_id"], -2)
        self.assertEqual(admin_scope["selected_residential"].name, "Brisas del Mar")

        legacy_scope = resolve_reporting_scope(_user(90, role="admin"), 77, db)
        self.assertEqual(legacy_scope["residential_id"], 1)
        self.assertEqual(legacy_scope["employee_id"], -1)

        regular_user = _user(12, residential_id=2)
        setattr(regular_user, "_active_residential_id", 1)
        user_scope = resolve_reporting_scope(regular_user, 999, db)
        self.assertEqual(user_scope["residential_id"], 1)
        self.assertEqual(user_scope["selected_residential"].code, "AC")

    def test_visits_group_by_residential_snapshot(self):
        session_rows = [
            (1, 50, "Alice Beard", 1.5, 1, "Aristides Chavier"),
            (2, 50, "Alice Beard", 2.0, 1, "Aristides Chavier"),
            (3, 50, "Alice Beard", 1.0, 2, "Brisas del Mar"),
        ]

        rows, summary = calculate_visits_rows_and_summary(
            session_rows,
            {1: 2, 2: 3, 3: 1},
            is_global=True,
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["residential_name"], "Aristides Chavier")
        self.assertEqual(rows[0]["visits"], 2)
        self.assertEqual(rows[0]["attendances"], 5)
        self.assertEqual(rows[0]["hours"], 3.5)
        self.assertEqual(summary, {"visits": 3, "attendances": 6, "hours": 4.5})

    def test_visit_report_separates_owner_from_audit_actor(self):
        db = _Database(results=[_Result()])

        report = get_or_create_visit_report(
            db,
            proposal_id=7,
            report_month=8,
            report_year=2026,
            residential_id=1,
            created_by_user_id=44,
        )

        self.assertIsInstance(report, VisitReport)
        self.assertEqual(report.residential_id, 1)
        self.assertEqual(report.created_by_user_id, 44)
        self.assertEqual(db.added, [report])
        self.assertEqual(db.flushes, 1)
        lookup_sql = str(db.statements[0])
        self.assertIn("visit_reports.residential_id", lookup_sql)
        self.assertNotIn("visit_reports.created_by_user_id =", lookup_sql)

    def test_visit_report_recovers_from_concurrent_insert(self):
        existing = VisitReport(
            proposal_id=7,
            report_month=8,
            report_year=2026,
            residential_id=1,
            created_by_user_id=41,
        )
        existing.report_id = 99
        db = _Database(
            results=[_Result(), _Result(scalar=existing)],
            flush_error=IntegrityError("duplicate", {}, Exception("2601")),
        )

        report = get_or_create_visit_report(
            db,
            proposal_id=7,
            report_month=8,
            report_year=2026,
            residential_id=1,
            created_by_user_id=44,
        )

        self.assertIs(report, existing)
        self.assertEqual(report.created_by_user_id, 41)
        self.assertEqual(db.rollbacks, 1)

    def test_schema_migration_preserves_existing_snapshots(self):
        self.assertIn("ALTER TABLE dbo.participants ADD residential_id", RECORD_RESIDENTIAL_COLUMNS_SQL)
        self.assertIn("WHERE records.residential_id IS NULL", RECORD_RESIDENTIAL_SNAPSHOT_SQL)
        self.assertIn("residentials.code", RECORD_RESIDENTIAL_SNAPSHOT_SQL)
        self.assertIn("UX_participants_residential_seq4", RECORD_RESIDENTIAL_UNIQUENESS_SQL)
        self.assertIn("DROP CONSTRAINT uq_participants_employee_seq4", RECORD_RESIDENTIAL_UNIQUENESS_SQL)
        self.assertNotIn("SET s.control_number = UPPER(LTRIM(RTRIM(u.username)))", PHASE1_PROPOSALS_SQL)
        self.assertIn("THROW 50011", RECORD_RESIDENTIAL_UNIQUENESS_SQL)
        self.assertIn("UX_school_grade_reports_period_residential", RECORD_RESIDENTIAL_UNIQUENESS_SQL)
        self.assertIn("UX_visit_reports_period_residential", RECORD_RESIDENTIAL_UNIQUENESS_SQL)


if __name__ == "__main__":
    unittest.main()
