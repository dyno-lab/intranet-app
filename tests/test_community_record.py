"""Participant record navigation, program additions and scoped attendance history."""
import unittest
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import test_community_routes as fixture
from app.models.community import CPParticipant, CPParticipantProgram
from app.services.community import create_fiscal_year, create_participant
from app.services.community_activity import create_activity
from app.services.community_fiscal import sync_participants, enroll_participant, discharge_participant, set_fiscal_status
from app.services.community_operations import create_activity_session, set_session_attendance


class CommunityRecordTests(unittest.TestCase):
    setUp = fixture.CommunityRouteTests.setUp
    tearDown = fixture.CommunityRouteTests.tearDown
    token = fixture.CommunityRouteTests.token
    login = fixture.CommunityRouteTests.login

    def seed(self, only_voca=False):
        with Session(self.engine) as db:
            p = create_participant(db, actor_user_id=self.admin_id, exp_year=2026,
                program_ids=[self.voca_id] if only_voca else [self.voca_id, self.tanf_id, self.icp_id],
                fields={'nombre': 'Ana', 'apellido_paterno': 'Prueba', 'genero': 'F',
                        'direccion_fisica': 'Dirección de prueba', 'pueblo': 'Ponce'})
            year = create_fiscal_year(db, '2025', 'Año de prueba', date(2025, 1, 1), date(2025, 12, 31))
            sync_participants(db, year.fiscal_year_id, [p.participant_id], actor_user_id=self.admin_id)
            self.sessions = []
            for month, program_id in enumerate([self.voca_id] if only_voca else [self.voca_id, self.tanf_id, self.icp_id], 1):
                activity = create_activity(db, program_id=program_id, code=f'TALLER-{month}',
                    description=f'Actividad de prueba {month}', fiscal_year_ids=[year.fiscal_year_id])
                enroll_participant(db, participant_id=p.participant_id, program_id=program_id,
                    fiscal_year_id=year.fiscal_year_id, start_date=date(2025, 1, 1), actor_user_id=self.admin_id)
                session = create_activity_session(db, fiscal_year_id=year.fiscal_year_id, program_id=program_id,
                    activity_id=activity.activity_id, session_date=date(2025, month, 10), actor_user_id=self.admin_id)
                set_session_attendance(db, session_id=session.session_id, present_participant_ids=[p.participant_id])
                self.sessions.append(session.session_id)
                if month == 1:
                    absent = create_activity_session(db, fiscal_year_id=year.fiscal_year_id, program_id=program_id,
                        activity_id=activity.activity_id, session_date=date(2025, 1, 11), actor_user_id=self.admin_id)
                    set_session_attendance(db, session_id=absent.session_id, present_participant_ids=[])
                    self.activity_id = activity.activity_id
            db.commit()
            self.pid, self.year_id, self.number = p.participant_id, year.fiscal_year_id, p.expediente_num
        self.path = f'/community/participants/{self.pid}'

    def test_add_program_from_record_preserves_number_and_existing_history(self):
        self.seed(only_voca=True)
        token = self.login(self.user_id)
        page = self.client.get(self.path)
        self.assertIn('Añadir programa', page.text)
        self.assertEqual([p.program_id for p in page.context['available_programs']], [self.tanf_id])
        result = self.client.post(self.path + '/programs', data={'token': token, 'program_ids': [self.tanf_id]})
        self.assertEqual(result.status_code, 303)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPParticipant)), 1)
            self.assertEqual(db.get(CPParticipant, self.pid).expediente_num, self.number)
            self.assertEqual(db.get(CPParticipantProgram, (self.pid, self.tanf_id)).record_number, 'CP-2026-TANF-M-0001')
        page = self.client.get(self.path)
        self.assertEqual(page.context['record']['participation_total'], 1)
        self.assertEqual(page.context['available_programs'], [])
        self.assertEqual(self.client.post(self.path + '/programs', data={'token': token, 'program_ids': [self.icp_id]}).status_code, 403)

    def test_detail_counts_confirmed_attendance_and_hides_other_programs(self):
        self.seed()
        self.login(self.user_id)
        page = self.client.get(self.path)
        self.assertEqual(page.status_code, 200, page.text)
        record = page.context['record']
        self.assertEqual(record['participation_total'], 2)
        self.assertEqual(record['last_participation_date'], date(2025, 2, 10))
        self.assertEqual(len(record['fiscal_years']), 1)
        self.assertEqual({row['program'].code for row in record['history_rows']}, {'VOCA', 'TANF-M'})
        self.assertNotIn('TALLER-3', page.text)
        self.assertNotIn('Programa ICP', page.text)
        self.assertNotIn('Editar participante', page.text)

    def test_filters_chart_and_pagination_have_the_same_scope(self):
        self.seed()
        self.login(self.user_id)
        params = {'fiscal_year_id': self.year_id, 'program_id': self.voca_id,
                  'from_date': '2025-01-10', 'to_date': '2025-01-10', 'activity': 'TALLER-1'}
        page = self.client.get(self.path, params=params)
        record = page.context['record']
        self.assertEqual(record['history_total'], 1)
        self.assertEqual(record['chart_total'], 1)
        self.assertEqual(record['chart_rows'][0]['value'], 1)
        self.assertEqual(record['history_rows'][0]['session'].session_id, self.sessions[0])
        self.assertEqual(record['participation_total'], 2)
        self.assertEqual(self.client.get(self.path, params={'program_id': self.icp_id}).status_code, 403)
        self.assertEqual(self.client.get(self.path, params={'from_date': '2025-02-01', 'to_date': '2025-01-01'}).status_code, 422)
        self.assertEqual(self.client.get(self.path, params={'fiscal_year_id': '9999'}).status_code, 404)

    def test_closed_year_and_program_discharge_keep_history_visible(self):
        self.seed()
        self.login(self.user_id)
        with Session(self.engine) as db:
            discharge_participant(db, participant_id=self.pid, program_id=self.tanf_id, fiscal_year_id=self.year_id,
                end_date=date(2025, 3, 1), actor_user_id=self.admin_id, reason='Baja de prueba')
            set_fiscal_status(db, self.year_id, closed=True, actor_user_id=self.admin_id)
            db.commit()
        page = self.client.get(self.path, params={'fiscal_year_id': self.year_id})
        record = page.context['record']
        self.assertEqual(record['history_total'], 2)
        self.assertEqual(record['chart_total'], 2)
        states = {row['program'].code: row['status'] for row in record['fiscal_rows']}
        self.assertEqual(states['TANF-M'], 'Baja')
        self.assertEqual(states['VOCA'], 'Activo en este año')
        self.assertIn('Cerrado', page.text)

    def test_viewer_can_read_history_but_not_add_programs(self):
        self.seed(only_voca=True)
        token = self.login(self.viewer_id)
        page = self.client.get(self.path)
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('Añadir programa', page.text)
        self.assertNotIn('Editar participante', page.text)
        self.assertEqual(page.context['record']['history_total'], 1)
        self.assertEqual(self.client.post(self.path + '/programs', data={'token': token, 'program_ids': [self.tanf_id]}).status_code, 403)

    def test_history_pagination_keeps_program_and_date_filters(self):
        self.seed(only_voca=True)
        with Session(self.engine) as db:
            for day in range(1, 27):
                session = create_activity_session(db, fiscal_year_id=self.year_id, program_id=self.voca_id,
                    activity_id=self.activity_id, session_date=date(2025, 4, day), actor_user_id=self.admin_id)
                set_session_attendance(db, session_id=session.session_id, present_participant_ids=[self.pid])
            db.commit()
        self.login(self.user_id)
        page = self.client.get(self.path, params={'program_id': self.voca_id, 'from_date': '2025-04-01', 'history_page': 2})
        record = page.context['record']
        self.assertEqual(record['history_total'], 26)
        self.assertEqual(len(record['history_rows']), 1)
        self.assertEqual(record['history_page'], 2)
        self.assertIn(f'program_id={self.voca_id}', record['history_links']['first'])
        self.assertIn('from_date=2025-04-01', record['history_links']['first'])
