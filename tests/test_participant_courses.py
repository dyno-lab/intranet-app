from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import event, select

from tests import test_full_monthly_report_data as fixtures
from app.models.participant_monthly_course import ParticipantMonthlyCourse
from app.services.participant_courses import build_course_report, save_course_assignments


class ParticipantCoursesTests(unittest.TestCase):
    def setUp(self):
        self.source = fixtures.FullMonthlyReportDataTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.db = self.source.db
        self.user = self.source.user
        self.user.user_id = 1
        self.db.execute(self.source.tables['activity_codes'].update().values(code='2.b.5'))
        self.source.insert('activity_sessions', session_id=6, proposal_id=1, residential_id=1,
                           session_date=date(2026, 8, 1), activity_code_id=10, employee_id=1, hours=1)
        self.source.insert('attendance', attendance_id=7, session_id=6, participant_id=1, attended=True)
        self.db.commit()
        self.filters = dict(proposal_ids=[1, 2], month=7, year=2026, employee_id=0)

    def build(self, **filters):
        return build_course_report(self.db, self.user, **{**self.filters, **filters})

    def change(self, participant=1, month=7, course='reposteria', revision=0, year=2026):
        return dict(participant_id=participant, month=month, year=year, course=course, revision=revision)

    def save(self, changes, **filters):
        return save_course_assignments(self.db, self.user, {**self.filters, **filters}, changes)

    def test_unique_people_across_proposals_and_independent_calendar_months(self):
        filters = dict(period_type='custom', start_date='2026-07-01', end_date='2026-08-31')
        data = self.build(**filters)
        self.assertEqual(data['total'], 2)
        self.assertEqual([m['key'] for m in data['months']], ['2026-07', '2026-08'])
        self.assertEqual([c['attended'] for c in data['rows'][0]['cells']], [True, True])
        self.assertEqual([c['attended'] for c in data['rows'][1]['cells']], [True, False])
        self.save([self.change(), self.change(month=8, course='charcuteria')], **filters)
        row = self.build(**filters)['rows'][0]
        self.assertEqual([c['course'] for c in row['cells']], ['reposteria', 'charcuteria'])
        self.assertEqual(self.build(proposal_ids=[2])['rows'][0]['cells'][0]['course'], 'reposteria')

    def test_absent_attendance_wrong_activity_and_other_proposal_are_excluded(self):
        self.assertEqual([r['participant_id'] for r in self.build()['rows']], [1, 2])
        self.assertEqual(self.build(proposal_ids=[2])['total'], 1)
        self.assertEqual(self.build(month=9)['total'], 0)
        self.db.execute(self.source.tables['activity_codes'].update().values(code='2.b.50'))
        self.db.commit()
        self.assertEqual(self.build()['total'], 0)

    def test_custom_dates_are_exact_and_months_cross_year(self):
        self.assertEqual(self.build(period_type='custom', start_date='2026-07-02', end_date='2026-07-30')['total'], 0)
        months = self.build(period_type='custom', start_date='2025-12-15', end_date='2026-01-15')['months']
        self.assertEqual([m['key'] for m in months], ['2025-12', '2026-01'])

    def test_user_cannot_write_outside_residential_or_without_confirmed_attendance(self):
        self.user.role, self.user.residential_id = 'user', 2
        self.assertEqual(self.build(employee_id=-1)['total'], 1)
        for change in [self.change(participant=2), self.change(participant=3), self.change(month=8)]:
            with self.subTest(change=change), self.assertRaises(HTTPException):
                self.save([change])
        self.save([self.change()])

    def test_read_only_roles_cannot_save(self):
        for role in ('viewer', 'unknown'):
            self.user.role, self.user.residential_id = role, 1
            self.assertFalse(self.build()['can_edit'])
            with self.assertRaises(HTTPException) as error:
                self.save([self.change()])
            self.assertEqual(error.exception.status_code, 403)

    def test_supervisor_can_save_and_change_courses_in_global_and_residential_scope(self):
        self.user.role = 'supervisor'
        for scope in (0, -1, -2):
            with self.subTest(scope=scope):
                data = self.build(employee_id=scope)
                self.assertTrue(data['can_edit'])
                cell = data['rows'][0]['cells'][0]
                self.assertTrue(cell['editable'])
                self.save([self.change(course='charcuteria', revision=cell['revision'])], employee_id=scope)
                self.assertEqual(self.build(employee_id=scope)['rows'][0]['cells'][0]['course'], 'charcuteria')

    def test_active_residential_is_respected_for_users_and_supervisors(self):
        self.user.residential_id = 1
        self.user._active_residential_id = 2
        for revision, role in enumerate(('user', 'supervisor')):
            self.user.role = role
            data = self.build(employee_id=-1)
            self.assertEqual(data['selected_employee_id'], -2)
            self.assertEqual([r['participant_id'] for r in data['rows']], [1])
            self.assertTrue(data['rows'][0]['cells'][0]['editable'])
            self.save([self.change(revision=revision)], employee_id=-1)
            with self.assertRaises(HTTPException) as error:
                self.save([self.change(participant=2)], employee_id=0)
            self.assertEqual(error.exception.status_code, 403)

    def test_supervisor_cannot_edit_closed_finalized_or_future_months(self):
        self.user.role = 'supervisor'
        proposals = self.source.tables['proposals']
        for values in (
            dict(locked_through_year=2026, locked_through_month=7, status='active'),
            dict(locked_through_year=None, locked_through_month=None, status='finalized'),
        ):
            with self.subTest(values=values):
                self.db.execute(proposals.update().where(proposals.c.proposal_id == 1).values(**values))
                self.db.commit()
                self.assertFalse(self.build(proposal_ids=[2])['rows'][0]['cells'][0]['editable'])
                with self.assertRaises(HTTPException) as error:
                    self.save([self.change()], proposal_ids=[2])
                self.assertEqual(error.exception.status_code, 409)
        self.db.execute(proposals.update().where(proposals.c.proposal_id == 1).values(status='active'))
        self.db.commit()
        with patch('app.services.participant_courses.is_future_reporting_period', return_value=True):
            self.assertFalse(self.build()['rows'][0]['cells'][0]['editable'])
            with self.assertRaises(HTTPException) as error:
                self.save([self.change()])
            self.assertEqual(error.exception.status_code, 409)

    def test_validation_atomicity_and_month_uniqueness(self):
        for changes in [[self.change(), self.change(participant=2, course='otro')],
                        [self.change(), self.change(course='charcuteria')],
                        [self.change(), self.change(participant=3)]]:
            with self.subTest(changes=changes), self.assertRaises(HTTPException):
                self.save(changes)
            self.assertEqual(self.db.scalars(select(ParticipantMonthlyCourse)).all(), [])

    def test_stale_edits_do_not_overwrite_and_clearing_retains_revision(self):
        self.save([self.change()])
        with self.assertRaises(HTTPException) as error:
            self.save([self.change(course='charcuteria')])
        self.assertEqual(error.exception.status_code, 409)
        self.save([self.change(course='', revision=1)])
        cell = self.build()['rows'][0]['cells'][0]
        self.assertEqual((cell['course'], cell['revision']), ('', 2))
        with self.assertRaises(HTTPException):
            self.save([self.change()])

    def test_closed_proposal_cannot_be_bypassed_by_selecting_other_extension(self):
        self.db.execute(self.source.tables['proposals'].update().where(
            self.source.tables['proposals'].c.proposal_id == 1).values(locked_through_year=2026, locked_through_month=7))
        self.db.commit()
        self.assertFalse(self.build(proposal_ids=[2])['rows'][0]['cells'][0]['editable'])
        with self.assertRaises(HTTPException) as error:
            self.save([self.change()], proposal_ids=[2])
        self.assertEqual(error.exception.status_code, 409)

    def test_invalid_filters_fail_explicitly(self):
        for filters in [dict(proposal_ids=[]), dict(proposal_ids=[999]), dict(month=13),
                        dict(period_type='custom', start_date='2026-08-01', end_date='2026-07-01')]:
            with self.subTest(filters=filters), self.assertRaises(HTTPException):
                self.build(**filters)

    def test_large_attendance_set_keeps_sql_server_parameter_budget_and_reads_only(self):
        people = self.source.tables['participants']
        attendance = self.source.tables['attendance']
        self.db.execute(people.insert(), [dict(participant_id=i, residential_id=1,
            nombre=f'Persona {i}', apellido_paterno='Prueba', is_active=True) for i in range(10, 2211)])
        self.db.execute(attendance.insert(), [dict(attendance_id=i + 100, session_id=1,
            participant_id=i, attended=True) for i in range(10, 2211)])
        self.db.commit()
        statements = []
        def record(_conn, _cursor, statement, params, _context, _many):
            statements.append((statement, len(params)))
        event.listen(self.source.engine, 'before_cursor_execute', record)
        try:
            data = self.build()
        finally:
            event.remove(self.source.engine, 'before_cursor_execute', record)
        self.assertEqual(data['total'], 2203)
        self.assertTrue(all(sql.lstrip().upper().startswith('SELECT') for sql, _ in statements))
        self.assertLess(max(count for _, count in statements), 2100)
