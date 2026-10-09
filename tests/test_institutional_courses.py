from datetime import date
import json
from types import SimpleNamespace
import unittest

from sqlalchemy import event
from sqlalchemy.dialects import mssql

from tests import test_participant_courses as fixtures
from app.api.routes import institutional_reports as reports


class InstitutionalCoursesTests(unittest.TestCase):
    def setUp(self):
        self.source = fixtures.ParticipantCoursesTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.db = self.source.db
        self.data = self.source.source
        self.period = dict(period_type='custom', start_date='2026-07-01', end_date='2026-08-31')

    def summary(self, **overrides):
        filters = dict(proposal_ids=[1, 2], year=2026,
                       start_date=date(2026, 7, 1), end_date=date(2026, 8, 31))
        return reports._faro_course_summary(self.db, **{**filters, **overrides})

    def counts(self, result):
        return {row['code']: row['people'] for row in result['by_course']}

    def test_each_person_counts_once_per_course_across_months_and_proposals(self):
        self.source.save([self.source.change(), self.source.change(participant=2),
                          self.source.change(month=8, course='charcuteria')], **self.period)
        result = self.summary()
        self.assertEqual(self.counts(result), dict(reposteria=2, charcuteria=1))
        self.assertEqual((result['unique_people'], result['total_by_course'], result['pending_people']), (2, 3, 0))
        self.assertNotIn('Participante', json.dumps(result))
        self.assertNotIn('participant_id', json.dumps(result))
        self.source.save([self.source.change(month=8, revision=1)], **self.period)
        self.assertEqual(self.summary()['total_by_course'], 2)

    def test_pending_people_are_unique_and_can_also_have_a_classified_month(self):
        self.source.save([self.source.change()])
        result = self.summary()
        self.assertEqual((result['unique_people'], result['total_by_course'], result['pending_people']), (2, 1, 2))
        self.source.save([self.source.change(course='', revision=1)])
        self.assertEqual(self.summary()['pending_people'], 2)
        self.assertEqual(self.summary()['total_by_course'], 0)

    def test_existing_filters_and_confirmed_exact_activity_control_eligibility(self):
        self.source.save([self.source.change(), self.source.change(month=8, course='charcuteria')], **self.period)
        self.assertEqual(self.summary(proposal_ids=[2])['total_by_course'], 1)
        self.assertEqual(self.summary(proposal_ids=[2])['unique_people'], 1)
        august = self.summary(start_date=date(2026, 8, 1), end_date=date(2026, 8, 1))
        self.assertEqual(self.counts(august), dict(reposteria=0, charcuteria=1))
        self.assertEqual(self.summary(start_date=date(2026, 7, 2), end_date=date(2026, 7, 30))['unique_people'], 0)
        self.assertEqual(self.summary(year=2025)['unique_people'], 0)
        self.assertEqual(self.summary(year=None)['unique_people'], 2)
        self.db.execute(self.data.tables['activity_codes'].update().values(code='2.b.50'))
        self.db.commit()
        self.assertEqual(self.summary()['unique_people'], 0)

    def test_current_person_identity_bridges_courses_and_does_not_trust_stale_legacy_id(self):
        self.source.save([self.source.change(), self.source.change(participant=2, course='charcuteria')])
        self.data.insert('persons', person_id=501, legacy_participant_id=1)
        self.data.insert('persons', person_id=502, legacy_participant_id=None)
        for pp, person, proposal in [(101, 501, 1), (102, 502, 1), (103, 502, 3)]:
            self.data.insert('proposal_participants', proposal_participant_id=pp, person_id=person, proposal_id=proposal)
        # Duplicate current and legacy attendance for the same person; stale legacy ID must not win.
        self.data.insert('attendance', attendance_id=20, session_id=1, participant_id=2, proposal_participant_id=101, attended=True)
        self.data.insert('attendance', attendance_id=21, session_id=1, proposal_participant_id=102, attended=True)
        self.data.insert('attendance', attendance_id=22, session_id=1, participant_id=3, proposal_participant_id=103, attended=True)
        self.db.commit()
        result = self.summary(end_date=date(2026, 7, 31))
        self.assertEqual(result['unique_people'], 3)
        self.assertEqual(result['pending_people'], 1)
        self.assertEqual(self.counts(result), dict(reposteria=1, charcuteria=1))

    def test_retired_course_is_excluded_from_chart_without_reclassifying_saved_people(self):
        self.data.insert('participant_monthly_courses', participant_id=1, report_year=2026,
                         report_month=7, course_code='campo_laboral', revision=1)
        self.db.commit()
        self.source.save([self.source.change(participant=2),
                          self.source.change(month=8, course='charcuteria')], **self.period)
        result = self.summary()
        self.assertEqual(self.counts(result), dict(reposteria=1, charcuteria=1))
        self.assertEqual((result['unique_people'], result['total_by_course'], result['pending_people']), (2, 2, 0))
        self.assertNotIn('campo_laboral', json.dumps(result))
        self.assertEqual(self.source.build()['rows'][0]['cells'][0]['course'], 'campo_laboral')

        # This proposal/month only has a saved retired course: no pie sector,
        # and it must not become a pending selection merely because it is hidden.
        historical = self.summary(proposal_ids=[2], end_date=date(2026, 7, 31))
        self.assertEqual(self.counts(historical), dict(reposteria=0, charcuteria=0))
        self.assertEqual((historical['unique_people'], historical['total_by_course'], historical['pending_people']), (1, 0, 0))

    def test_large_population_uses_one_read_query_with_bounded_parameters(self):
        self.db.execute(self.data.tables['participants'].insert(), [dict(participant_id=i, nombre=f'Persona {i}') for i in range(10, 2211)])
        self.db.execute(self.data.tables['attendance'].insert(), [dict(attendance_id=i+100, session_id=1, participant_id=i, attended=True) for i in range(10, 2211)])
        self.db.commit()
        executed = []
        def capture(_conn, _cursor, statement, parameters, _context, _many):
            executed.append((statement, len(parameters)))
        event.listen(self.data.engine, 'before_cursor_execute', capture)
        try:
            result = self.summary()
        finally:
            event.remove(self.data.engine, 'before_cursor_execute', capture)
        self.assertEqual(result['unique_people'], 2203)
        self.assertEqual(result['pending_people'], 2203)
        self.assertEqual(len(executed), 1)
        self.assertTrue(executed[0][0].lstrip().upper().startswith('SELECT'))
        self.assertLess(executed[0][1], 2100)

    def test_month_and_year_join_compile_for_sql_server(self):
        class Capture:
            def execute(_, statement):
                sql = str(statement.compile(dialect=mssql.dialect())).lower()
                self.assertIn('datepart(month, activity_sessions.session_date)', sql)
                self.assertIn('datepart(year, activity_sessions.session_date)', sql)
                self.assertIn('participant_monthly_courses', sql)
                return type('Result', (), {'all': lambda _: []})()
        result = reports._faro_course_summary(Capture(), proposal_ids=[1, 2], year=2026,
                                            start_date=None, end_date=None)
        self.assertEqual(result['unique_people'], 0)

    def test_existing_data_endpoint_returns_courses_under_its_shared_filters(self):
        self.db.connection().connection.dbapi_connection.create_function(
            'datefromparts', 3, lambda y, m, d: date(y, m, d).isoformat())
        self.source.save([self.source.change(), self.source.change(month=8, course='charcuteria')], **self.period)
        response = reports.faro_institutional_report_data(
            request=SimpleNamespace(session={}), db=self.db,
            proposal_ids=['1', '2'], year='2026', start_date='2026-08-01', end_date='2026-08-31')
        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['filters'], dict(proposal_ids=[1, 2], year=2026,
                         start_date='2026-08-01', end_date='2026-08-31'))
        self.assertEqual(self.counts(payload['real']['courses']), dict(reposteria=0, charcuteria=1))
        self.assertEqual(payload['real']['courses']['unique_people'], 1)
        self.assertIn('courses', payload['meta']['real_metrics'])
        self.assertEqual(response.headers['cache-control'], 'no-store')
