"""Monthly handoff is explicit, scoped and invalidated by later attendance changes."""
import unittest
from datetime import date
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select, event
from sqlalchemy.orm import Session

from tests import test_participant_transfers as fixtures
from app.models.base import Base
from app.models.notification import FaroAnnouncement, FaroAnnouncementRole, FaroAnnouncementResidential, FaroAnnouncementRead
from app.models.monthly_attendance import MonthlyAttendanceSettings, AttendanceMonth, AttendanceMonthResidential, AttendanceMonthEvent
from app.services.monthly_attendance import build_month, confirm_month, change_months, default_due_date, configure_month, remind_month
from app.services.monthly_attendance_notifications import monthly_notification
from app.services.notifications import announcement_notifications


class MonthlyAttendanceTests(unittest.TestCase):
    fixture_class = fixtures.ParticipantTransferTests

    def setUp(self):
        self.fixture = self.fixture_class()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.db = self.fixture.db
        Base.metadata.create_all(self.fixture.engine, tables=[m.__table__ for m in (
            FaroAnnouncement, FaroAnnouncementRole, FaroAnnouncementResidential, FaroAnnouncementRead,
            MonthlyAttendanceSettings, AttendanceMonth, AttendanceMonthResidential, AttendanceMonthEvent)])
        self.db.add(MonthlyAttendanceSettings(settings_id=1, first_month=date(2026, 9, 1)))
        self.db.commit()
        self.user = SimpleNamespace(user_id=self.fixture.actor.user_id, username='Usuario MH', role='user',
                                    _active_residential_id=self.fixture.a.residential_id)
        self.today = date(2026, 11, 9)

    def view(self, user=None):
        return build_month(self.db, user or self.user, self.fixture.proposal.proposal_id, 2026, 9, today=self.today)

    def confirm(self, **overrides):
        values = dict(proposal_id=self.fixture.proposal.proposal_id, year=2026, month=9,
                      fingerprint=self.view()['rows'][0]['fingerprint'], declared=True,
                      no_activity=False, note='', today=self.today)
        values.update(overrides)
        result = confirm_month(self.db, self.user, **values)
        self.db.commit()
        return result

    def test_confirm_records_responsible_and_source_only(self):
        before = self.view()
        self.assertEqual(before['rows'][0]['status'], 'pending')
        self.confirm()
        row = self.view()['rows'][0]
        self.assertEqual(row['status'], 'done')
        self.assertEqual(row['record'].confirmed_by_name, 'Usuario MH')
        global_view = self.view(self.fixture.actor)
        self.assertEqual((global_view['completed'], global_view['total']), (1, 2))
        self.assertFalse(global_view['all_done'])
        self.assertEqual(self.fixture.attendance.session_id, self.fixture.session.session_id)

    def test_zero_activity_needs_explicit_reason_and_tenth_is_default(self):
        self.assertEqual(default_due_date(2026, 12), date(2027, 1, 10))
        self.user._active_residential_id = self.fixture.b.residential_id
        for values in ({}, {'no_activity': True}, {'no_activity': True, 'note': '  '}):
            with self.assertRaises(HTTPException):
                self.confirm(**values)
            self.db.rollback()
        self.confirm(no_activity=True, note='Centro cerrado durante el mes por mantenimiento.')
        self.assertEqual(self.view()['rows'][0]['status'], 'done')

    def test_change_reopens_confirmation_and_rollback_preserves_it(self):
        self.confirm()
        key = (self.fixture.proposal.proposal_id, self.fixture.a.residential_id, date(2026, 9, 10))
        change_months(self.db, self.fixture.actor, [key], reason='Asistencia corregida', today=self.today)
        self.db.rollback()
        self.assertEqual(self.view()['rows'][0]['status'], 'done')
        change_months(self.db, self.fixture.actor, [key], reason='Asistencia corregida', today=self.today)
        self.db.commit()
        self.assertEqual(self.view()['rows'][0]['status'], 'review')
        self.confirm()
        self.assertEqual(self.view()['rows'][0]['status'], 'done')

    def test_declaration_and_readonly_role_are_enforced(self):
        with self.assertRaises(HTTPException):
            self.confirm(declared=False)
        self.db.rollback()
        self.user.role = 'viewer'
        with self.assertRaises(HTTPException) as error:
            self.confirm()
        self.assertEqual(error.exception.status_code, 403)

    def test_stale_page_and_same_count_changes_require_review(self):
        fingerprint = self.view()['rows'][0]['fingerprint']
        self.fixture.session.hours = 2
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            self.confirm(fingerprint=fingerprint)
        self.assertEqual(error.exception.status_code, 409)
        self.db.rollback()
        self.confirm()
        # Also detect modifications made outside the application's mutation hooks.
        self.fixture.attendance.attended = False
        self.db.commit()
        self.assertEqual(self.view()['rows'][0]['status'], 'review')

    def test_all_complete_notifications_are_retired_after_change_and_retry_is_idempotent(self):
        self.confirm()
        count = len(self.db.scalars(select(AttendanceMonthEvent)).all())
        self.confirm()
        self.assertEqual(len(self.db.scalars(select(AttendanceMonthEvent)).all()), count)
        self.user._active_residential_id = self.fixture.b.residential_id
        self.confirm(no_activity=True, note='No hubo actividades.')
        self.assertTrue(self.view(self.fixture.actor)['all_done'])
        period = self.view()['period']
        notice_id = period.all_announcement_id
        key = (self.fixture.proposal.proposal_id, self.fixture.a.residential_id, date(2026, 9, 10))
        change_months(self.db, self.fixture.actor, [key], reason='Corrección', today=self.today)
        self.db.commit()
        self.assertFalse(self.db.get(FaroAnnouncement, notice_id).is_active)
        self.assertFalse(self.view(self.fixture.actor)['all_done'])
        self.user._active_residential_id = self.fixture.a.residential_id
        reopened_notice = self.view()['rows'][0]['record'].reminder_announcement_id
        self.confirm()
        self.assertFalse(self.db.get(FaroAnnouncement, reopened_notice).is_active)
        self.assertTrue(self.view(self.fixture.actor)['all_done'])

    def test_roster_due_date_and_stale_config(self):
        values = dict(proposal_id=self.fixture.proposal.proposal_id, year=2026, month=9,
            due_on=date(2026, 10, 12), residential_ids=[self.fixture.a.residential_id],
            revision=0, reason='Solo MH participa en esta propuesta.', today=self.today)
        for role in ('user', 'supervisor'):
            actor = SimpleNamespace(**{**vars(self.user), 'role': role, '_active_residential_id': None})
            with self.assertRaises(HTTPException):
                configure_month(self.db, actor, **values)
        configure_month(self.db, self.fixture.actor, **values)
        self.db.commit()
        self.assertEqual(self.view(self.fixture.actor)['total'], 1)
        self.assertEqual(self.view()['due_on'], date(2026, 10, 12))
        with self.assertRaises(HTTPException) as error:
            configure_month(self.db, self.fixture.actor, **values)
        self.assertEqual(error.exception.status_code, 409)
        self.db.rollback()
        self.user._active_residential_id = self.fixture.b.residential_id
        with self.assertRaises(HTTPException) as error:
            confirm_month(self.db, self.user, proposal_id=self.fixture.proposal.proposal_id, year=2026,
                month=9, fingerprint='', declared=True, no_activity=True, note='Sin actividad', today=self.today)
        self.assertEqual(error.exception.status_code, 403)

    def test_reminders_only_pending_authorized_audience_and_cooldown(self):
        self.confirm()
        values = dict(proposal_id=self.fixture.proposal.proposal_id, year=2026, month=9, today=self.today)
        with self.assertRaises(HTTPException):
            remind_month(self.db, self.user, **values)
        count = remind_month(self.db, self.fixture.actor, **values, message='Favor completar.')
        self.db.commit()
        self.assertEqual(count, 1)
        self.assertEqual(announcement_notifications(self.db, self.user, today=self.today), [])
        self.user._active_residential_id = self.fixture.b.residential_id
        notices = announcement_notifications(self.db, self.user, today=self.today)
        self.assertEqual(len(notices), 1)
        self.assertIn('/ui/monthly-attendance?', notices[0]['actions'][0]['url'])
        with self.assertRaises(HTTPException) as error:
            remind_month(self.db, self.fixture.actor, **values)
        self.assertEqual(error.exception.status_code, 409)
        self.db.rollback()
        self.confirm(no_activity=True, note='Sin actividad.')
        self.assertEqual(announcement_notifications(self.db, self.user, today=self.today), [])

    def test_pending_provider_includes_zero_activity_and_keeps_older_unstarted_months(self):
        data = monthly_notification(self.db, self.fixture.actor, today=self.today)
        self.assertEqual(data['pending_count'], 4)  # Both residences for September and October.
        self.assertEqual(data['residential_count'], 2)
        self.confirm()
        data = monthly_notification(self.db, self.user, today=self.today)
        self.assertEqual([(g['month'], g['residential_id']) for g in data['groups']], [(10, self.fixture.a.residential_id)])
        data = monthly_notification(self.db, self.user, today=date(2026, 12, 11))
        self.assertEqual({g['month'] for g in data['groups']}, {10, 11})

    def test_notification_query_count_does_not_grow_with_months(self):
        counts = []
        actor = SimpleNamespace(role='admin', user_id=self.fixture.actor.user_id)
        for start in (date(2026, 10, 1), date(2020, 1, 1)):
            settings = self.db.get(MonthlyAttendanceSettings, 1)
            settings.first_month = start
            self.db.commit()
            queries = []
            def capture(*args):
                queries.append(args[2])
            event.listen(self.fixture.engine, 'before_cursor_execute', capture)
            try:
                with Session(self.fixture.engine) as db:
                    self.assertIsNotNone(monthly_notification(db, actor, today=self.today))
            finally:
                event.remove(self.fixture.engine, 'before_cursor_execute', capture)
            counts.append(len(queries))
        self.assertEqual(counts, [5, 5])

    def test_locked_inactive_finalized_and_future_periods_are_read_only(self):
        for field, value in (('is_active', False), ('status', 'finalized'), ('locked_through_year', 2026)):
            original = getattr(self.fixture.proposal, field)
            self.fixture.proposal.locked_through_month = 9
            setattr(self.fixture.proposal, field, value)
            self.db.commit()
            self.assertFalse(self.view()['writable'])
            with self.assertRaises(HTTPException):
                self.confirm()
            self.db.rollback()
            setattr(self.fixture.proposal, field, original)
            self.fixture.proposal.locked_through_month = None
            self.db.commit()
        with self.assertRaises(HTTPException):
            self.confirm(year=2027)


if __name__ == '__main__':
    unittest.main()
