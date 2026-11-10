import re
import unittest
from datetime import date
from unittest.mock import patch
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select

from tests import test_monthly_attendance as fixtures
from app.api.deps import get_db
from app.api.routes import monthly_attendance as routes, ui, sessions
from app.core.auth import get_current_user
from app.core.residential_scope import require_faro_access
from app.models.base import Base
from app.models.user_residential import UserResidential
from app.models.monthly_attendance import AttendanceMonthResidential, AttendanceMonthEvent
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.proposal import Proposal
from app.services.monthly_attendance import build_month, confirm_month


class MonthlyAttendanceRouteTests(unittest.TestCase):
    def setUp(self):
        self.source = fixtures.MonthlyAttendanceTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.f = self.source.fixture
        self.db, self.actor = self.f.db, self.f.actor
        Base.metadata.create_all(self.f.engine, tables=[UserResidential.__table__])
        self.db.add(UserResidential(user_id=self.actor.user_id, residential_id=self.f.a.residential_id))
        self.db.commit()
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key='monthly-test-only')
        app.include_router(routes.router)
        app.include_router(ui.router, prefix='/ui', dependencies=[Depends(require_faro_access)])
        app.include_router(sessions.router, prefix='/sessions', dependencies=[Depends(require_faro_access)])
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: self.actor
        permission = patch('app.core.residential_scope._FARO_PERMISSION_DEPENDENCY', return_value=self.actor)
        permission.start()
        self.addCleanup(permission.stop)
        @app.get('/test/context/{rid}')
        def context(request: Request, rid: int):
            request.session.clear()
            if rid:
                request.session['active_residential_id'] = rid
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.url = f'/ui/monthly-attendance?proposal_id={self.f.proposal.proposal_id}&year=2026&month=9'

    def prepare(self, scope=True):
        self.client.get(f'/test/context/{self.f.a.residential_id if scope else 0}')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.text)
        form = dict(proposal_id=self.f.proposal.proposal_id, year=2026, month=9, declared='on',
            csrf_token=re.search(r'name="csrf_token" value="([^"]+)"', response.text)[1])
        fingerprint = re.search(r'name="fingerprint" value="([^"]+)"', response.text)
        if fingerprint:
            form['fingerprint'] = fingerprint[1]
        return response, form

    def confirm(self):
        _, form = self.prepare()
        response = self.client.post('/ui/monthly-attendance/confirm', data=form, follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        return form

    def status(self, month=9, proposal_id=None):
        return build_month(self.db, self.source.user, proposal_id or self.f.proposal.proposal_id, 2026, month)['rows'][0]['status']

    def test_scoped_confirmation_ignores_forged_target_and_global_get_has_no_writes(self):
        page, _ = self.prepare(False)
        self.assertIn('Estado por residencial', page.text)
        self.assertEqual(self.db.scalars(select(AttendanceMonthEvent)).all(), [])
        self.actor.role = 'user'
        _, form = self.prepare()
        response = self.client.post('/ui/monthly-attendance/confirm', data={**form,
            'residential_id': self.f.b.residential_id, 'user_id': 999}, follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        rows = self.db.scalars(select(AttendanceMonthResidential)).all()
        self.assertEqual([r.residential_id for r in rows if r.confirmed_at], [self.f.a.residential_id])
        page = self.client.get(self.url)
        self.assertIn('Completado', page.text)
        self.assertNotIn('Destino', page.text)

    def test_csrf_role_and_context_revocation(self):
        _, form = self.prepare()
        self.assertEqual(self.client.post('/ui/monthly-attendance/confirm', data={**form, 'csrf_token': 'bad'}).status_code, 403)
        self.assertEqual(self.client.post('/ui/monthly-attendance/confirm', data={**form, 'csrf_token': 'ñ'}).status_code, 403)
        self.assertEqual(self.client.post('/ui/monthly-attendance/confirm', data={**form, 'fingerprint': 'ñ'}).status_code, 409)
        self.actor.role = 'viewer'
        self.assertEqual(self.client.post('/ui/monthly-attendance/confirm', data=form).status_code, 403)
        self.actor.role = 'user'
        self.db.query(UserResidential).update({UserResidential.is_active: False})
        self.db.commit()
        self.assertEqual(self.client.post('/ui/monthly-attendance/confirm', data=form, follow_redirects=False).status_code, 303)
        self.assertEqual(self.db.scalars(select(AttendanceMonthEvent)).all(), [])

    def test_blank_filters_and_invalid_periods(self):
        response = self.client.get('/ui/monthly-attendance?proposal_id=&month=&year=')
        self.assertEqual(response.status_code, 200, response.text)
        for suffix in ('month=0', 'month=13', 'year=1999', 'year=no'):
            self.assertIn(self.client.get('/ui/monthly-attendance?' + suffix).status_code, (409, 422))

    def test_replacing_clearing_deleting_and_creating_attendance_reopens(self):
        form = self.confirm()
        response = self.client.post(f'/ui/listado/{self.f.session.session_id}',
            data={'present': str(self.f.old.proposal_participant_id)}, follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(self.status(), 'review')
        self.confirm()
        response = self.client.post(f'/ui/listado/{self.f.session.session_id}/clear-attendance', follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(self.status(), 'review')
        self.confirm()
        response = self.client.post(f'/ui/listado/{self.f.session.session_id}/delete', follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(self.status(), 'review')
        self.assertEqual(self.db.scalars(select(Attendance)).all(), [])

    def test_ui_and_api_create_invalidate_empty_confirmed_month(self):
        for route in ('/ui/listado/create-session', '/sessions'):
            month = 8 if route.startswith('/ui') else 7
            data = build_month(self.db, self.source.user, self.f.proposal.proposal_id, 2026, month)
            confirm_month(self.db, self.source.user, proposal_id=self.f.proposal.proposal_id, year=2026,
                month=month, fingerprint=data['rows'][0]['fingerprint'], declared=True, no_activity=True, note='Sin actividad.')
            self.db.commit()
            self.prepare()
            payload = dict(session_date=f'2026-{month:02d}-15', proposal_id=self.f.proposal.proposal_id,
                           activity_code_id=self.f.code.activity_code_id, employee_id=self.f.employee.employee_id)
            response = self.client.post(route, **({'data': payload} if route.startswith('/ui') else {'json': payload}), follow_redirects=False)
            self.assertIn(response.status_code, (200, 303), response.text)
            self.assertEqual(self.status(month), 'review')

    def test_session_move_reopens_old_and_new_periods(self):
        self.confirm()
        data = build_month(self.db, self.source.user, self.f.proposal.proposal_id, 2026, 10)
        confirm_month(self.db, self.source.user, proposal_id=self.f.proposal.proposal_id, year=2026,
            month=10, fingerprint=data['rows'][0]['fingerprint'], declared=True, no_activity=True, note='Sin actividad.')
        self.db.commit()
        response = self.client.post(f'/ui/listado/{self.f.session.session_id}/edit', data={
            'session_date': '2026-10-01', 'activity_code_id': self.f.code.activity_code_id,
            'employee_id': self.f.employee.employee_id, 'proposal_id': self.f.proposal.proposal_id, 'hours_minutes': 60}, follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual((self.status(9), self.status(10)), ('review', 'review'))

    def test_failed_attendance_write_rolls_back_invalidation_and_notices(self):
        self.confirm()
        before = self.db.scalars(select(AttendanceMonthEvent)).all()
        with patch.object(self.db, 'commit', side_effect=RuntimeError('Synthetic commit failure')):
            with self.assertRaises(RuntimeError):
                self.client.post(f'/ui/listado/{self.f.session.session_id}/clear-attendance')
        self.db.rollback()  # get_db closes/rolls back failed requests in production.
        self.assertEqual(self.status(), 'done')
        self.assertEqual(len(self.db.scalars(select(AttendanceMonthEvent)).all()), len(before))
        self.assertEqual(len(self.db.scalars(select(Attendance)).all()), 1)

    def test_proposal_deletion_preserves_confirmation_audit(self):
        from app.api.routes import admin
        self.confirm()
        with patch.object(admin, 'verify_password', return_value=True):
            response = admin.admin_delete_proposal(self.f.proposal.proposal_id, admin_password='test',
                delete_confirmation='ELIMINAR', db=self.db, current_user=self.actor)
        self.assertEqual(response.status_code, 303)
        self.assertIn('seguimiento+mensual', response.headers['location'])
        self.assertIsNotNone(self.db.get(Proposal, self.f.proposal.proposal_id))

    def test_reminders_settings_and_escaped_notes(self):
        _, form = self.prepare(False)
        self.actor.role = 'supervisor'
        response = self.client.post('/ui/monthly-attendance/remind', data=form, follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(self.client.post('/ui/monthly-attendance/configure', data={**form,
            'revision': 0, 'due_on': '2026-10-12', 'residential_ids': self.f.a.residential_id, 'reason': 'Ajuste'}).status_code, 403)
        self.actor.role = 'admin'
        response = self.client.post('/ui/monthly-attendance/configure', data={**form,
            'revision': 0, 'due_on': '2026-10-12', 'residential_ids': self.f.a.residential_id,
            'reason': '<script>alert(1)</script>'}, follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        page = self.client.get(self.url)
        self.assertIn('&lt;script&gt;', page.text)
        self.assertNotIn('<script>alert(1)</script>', page.text)
