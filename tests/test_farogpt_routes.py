import unittest
from datetime import date

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from tests.test_farogpt import FaroGPTTests
from app.api.routes import farogpt as routes
from app.api.deps import get_db
from app.models.base import Base
from app.models.platform_permission import PlatformPermission
from app.models.user_platform_permission import UserPlatformPermission
from app.models.user_residential import UserResidential
from app.core.platform_permissions import ACCESS_FARO


class FaroGPTRouteTests(unittest.TestCase):
    def setUp(self):
        self.source = FaroGPTTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.f = self.source.f
        self.db = self.f.db
        Base.metadata.create_all(self.f.engine, tables=[PlatformPermission.__table__,
            UserPlatformPermission.__table__, UserResidential.__table__])
        permission = PlatformPermission(key=ACCESS_FARO, name='Faro', is_active=True)
        self.db.add(permission)
        self.db.flush()
        self.grant = UserPlatformPermission(user_id=self.f.actor.user_id, permission_id=permission.permission_id)
        self.db.add(self.grant)
        self.db.add(UserResidential(user_id=self.f.actor.user_id, residential_id=self.f.b.residential_id))
        self.db.commit()
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key='farogpt-local-test-only')
        app.include_router(routes.router)
        app.dependency_overrides[get_db] = lambda: self.db

        @app.get('/test/login')
        def login(request: Request, scoped: bool = False):
            request.session.clear()
            request.session.update(user_id=self.f.actor.user_id, session_version=self.f.actor.session_version)
            if scoped:
                request.session['active_residential_id'] = self.f.b.residential_id

        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.client.get('/test/login')

    def send(self, question='participantes únicos Chavier septiembre 2026', **extra):
        first = self.client.get('/ui/farogpt/inicio')
        token = first.json()['csrf_token']
        return self.client.post('/ui/farogpt/consulta', json={'question': question, **extra},
            headers={'X-FaroGPT-CSRF': token})

    def test_authenticated_conversation_and_report_match(self):
        response = self.send()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.json()['value'], 1)
        report = self.client.get(response.json()['report_url'])
        self.assertEqual(report.status_code, 200, report.text)
        self.assertIn('Arístides Chavier', report.text)
        self.assertIn('Septiembre 2026', report.text)
        self.assertNotIn('Ana Prueba', report.text)
        self.assertEqual(report.headers['cache-control'], 'no-store')

    def test_summary_recovers_pending_conversation_and_matches_report(self):
        self.f.proposal.name = '2025-000094-C'
        self.f.session.session_date = date(2026, 6, 10)
        self.db.commit()
        pending = self.send('Participantes únicos en Chavier menores de 18 años').json()
        self.assertEqual(pending['type'], 'clarification')
        rejected = self.send('junio 2026', context=pending['context']).json()
        self.assertEqual(rejected['type'], 'clarification')
        self.assertEqual(rejected['suggestions'], ['Resumen de Participantes únicos Junio 2026'])
        response = self.send(rejected['suggestions'][0], context=rejected['context'])
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['type'], 'result', result)
        self.assertEqual(result['value'], 1)
        self.assertEqual(result['context']['proposal_id'], self.f.proposal.proposal_id)
        self.assertEqual(result['context']['residential_id'], self.f.a.residential_id)
        self.assertIsNone(result['context']['pending_terms'])
        report = self.client.get(result['report_url'])
        self.assertEqual(report.status_code, 200, report.text)
        self.assertIn('Junio 2026', report.text)
        self.assertIn('2025-000094-C', report.text)
        self.assertIn('Arístides Chavier', report.text)

    def test_activity_code_is_preserved_in_api_and_report(self):
        self.f.code.description = 'Destrezas para el empleo'
        self.db.commit()
        response = self.send('Cuántas actividades 2.B.5 se hicieron en septiembre 2026')
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['value'], 1)
        self.assertEqual(result['context']['activity_code'], '2.b.5')
        report = self.client.get(result['report_url'])
        self.assertEqual(report.status_code, 200, report.text)
        self.assertIn('2.b.5', report.text)
        self.assertIn('Destrezas para el empleo', report.text)
        self.assertEqual(self.client.get('/ui/farogpt/informe', params={
            'metric': 'activities', 'month': 9, 'year': 2026, 'activity_code': '2B5'}).status_code, 200)

    def test_activity_code_context_is_validated_and_scoped(self):
        self.assertEqual(self.send(context={'activity_code': 'DROP TABLE attendance'}).status_code, 422)
        self.assertEqual(self.client.get('/ui/farogpt/informe', params={
            'metric': 'activities', 'month': 9, 'year': 2026, 'activity_code': '9.z.99'}).status_code, 422)
        self.client.get('/test/login?scoped=true')
        result = self.send('Actividades 2b5 global septiembre 2026').json()
        self.assertEqual(result['value'], 0)
        self.assertEqual(result['context']['residential_id'], self.f.b.residential_id)
        self.assertEqual(self.send('agosto 2026', context={'metric': 'activities', 'activity_code': '2.b.5',
            'month': 9, 'year': 2026, 'residential_id': self.f.a.residential_id}).status_code, 403)

    def test_csrf_and_session_required(self):
        response = self.client.post('/ui/farogpt/consulta', json={'question': 'participantes únicos septiembre 2026'})
        self.assertEqual(response.status_code, 403)
        self.client.cookies.clear()
        response = self.client.get('/ui/farogpt/inicio', follow_redirects=False)
        self.assertEqual(response.status_code, 303)

    def test_guided_question_and_multiple_month_report_link(self):
        first = self.send('Cuántas actvidades 2b5 se hicieron').json()
        self.assertEqual(first['type'], 'clarification')
        self.assertIn('mes o meses', first['message'])
        response = self.send('agosto y septiembre 2026', context=first['context'])
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['value'], 1)
        self.assertEqual(result['context']['months'], [8, 9])
        self.assertEqual(result['context']['proposal_id'], self.f.proposal.proposal_id)
        report = self.client.get(result['report_url'])
        self.assertEqual(report.status_code, 200, report.text)
        self.assertIn('Agosto y Septiembre 2026', report.text)
        self.assertIn('Desglose por mes', report.text)
        self.assertNotIn('Ana Prueba', report.text)
        for months in ([0, 8], [8, 13], ['invalid'], list(range(1, 14))):
            with self.subTest(months=months):
                bad = self.client.get('/ui/farogpt/informe', params={
                    'metric': 'activities', 'year': 2026, 'months': months})
                self.assertEqual(bad.status_code, 422, bad.text)

    def test_reported_question_asks_period_then_returns_scoped_result(self):
        self.f.code.code = '1.a.2'
        self.db.commit()
        pending = self.send('Cuantas actividades 1.a.2 se a realizado').json()
        self.assertEqual(pending['type'], 'clarification')
        self.assertIn('mes o meses', pending['message'])
        result = self.send('septiembre 2026', context=pending['context']).json()
        self.assertEqual(result['type'], 'result', result)
        self.assertEqual(result['value'], 1)
        self.assertEqual(result['context']['activity_code'], '1.a.2')
        self.assertEqual(self.client.get(result['report_url']).status_code, 200)

    def test_report_query_rejects_unknown_or_conflicting_filters(self):
        for extra in ({'months': [8, 9]}, {'proposal_scope': 'all', 'proposal_id': self.f.proposal.proposal_id},
                      {'unsupported': 'filter'}):
            with self.subTest(extra=extra):
                response = self.client.get('/ui/farogpt/informe', params={
                    'metric': 'activities', 'year': 2026, 'month': 9, **extra})
                self.assertEqual(response.status_code, 422)

    def test_access_permission_and_roles(self):
        self.f.actor.role = 'supervisor'
        self.db.commit()
        self.assertEqual(self.send().status_code, 200)
        for role in ('viewer', 'user'):
            self.f.actor.role = role
            self.db.commit()
            self.assertEqual(self.client.get('/ui/farogpt/inicio').status_code, 403)
        self.f.actor.role = 'admin'
        self.db.delete(self.grant)
        self.db.commit()
        self.assertEqual(self.client.get('/ui/farogpt/inicio').status_code, 403)

    def test_context_tampering_and_scope_cannot_broaden_data(self):
        self.client.get('/test/login?scoped=true')
        result = self.send('participantes únicos septiembre 2026')
        self.assertEqual(result.json()['value'], 0)
        response = self.send('septiembre 2026', context={'metric': 'people',
            'residential_id': self.f.a.residential_id, 'month': 9, 'year': 2026})
        self.assertEqual(response.status_code, 403)
        response = self.client.get('/ui/farogpt/informe', params={
            'metric': 'people', 'residential_id': self.f.a.residential_id, 'month': 9, 'year': 2026})
        self.assertEqual(response.status_code, 403)

    def test_invalid_payload_and_unknown_filters(self):
        self.assertEqual(self.send('x' * 801).status_code, 422)
        self.assertEqual(self.send(context={'year': 1900}).status_code, 422)
        self.assertEqual(self.send(context={'month': 13}).status_code, 422)
        response = self.send('participantes únicos chavier septiembre 2026 mujeres')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['type'], 'clarification')

    def test_home_only_exposes_widget_to_administration_and_supervision(self):
        from types import SimpleNamespace
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        template = Environment(loader=FileSystemLoader('app/templates'),
            autoescape=select_autoescape(['html'])).get_template('ui/home.html')
        for role in ('admin', 'supervisor', 'user', 'viewer'):
            with self.subTest(role=role):
                html = template.render(request=SimpleNamespace(url=SimpleNamespace(path='/ui/'), session={}),
                    current_user=SimpleNamespace(username='Prueba', role=role), phase2_expediente_enabled=True)
                self.assertEqual('data-farogpt' in html, role in ('admin', 'supervisor'))
                self.assertIn('data-faro-home-slideshow', html)
                self.assertIn('Accesos rápidos', html)
