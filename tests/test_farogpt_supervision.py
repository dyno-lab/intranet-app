"""Supervision questions reuse authorized, read-only operational sources."""
import json
import unittest
from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import event, select

from tests import test_data_validation_routes as fixtures
from app.api.routes import farogpt as routes
from app.models.base import Base
from app.models.monthly_attendance import AttendanceMonth, AttendanceMonthResidential
from app.models.notification import FaroAnnouncement
from app.models.proposal import Proposal
from app.models.proposal_participant import ProposalParticipant
from app.models.platform_permission import PlatformPermission
from app.models.user_platform_permission import UserPlatformPermission
from app.services import farogpt, data_validation


class FaroGPTSupervisionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DataValidationRoutes()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture.f
        self.db, self.user, self.client = self.fixture.db, self.fixture.user, self.fixture.client
        self.client.app.include_router(routes.router)
        Base.metadata.create_all(self.f.engine, tables=[FaroAnnouncement.__table__, AttendanceMonth.__table__, AttendanceMonthResidential.__table__])
        self.f.a.name = 'Arístides Chavier'
        self.db.commit()
        self.today = date(2026, 11, 14)

    def ask(self, question, context=None, user=None):
        return farogpt.answer(self.db, user or self.user, question, context or {}, today=self.today)

    def result(self, question, context=None, user=None):
        result = self.ask(question, context, user)
        self.assertEqual(result['type'], 'result', result)
        return result

    def send(self, question, context=None):
        token = self.client.get('/ui/farogpt/inicio').json()['csrf_token']
        return self.client.post('/ui/farogpt/consulta', json={'question': question, 'context': context or {}},
                                headers={'X-FaroGPT-CSRF': token})

    def test_requested_record_question_is_complete_without_month_and_groups_errors(self):
        self.f.old.apellido_paterno = ''
        self.f.old.edificio = None
        self.f.old.apart = None
        self.db.commit()
        result = self.result('Que expedientes tienen informacion incompleta en Chavier')
        self.assertEqual(result['context']['metric'], 'record_issues')
        self.assertEqual(result['period'], 'Expediente · revisión completa')
        self.assertEqual(result['value'], 1)
        rows = result['tables'][0]['rows']
        self.assertEqual(len(rows), 1)
        text = json.dumps(rows, ensure_ascii=False)
        for label in ('Primer apellido sin registrar', 'Edificio sin registrar', 'Apartamento sin registrar'):
            self.assertIn(label, text)
        self.assertIn(self.f.old.expediente_num, text)
        self.assertNotIn('Ana', text)
        self.assertNotIn('relacion_familiar', text)
        other = self.result('Expedientes incompletos en Chavier enero 2025')
        self.assertEqual(other['value'], result['value'])

    def test_activity_errors_group_sessions_and_exclude_future_dates(self):
        empty = self.f.make_session(self.f.a.residential_id, date(2026, 9, 12))
        empty.hours = 0
        self.f.make_session(self.f.a.residential_id, date(2027, 9, 12))
        self.db.commit()
        result = self.result('Que actividades tienen asistencias vacias o les faltan horas septiembre 2026')
        self.assertEqual(result['context']['metric'], 'session_issues')
        self.assertEqual(result['value'], 2)  # original: hours; new: hours + attendance
        self.assertEqual(len(result['tables'][0]['rows']), 2)
        self.assertEqual(result['metrics']['no_participations'], 1)
        self.assertEqual(result['metrics']['hours'], 2)
        self.assertEqual(self.result('Actividades sin asistencias septiembre 2026')['value'], 1)
        self.assertEqual(self.result('Actividades sin horas septiembre 2026')['value'], 2)
        self.assertEqual(self.result('Actividades sin asistencias u horas septiembre 2027')['value'], 0)

    def test_requested_monthly_confirmation_question_and_missing_month(self):
        result = self.result('Que residenciales faltan por confirmar las asistencias de octubre 2026')
        self.assertEqual(result['context']['metric'], 'attendance_pending')
        self.assertEqual(result['value'], 2)
        pending = self.ask('Confirmaciones mensuales pendientes')
        self.assertEqual(pending['type'], 'clarification')
        self.assertIn('mes o meses', pending['message'])
        self.assertEqual(self.result('octubre 2026', pending['context'])['value'], 2)

    def test_groups_same_record_across_proposals_and_keeps_historical_files(self):
        other = Proposal(code='006', name='Otra propuesta', is_active=False)
        self.db.add(other)
        self.db.flush()
        self.db.add(ProposalParticipant(person_id=self.f.person.person_id, proposal_id=other.proposal_id,
            residential_id=self.f.a.residential_id, nombre='Ana', apellido_paterno='Prueba',
            expediente_num=self.f.old.expediente_num))
        self.db.commit()
        result = self.result('Expedientes incompletos todas las propuestas')
        self.assertEqual(result['value'], 1)
        self.assertEqual(len(result['tables'][0]['rows']), 1)
        self.f.move()
        self.db.commit()
        historical = self.result('Expedientes incompletos todas las propuestas')
        self.assertEqual(historical['value'], 2)

    def test_justified_and_resolved_are_excluded_but_changed_evidence_reopens(self):
        filters = dict(proposal_id=self.f.proposal.proposal_id, residential_id=None, year=2026, months=(9,), today=self.today)
        hours = next(row for row in data_validation.review(self.db, self.user, **filters)['findings'] if row['rule']=='hours')
        data_validation.mutate(self.db, self.user, 'justify', filters, targets=[hours['token']], note='Excepción documentada de prueba.')
        self.db.commit()
        self.assertEqual(self.result('Actividades sin horas septiembre 2026')['value'], 0)
        self.f.session.hours = -1
        self.db.commit()
        self.assertEqual(self.result('Actividades sin horas septiembre 2026')['value'], 1)
        self.f.session.hours = 1
        self.db.commit()
        data_validation.mutate(self.db, self.user, 'revalidate', filters)
        self.db.commit()
        self.assertEqual(self.result('Actividades sin horas septiembre 2026')['value'], 0)

    def test_multiple_months_and_followups_keep_issue_type_until_new_report(self):
        self.f.make_session(self.f.a.residential_id, date(2026, 10, 12))
        self.db.commit()
        first = self.result('Actividades sin horas septiembre y octubre 2026')
        self.assertEqual(first['value'], 2)
        self.assertEqual(first['context']['issue_filter'], 'hours')
        self.assertEqual(self.result('y octubre', first['context'])['value'], 1)
        self.assertEqual(farogpt.summary(self.db, self.user, first['context'], today=self.today), first)
        raw = self.result('Cuantas actividades 2.b.5 septiembre 2026', first['context'])
        self.assertEqual(raw['context']['metric'], 'activities')
        self.assertIsNone(raw['context']['issue_filter'])
        monthly = self.result('Confirmaciones mensuales pendientes septiembre y octubre 2026')
        self.assertEqual(monthly['value'], 4)
        self.assertEqual(monthly['metrics']['residentials'], 2)

    def test_record_review_does_not_invent_a_period_for_later_attendance_question(self):
        record = self.result('Expedientes incompletos')
        self.assertIsNone(record['context']['year'])
        self.assertIsNone(record['context']['month'])
        next_question = self.ask('Actividades sin horas', record['context'])
        self.assertEqual(next_question['type'], 'clarification')
        self.assertIn('mes o meses', next_question['message'])
        self.assertEqual(self.result('septiembre 2026', next_question['context'])['value'], 1)

    def test_corrected_but_not_revalidated_is_explicitly_labelled(self):
        filters = dict(proposal_id=self.f.proposal.proposal_id, residential_id=None, year=2026, months=(9,), today=self.today)
        data_validation.mutate(self.db, self.user, 'revalidate', filters)
        self.db.commit()
        self.f.session.hours = 1
        self.db.commit()
        result = self.result('Actividades sin horas septiembre 2026')
        self.assertEqual(result['value'], 1)
        self.assertIn('Por revalidar', str(result['tables']))
        self.assertIn('ya no se detecta', result['note'])

    def test_record_label_is_escaped_and_report_filters_cannot_bypass_access(self):
        self.f.old.expediente_num = '<script>alert(1)</script>'
        self.db.commit()
        result = self.send('Expedientes incompletos').json()
        html = self.client.get(result['report_url']).text
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>alert(1)</script>', html)
        for filters in ({'metric':'record_issues', 'issue_filter':'hours'},
                        {'metric':'session_issues', 'issue_filter':'unknown'},
                        {'metric':'record_issues', 'field':'records'}):
            response = self.client.get('/ui/farogpt/informe', params=dict(year=2026, month=9, **filters))
            self.assertEqual(response.status_code, 422)

    def test_automation_permission_required_even_for_report_url(self):
        grant = self.db.scalar(select(UserPlatformPermission).join(PlatformPermission)
            .where(PlatformPermission.key == 'access_automation'))
        self.db.delete(grant)
        self.db.commit()
        with patch('app.services.data_validation.review') as review:
            self.assertEqual(self.send('Expedientes incompletos').status_code, 403)
            self.assertEqual(self.client.get('/ui/farogpt/informe', params={
                'metric':'session_issues', 'year':2026, 'month':9}).status_code, 403)
            review.assert_not_called()
        self.assertEqual(self.send('Confirmaciones mensuales pendientes octubre 2026').status_code, 200)

    def test_active_residential_cannot_be_escaped_through_questions_or_links(self):
        user = SimpleNamespace(user_id=self.user.user_id, username='Supervisión', role='supervisor',
                               _active_residential_id=self.f.b.residential_id)
        self.assertEqual(self.result('Expedientes incompletos global', user=user)['value'], 0)
        self.assertEqual(self.result('Actividades sin horas global septiembre 2026', user=user)['value'], 0)
        self.assertEqual(self.result('Confirmaciones mensuales pendientes octubre 2026', user=user)['value'], 1)
        with self.assertRaises(HTTPException) as caught:
            farogpt.summary(self.db, user, dict(metric='record_issues', residential_id=self.f.a.residential_id))
        self.assertEqual(caught.exception.status_code, 403)

    def test_opening_report_preserves_filters_and_protected_links(self):
        response = self.send('Expedientes incompletos en Chavier')
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        report = self.client.get(result['report_url'])
        self.assertEqual(report.status_code, 200, report.text)
        self.assertIn('Expediente · revisión completa', report.text)
        cell = result['tables'][0]['rows'][0][0]
        self.assertIn('/automatizaciones/faro/validacion?', cell['url'])
        self.assertEqual(self.client.get(cell['url']).status_code, 200)
        self.assertIn('href="' + cell['url'].replace('&', '&amp;') + '"', report.text)
        params = parse_qs(urlsplit(cell['url']).query)
        self.assertEqual(params['residential_id'], [str(self.f.a.residential_id)])
        self.assertEqual(params['kind'], ['record'])
        self.assertNotIn('Ana Prueba', report.text)

    def test_queries_only_read_and_do_not_silently_ignore_filters(self):
        statements = []
        def capture(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lstrip().split()[0].upper())
        event.listen(self.f.engine, 'before_cursor_execute', capture)
        try:
            self.result('Expedientes incompletos')
            self.result('Actividades sin horas septiembre 2026')
            self.result('Confirmaciones mensuales pendientes octubre 2026')
        finally:
            event.remove(self.f.engine, 'before_cursor_execute', capture)
        self.assertEqual(set(statements), {'SELECT'})
        for question in ('Expedientes incompletos menores de 18 años',
                         'Expedientes incompletos con asistencias en Chavier octubre 2026',
                         'Confirmaciones mensuales pendientes con horas octubre 2026',
                         'Actividades sin asistencias con horas septiembre 2026',
                         'Actividades sin horas con asistencias septiembre 2026',
                         'Actividades sin asistencias y horas septiembre 2026',
                         'Actividades sin horas 2.b.5 septiembre 2026',
                         'Confirma las asistencias de octubre 2026'):
            self.assertEqual(self.ask(question)['type'], 'clarification')
        self.assertFalse(self.db.new or self.db.dirty or self.db.deleted)


if __name__ == '__main__':
    unittest.main()
