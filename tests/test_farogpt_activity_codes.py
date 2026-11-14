"""Activity-code queries count sessions, with historical residential/proposal filters."""
import unittest
from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from sqlalchemy import event

from tests import test_farogpt as fixtures
from app.models.activity_code import ActivityCode
from app.models.attendance import Attendance
from app.models.proposal import Proposal
from app.services import farogpt


class FaroGPTActivityCodeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.FaroGPTTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture.f
        self.db = self.fixture.db
        self.f.session.session_date = date(2026, 8, 1)
        self.f.code.description = 'Desarrollo de destrezas para el empleo'
        self.f.code.proposal_id = self.f.proposal.proposal_id
        self.f.make_session(self.f.a.residential_id, date(2026, 8, 31))
        other_residential = self.f.make_session(self.f.b.residential_id, date(2026, 8, 15))
        self.db.add(Attendance(session_id=other_residential.session_id,
                              participant_id=self.f.other.participant_id, attended=True))
        self.other_proposal = Proposal(code='006', name='Segunda propuesta', is_active=False)
        self.other_code = ActivityCode(code='2.b.6', description='Otra actividad')
        self.db.add_all([self.other_proposal, self.other_code])
        self.db.flush()
        shared = self.f.make_session(self.f.a.residential_id, date(2026, 8, 17))
        shared.proposal_id = self.other_proposal.proposal_id
        unrelated = self.f.make_session(self.f.a.residential_id, date(2026, 8, 18))
        unrelated.activity_code_id = self.other_code.activity_code_id
        self.db.add(Attendance(session_id=unrelated.session_id, participant_id=self.f.participant.participant_id,
                              proposal_participant_id=self.f.old.proposal_participant_id, attended=True))
        self.f.make_session(self.f.a.residential_id, date(2026, 7, 31))
        self.f.make_session(self.f.a.residential_id, date(2026, 9, 1))
        self.db.commit()

    def ask(self, question, context=None, user=None):
        return farogpt.answer(self.db, user or self.f.actor, question, context or {'proposal_scope': 'all'}, today=date(2026, 11, 14))

    def result(self, question, **kwargs):
        result = self.ask(question, **kwargs)
        self.assertEqual(result['type'], 'result', result)
        return result

    def test_exact_user_question_counts_sessions_including_empty_attendance(self):
        result = self.result('CUANTAS ACTIVIDADES 2.B.5 SE HICIERON EN AGOSTO 2026')
        self.assertEqual(result['value'], 4)
        self.assertEqual(result['metrics'], {'activities': 4, 'duplicates': 2, 'people': 1})
        self.assertEqual(result['context']['activity_code'], '2.b.5')
        self.assertIn('2.b.5', result['title'])
        self.assertIn('Desarrollo de destrezas', result['activity'])
        self.assertEqual(parse_qs(urlsplit(result['report_url']).query)['activity_code'], ['2.b.5'])
        self.assertEqual(farogpt.summary(self.db, self.f.actor, result['context']), result)

    def test_dotted_compact_and_spaced_codes_are_equivalent(self):
        for code in ('2.b.5', '2B5', '2 B 5'):
            with self.subTest(code=code):
                result = self.result(f'Cuántas actividades {code} se realizaron en agosto 2026')
                self.assertEqual(result['value'], 4)
                self.assertEqual(result['context']['activity_code'], '2.b.5')

    def test_residential_and_proposal_filters_follow_session_not_code_owner(self):
        self.assertEqual(self.result('Actividades 2.b.5 Chavier agosto 2026')['value'], 3)
        self.assertEqual(self.result('Actividades 2.b.5 Bella Vista agosto 2026')['value'], 1)
        self.assertEqual(self.result('Actividades 2.b.5 agosto 2026 propuesta 005')['value'], 3)
        self.assertEqual(self.result('Actividades 2.b.5 agosto 2026 propuesta 006')['value'], 1)

    def test_comparison_and_followup_preserve_code_until_explicitly_reset(self):
        first = self.result('Actividades 2.b.5 Chavier agosto 2026')
        comparison = self.result('Comparar con julio 2026', context=first['context'])
        self.assertEqual(comparison['comparison']['value'], 1)
        self.assertEqual(comparison['comparison']['difference'], 2)
        global_result = self.result('Y global', context=first['context'])
        self.assertEqual(global_result['value'], 4)
        self.assertEqual(global_result['context']['activity_code'], '2.b.5')
        all_activities = self.result('Todas las actividades global agosto 2026', context=first['context'])
        self.assertEqual(all_activities['value'], 5)
        self.assertIsNone(all_activities['context']['activity_code'])
        self.assertEqual(self.ask('Comparar actividades 2.b.6 en julio 2026', first['context'])['type'], 'clarification')

    def test_other_code_and_other_report_do_not_reuse_a_stale_code(self):
        first = self.result('Actividades 2.b.5 agosto 2026')
        self.assertEqual(self.result('Y la 2.b.6', context=first['context'])['value'], 1)
        other_report = self.result('No duplicados agosto 2026', context=first['context'])
        self.assertIsNone(other_report['context']['activity_code'])
        self.assertEqual(other_report['context']['metric'], 'no_duplicado')

    def test_activity_code_is_kept_when_month_is_supplied_later(self):
        first = self.ask('Cuántas actividades 2.b.5 se hicieron')
        self.assertEqual(first['type'], 'clarification')
        self.assertEqual(first['context']['activity_code'], '2.b.5')
        self.assertEqual(self.result('agosto 2026', context=first['context'])['value'], 4)

    def test_unknown_multiple_codes_and_unsupported_report_filter_are_not_ignored(self):
        for question in ('actividades 9.z.99 agosto 2026', 'actividades 2.b.5 y 2.b.6 agosto 2026',
                         'notas 2.b.5 agosto 2026', 'ADM 2.b.5 agosto 2026',
                         'actividades 2.b.5 del 5 al 10 de agosto 2026'):
            with self.subTest(question=question):
                result = self.ask(question)
                self.assertEqual(result['type'], 'clarification', result)
                self.assertNotIn('value', result)
        with self.assertRaises(HTTPException):
            farogpt.summary(self.db, self.f.actor, {'metric': 'activities', 'month': 8, 'year': 2026,
                                                   'activity_code': '9.z.99'})
        with self.assertRaises(HTTPException):
            farogpt.summary(self.db, self.f.actor, {'metric': 'notes', 'month': 8, 'year': 2026,
                                                   'activity_code': '2.b.5'})

    def test_valid_code_with_zero_sessions_and_inactive_historical_code(self):
        self.assertEqual(self.result('Actividades 2.b.6 julio 2026')['value'], 0)
        self.f.code.is_active = False
        self.db.commit()
        self.assertEqual(self.result('Actividades 2.b.5 agosto 2026')['value'], 4)

    def test_day_range_is_not_misinterpreted_as_an_existing_activity_code(self):
        self.db.add(ActivityCode(code='1.a.5', description='Otra actividad válida'))
        self.db.commit()
        self.assertEqual(self.ask('Actividades del 1 a 5 de agosto 2026')['type'], 'clarification')
        self.assertEqual(self.result('Actividades de 1.A.5 en agosto 2026')['value'], 0)

    def test_participations_and_unique_people_keep_the_activity_filter(self):
        self.assertEqual(self.result('Participaciones 2.b.5 agosto 2026')['value'], 2)
        self.assertEqual(self.result('Participaciones de la actividad 2.b.5 agosto 2026')['value'], 2)
        self.assertEqual(self.result('Participantes únicos 2.b.5 agosto 2026')['value'], 1)
        self.assertEqual(self.result('Participantes únicos en la actividad 2.b.5 agosto 2026')['value'], 1)
        self.assertEqual(self.ask('Actividades y participaciones 2.b.5 agosto 2026')['type'], 'clarification')

    def test_scoped_supervisor_and_read_only_queries(self):
        scoped = SimpleNamespace(role='supervisor', _active_residential_id=self.f.b.residential_id)
        statements = []
        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement.lstrip().split()[0].upper())
        event.listen(self.f.engine, 'before_cursor_execute', capture)
        try:
            result = self.result('Actividades 2.b.5 global agosto 2026', user=scoped)
            self.assertEqual(result['value'], 1)
            self.assertEqual(result['context']['residential_id'], self.f.b.residential_id)
            with self.assertRaises(HTTPException):
                farogpt.summary(self.db, scoped, dict(result['context'], residential_id=self.f.a.residential_id))
        finally:
            event.remove(self.f.engine, 'before_cursor_execute', capture)
        self.assertEqual(set(statements), {'SELECT'})
        self.assertFalse(self.db.new or self.db.dirty or self.db.deleted)


if __name__ == '__main__':
    unittest.main()
