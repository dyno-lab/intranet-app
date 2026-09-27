"""The live number preview is read-only; only saving allocates a unique number."""
import unittest
from datetime import date
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import test_community_routes as fixture
from app.core.config import settings
from app.models.community import CPParticipant, CPSequence


class CommunityNumberPreviewTests(unittest.TestCase):
    setUp = fixture.CommunityRouteTests.setUp
    tearDown = fixture.CommunityRouteTests.tearDown
    login = fixture.CommunityRouteTests.login
    token = fixture.CommunityRouteTests.token
    participant_data = fixture.CommunityRouteTests.participant_data

    def preview(self, year=2026):
        return self.client.get('/community/participants/next-number', params={'exp_year': year})

    def test_repeated_preview_and_form_render_do_not_allocate_numbers(self):
        self.login(self.user_id)
        for _ in range(3):
            response = self.preview()
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {'exp_year': 2026, 'expediente_num': 'CP-2026-0001'})
            self.assertIn('no-store', response.headers['cache-control'])
        page = self.client.get('/community/participants')
        self.assertIn(f'value="CP-{date.today().year}-0001"', page.text)
        self.assertIn('Próximo expediente', page.text)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPSequence)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(CPParticipant)), 0)

    def test_saving_advances_preview_for_all_employees_and_preserves_other_year(self):
        admin_token = self.login()
        self.assertEqual(self.preview().json()['expediente_num'], 'CP-2026-0001')
        created = self.client.post('/community/participants', data=self.participant_data(
            admin_token, nombre='Empleado primero', program_ids=[self.icp_id]))
        self.assertEqual(created.status_code, 303, created.text)
        user_token = self.login(self.user_id)
        self.assertEqual(self.preview().json()['expediente_num'], 'CP-2026-0002')
        self.assertEqual(self.preview(2027).json()['expediente_num'], 'CP-2027-0001')
        created = self.client.post('/community/participants', data=self.participant_data(
            user_token, nombre='Empleado segundo', expediente_num='CP-2026-0001', exp_sequence='1'))
        self.assertEqual(created.status_code, 303, created.text)
        with Session(self.engine) as db:
            self.assertEqual(set(db.scalars(select(CPParticipant.expediente_num))),
                             {'CP-2026-0001', 'CP-2026-0002'})

    def test_validation_failure_and_duplicate_warning_do_not_consume_preview(self):
        token = self.login()
        data = self.participant_data(token)
        bad = self.client.post('/community/participants', data={**data, 'telefono': 'invalid'})
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(self.preview().json()['expediente_num'], 'CP-2026-0001')
        self.assertEqual(self.client.post('/community/participants', data=data).status_code, 303)
        duplicate = self.client.post('/community/participants', data=data)
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.context['duplicate_matches'])
        self.assertEqual(self.preview().json()['expediente_num'], 'CP-2026-0002')

    def test_preview_never_reuses_deleted_record_number(self):
        token = self.login()
        self.client.post('/community/participants', data=self.participant_data(token))
        with Session(self.engine) as db:
            pid = db.scalar(select(CPParticipant.participant_id))
        response = self.client.post(f'/community/participants/{pid}/delete', data={'token': token})
        self.assertEqual(response.status_code, 303)
        with Session(self.engine) as db:
            self.assertIsNone(db.get(CPParticipant, pid))
        self.assertEqual(self.preview().json()['expediente_num'], 'CP-2026-0002')

    def test_exhaustion_returns_no_number_instead_of_overflowing_four_digits(self):
        self.login()
        year = date.today().year
        with Session(self.engine) as db:
            db.add(CPSequence(exp_year=year, last_value=9999))
            db.commit()
        self.assertEqual(self.preview(year).json(), {'exp_year': year, 'expediente_num': None})
        self.assertIn('Numeración agotada', self.client.get('/community/participants').text)
        self.assertEqual(self.preview(year + 1).json()['expediente_num'], f'CP-{year + 1}-0001')

    def test_invalid_years_and_access_checks(self):
        self.login()
        for year in ('bad', 999, 10000, '2026.5'):
            with self.subTest(year=year):
                self.assertEqual(self.preview(year).status_code, 422)
        self.assertEqual(self.client.get('/community/participants/next-number').status_code, 422)
        self.login(self.viewer_id)
        self.assertEqual(self.preview().status_code, 403)
        self.client.get(f'/_test/session/{self.denied_id}')
        self.assertEqual(self.preview().status_code, 403)
        with patch.object(settings, 'COMMUNITY_ENABLED', False):
            self.assertEqual(self.preview().status_code, 404)

    def test_invalid_form_year_keeps_validation_error_without_preview_failure(self):
        token = self.login()
        response = self.client.post('/community/participants', data=self.participant_data(token, exp_year='bad'))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.context['form_error'])
        self.assertIn('Seleccione un año válido', response.text)
