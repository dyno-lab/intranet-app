"""Real SQL Server migration and concurrency evidence in a disposable test DB."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier, Event
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from tests import test_monthly_attendance as monthly
from tests import test_participant_transfers as transfers
from app.models.base import Base
from app.models.monthly_attendance import MonthlyAttendanceSettings, AttendanceMonth, AttendanceMonthResidential, AttendanceMonthEvent
from app.models.notification import FaroAnnouncement, FaroAnnouncementRole, FaroAnnouncementResidential, FaroAnnouncementRead
from app.db.monthly_attendance_schema import MONTHLY_ATTENDANCE_SQL
from app.services.monthly_attendance import build_month, confirm_month, change_months
from app.models.activity_session import ActivitySession
from fastapi import HTTPException

TRACKING = (MonthlyAttendanceSettings, AttendanceMonth, AttendanceMonthResidential, AttendanceMonthEvent)
NOTICE = (FaroAnnouncement, FaroAnnouncementRole, FaroAnnouncementResidential, FaroAnnouncementRead)


@unittest.skipUnless(os.environ.get("FARO_MIGRATION_TEST_DSN"), "SQL Server test DSN not set")
class MonthlyAttendanceSQLServerTests(monthly.MonthlyAttendanceTests):
    class fixture_class(transfers.ParticipantTransferTests):
        models = transfers.ParticipantTransferTests.models + NOTICE + TRACKING

        def make_engine(self):
            engine = create_engine(URL.create("mssql+pyodbc", query={"odbc_connect": self.dsn}))
            @event.listens_for(engine, "connect")
            def select_database(connection, _):
                connection.cursor().execute(f"USE [{self.database}]")
            Base.metadata.drop_all(engine, tables=[m.__table__ for m in self.models])
            return engine

    @classmethod
    def setUpClass(cls):
        import pyodbc
        cls.database = "Faro_Monthly_Test_" + uuid4().hex
        cls.admin = pyodbc.connect(os.environ["FARO_MIGRATION_TEST_DSN"], autocommit=True, timeout=10)
        cls.admin.execute(f"CREATE DATABASE [{cls.database}]")
        cls.fixture_class.dsn, cls.fixture_class.database = os.environ["FARO_MIGRATION_TEST_DSN"], cls.database

    @classmethod
    def tearDownClass(cls):
        try:
            cls.admin.execute("USE [master]")
            cls.admin.execute(f"ALTER DATABASE [{cls.database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            cls.admin.execute(f"DROP DATABASE [{cls.database}]")
        finally:
            cls.admin.close()

    def test_migration_creates_tables_and_rerun_preserves_confirmations(self):
        self.db.commit()
        Base.metadata.drop_all(self.fixture.engine, tables=[m.__table__ for m in TRACKING])
        with self.fixture.engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE dbo.faro_announcements DROP COLUMN action_url")
            conn.exec_driver_sql(MONTHLY_ATTENDANCE_SQL)
            conn.exec_driver_sql(MONTHLY_ATTENDANCE_SQL)
        self.confirm()
        before = self.view()['rows'][0]['record'].confirmed_at
        self.db.commit()
        with self.fixture.engine.begin() as conn:
            conn.exec_driver_sql(MONTHLY_ATTENDANCE_SQL)
            self.assertEqual(conn.exec_driver_sql("SELECT COUNT(*) FROM dbo.attendance").scalar(), 1)
            self.assertEqual(conn.exec_driver_sql("SELECT COUNT(*) FROM dbo.attendance_month_events WHERE kind='confirmed'").scalar(), 1)
        self.db.expire_all()
        self.assertEqual(self.view()['rows'][0]['record'].confirmed_at, before)

    def test_nocount_confirmation_and_invalidation(self):
        self.db.execute(text("SET NOCOUNT ON"))
        self.confirm()
        change_months(self.db, self.fixture.actor,
            [(self.fixture.proposal.proposal_id, self.fixture.a.residential_id, date(2026, 9, 10))],
            reason="Corrección", today=self.today)
        self.db.commit()
        self.assertEqual(self.view()['rows'][0]['status'], 'review')

    def test_simultaneous_confirmations_produce_one_all_completed_notice(self):
        f = self.fixture
        users = [SimpleNamespace(user_id=f.actor.user_id, username='Operador', role='user',
                  _active_residential_id=rid) for rid in (f.a.residential_id, f.b.residential_id)]
        pid = f.proposal.proposal_id
        tokens = [build_month(self.db, user, pid, 2026, 9)['rows'][0]['fingerprint'] for user in users]
        self.db.commit()
        barrier = Barrier(2)
        def worker(index):
            with Session(f.engine, autoflush=False) as db:
                barrier.wait(timeout=10)
                confirm_month(db, users[index], proposal_id=pid, year=2026, month=9,
                    fingerprint=tokens[index], declared=True, no_activity=index == 1,
                    note='Sin actividad.' if index else '', today=self.today)
                db.commit()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(worker, range(2)))
        self.db.expire_all()
        self.assertTrue(self.view(f.actor)['all_done'])
        events = self.db.scalars(select(AttendanceMonthEvent).where(AttendanceMonthEvent.kind == 'all_confirmed')).all()
        self.assertEqual(len(events), 1)

    def test_first_confirmation_waits_for_in_flight_activity_creation(self):
        f = self.fixture
        pid, rid, employee, code = f.proposal.proposal_id, f.a.residential_id, f.employee.employee_id, f.code.activity_code_id
        actor = SimpleNamespace(user_id=f.actor.user_id, username='Operador', role='user', _active_residential_id=rid)
        fingerprint = build_month(self.db, actor, pid, 2026, 10)['rows'][0]['fingerprint']
        self.db.commit()
        locked, release, started = Event(), Event(), Event()
        def writer():
            with Session(f.engine, autoflush=False) as db:
                change_months(db, actor, [(pid, rid, date(2026, 10, 15))], reason='Nueva actividad', today=self.today)
                locked.set()
                if not release.wait(10):
                    raise AssertionError('Confirmation did not start')
                db.add(ActivitySession(proposal_id=pid, residential_id=rid, session_date=date(2026, 10, 15),
                    employee_id=employee, activity_code_id=code))
                db.commit()
        def confirm():
            with Session(f.engine, autoflush=False) as db:
                started.set()
                try:
                    confirm_month(db, actor, proposal_id=pid, year=2026, month=10,
                        fingerprint=fingerprint, declared=True, no_activity=True, note='Sin actividad.', today=self.today)
                    db.commit()
                    return 200
                except HTTPException as error:
                    db.rollback()
                    return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            writing = pool.submit(writer)
            self.assertTrue(locked.wait(10))
            confirming = pool.submit(confirm)
            self.assertTrue(started.wait(10))
            release.set()
            writing.result(timeout=20)
            self.assertEqual(confirming.result(timeout=20), 409)
        self.db.expire_all()
        self.assertEqual(build_month(self.db, actor, pid, 2026, 10)['rows'][0]['status'], 'pending')
