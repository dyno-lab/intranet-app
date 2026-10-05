"""Viewer reviews operational forms without gaining write or export access."""
import unittest
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import Session

from tests import test_community_routes as fixture
from app.models.community import CPParticipant, CPParticipantProgram
from app.services.community import create_participant


class CommunityViewerTests(unittest.TestCase):
    setUp = fixture.CommunityRouteTests.setUp
    tearDown = fixture.CommunityRouteTests.tearDown
    login = fixture.CommunityRouteTests.login
    token = fixture.CommunityRouteTests.token
    participant_data = fixture.CommunityRouteTests.participant_data

    def seed(self):
        with Session(self.engine) as db:
            person = create_participant(db, actor_user_id=self.admin_id, exp_year=2026,
                program_ids=[self.voca_id], fields={'nombre': 'Ana', 'apellido_paterno': 'Rivera', 'genero': 'F'})
            db.commit()
            return person.participant_id

    def test_operational_forms_are_visible_and_administration_stays_forbidden(self):
        pid = self.seed()
        token = self.login(self.viewer_id)
        for path in ['', '/participants', '/participants/new', '/participants/lookup',
                     f'/participants/{pid}', f'/participants/{pid}/edit',
                     f'/participants/{pid}/memberships', '/attendance', '/school-grades', '/reports']:
            with self.subTest(path=path):
                page = self.client.get('/community' + path)
                self.assertEqual(page.status_code, 200, page.text[:500])
                self.assertIn('community-viewer.js', page.text)
                self.assertNotIn('communitySidebarAdminNav', page.text)
        edit = self.client.get(f'/community/participants/{pid}/edit')
        self.assertIn('Guardar cambios', edit.text)
        self.assertIn('readonly', edit.text)
        self.assertIn('type="submit" disabled', edit.text)
        for path in ['programs', 'fiscal-years', 'fiscal-participants', 'activities', 'adm', 'catalogs']:
            self.assertEqual(self.client.get('/community/' + path).status_code, 403, path)
        self.assertEqual(self.client.post('/community/context', data={'token': token, 'program': self.voca_id}).status_code, 303)
        self.assertEqual(self.client.get('/community/participants').status_code, 200)

    def test_direct_posts_and_exports_are_denied_and_data_stays_intact(self):
        pid = self.seed()
        token = self.login(self.viewer_id)
        for path in ['/participants', f'/participants/{pid}/edit', f'/participants/{pid}/delete',
                     f'/participants/{pid}/programs', f'/participants/{pid}/memberships',
                     '/attendance', '/attendance/1/edit', '/attendance/1', '/attendance/1/delete',
                     '/school-grades', '/school-grades/1/participants', '/school-grades/1/delete']:
            with self.subTest(path=path):
                response = self.client.post('/community' + path, data=self.participant_data(token, nombre='Changed'))
                self.assertEqual(response.status_code, 403, response.text)
        for path in ['participants/export.csv', 'attendance/export.csv', 'attendance/export-attendance.csv']:
            self.assertEqual(self.client.get('/community/' + path).status_code, 403, path)
        with patch('app.api.routes.community_reports.build_report') as build:
            for output in ['screen', 'excel', 'pdf']:
                response = self.client.get('/community/reports', params={
                    'fiscal_year_id': 1, 'program_ids': self.voca_id, 'output': output})
                self.assertEqual(response.status_code, 403)
            build.assert_not_called()
        with Session(self.engine) as db:
            people = db.scalars(select(CPParticipant)).all()
            self.assertEqual([(p.participant_id, p.nombre) for p in people], [(pid, 'Ana')])
            self.assertEqual(len(db.scalars(select(CPParticipantProgram)).all()), 1)

    def test_user_still_cannot_edit_shared_demographics_and_admin_can(self):
        pid = self.seed()
        self.login(self.user_id)
        self.assertEqual(self.client.get(f'/community/participants/{pid}/edit').status_code, 403)
        self.login(self.admin_id)
        page = self.client.get(f'/community/participants/{pid}/edit')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('community-viewer.js', page.text)


if __name__ == '__main__':
    unittest.main()
