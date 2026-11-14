import unittest

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

    def test_csrf_and_session_required(self):
        response = self.client.post('/ui/farogpt/consulta', json={'question': 'participantes únicos septiembre 2026'})
        self.assertEqual(response.status_code, 403)
        self.client.cookies.clear()
        response = self.client.get('/ui/farogpt/inicio', follow_redirects=False)
        self.assertEqual(response.status_code, 303)

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
