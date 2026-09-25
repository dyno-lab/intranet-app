"""Only Community Admin/Supervisor may remove records with no history."""
import unittest
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

import test_community_routes as fixture
from app.models.community import CPParticipant, CPParticipantProgram, CPProgram, CPUserAccess
from app.models.community_catalog import CPProfileField, CPProfileValue
from app.models.community_fiscal import CPFiscalParticipant
from app.models.community_identity import CPIdentityReview
from app.models.community_operations import CPAttendance, CPGradeItem
from app.models.participant import Participant
from app.services.community import create_fiscal_year, create_participant
from app.services.community_fiscal import sync_participants
from app.services.community_activity import create_activity
from app.services.community_operations import create_activity_session, create_grade_report
from urllib.parse import parse_qs, urlparse


class CommunityParticipantDeleteTests(unittest.TestCase):
    setUp = fixture.CommunityRouteTests.setUp
    tearDown = fixture.CommunityRouteTests.tearDown
    token = fixture.CommunityRouteTests.token
    login = fixture.CommunityRouteTests.login

    def create_record(self):
        with Session(self.engine) as db:
            participant = create_participant(db, actor_user_id=self.admin_id, exp_year=2026,
                program_ids=[self.voca_id, self.tanf_id],
                fields={'nombre': 'Persona', 'apellido_paterno': 'Prueba', 'genero': 'F'})
            field = db.scalar(select(CPProfileField))
            if field is None:
                field = CPProfileField(field_key='referencia', label='Referencia')
                db.add(field)
                db.flush()
            db.add(CPProfileValue(participant_id=participant.participant_id, field_id=field.field_id, value='Dato del expediente'))
            db.commit()
            return participant.participant_id, participant.expediente_num

    def assert_record_intact(self, participant_id):
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(CPParticipant, participant_id))
            self.assertEqual(len(db.scalars(select(CPParticipantProgram).where(CPParticipantProgram.participant_id == participant_id)).all()), 2)
            self.assertIsNotNone(db.scalar(select(CPProfileValue).where(CPProfileValue.participant_id == participant_id)))

    def test_admin_and_supervisor_delete_unused_record_without_reusing_number(self):
        for role in ('admin', 'supervisor'):
            with self.subTest(role=role):
                with Session(self.engine) as db:
                    db.get(CPUserAccess, self.admin_id).role = role
                    db.commit()
                pid, number = self.create_record()
                token = self.login()
                path = f'/community/participants/{pid}/delete'
                self.assertIn(f'action="{path}"', self.client.get('/community/participants').text)
                response = self.client.post(path, data={'token': token})
                self.assertEqual(response.status_code, 303)
                self.assertNotIn('error=', response.headers['location'])
                with Session(self.engine) as db:
                    self.assertIsNone(db.get(CPParticipant, pid))
                    self.assertIsNone(db.scalar(select(CPParticipantProgram).where(CPParticipantProgram.participant_id == pid)))
                    self.assertIsNone(db.scalar(select(CPProfileValue).where(CPProfileValue.participant_id == pid)))
                    self.assertIsNotNone(db.get(CPProgram, self.voca_id))
                _, next_number = self.create_record()
                self.assertGreater(int(next_number.rsplit('-', 1)[1]), int(number.rsplit('-', 1)[1]))

    def test_user_and_viewer_cannot_delete_even_if_faro_role_is_admin(self):
        pid, _ = self.create_record()
        path = f'/community/participants/{pid}/delete'
        for user_id in (self.user_id, self.viewer_id):
            token = self.login(user_id)
            self.assertNotIn(f'action="{path}"', self.client.get('/community/participants').text)
            self.assertEqual(self.client.post(path, data={'token': token}).status_code, 403)
            self.assert_record_intact(pid)

    def test_csrf_and_program_context_are_checked_before_deletion(self):
        pid, _ = self.create_record()
        path = f'/community/participants/{pid}/delete'
        token = self.login()
        self.assertEqual(self.client.post(path, data={'token': 'incorrect'}).status_code, 403)
        self.assert_record_intact(pid)
        token = self.login(program=str(self.icp_id))
        self.assertEqual(self.client.post(path, data={'token': token}).status_code, 404)
        token = self.login(program=str(self.voca_id))
        response = self.client.post(path, data={'token': token})
        self.assertIn('error=', response.headers['location'])
        self.assert_record_intact(pid)

    def test_fiscal_snapshot_blocks_deletion_even_without_attendance(self):
        pid, _ = self.create_record()
        with Session(self.engine) as db:
            year = create_fiscal_year(db, 'FY24', 'Fiscal', date(2024, 1, 1), date(2024, 12, 31))
            sync_participants(db, year.fiscal_year_id, [pid], actor_user_id=self.admin_id)
            year.status = 'closed'
            db.commit()
            year_id = year.fiscal_year_id
        token = self.login()
        response = self.client.post(f'/community/participants/{pid}/delete', data={'token': token})
        self.assertEqual(response.status_code, 303)
        self.assertIn('error=', response.headers['location'])
        self.assert_record_intact(pid)
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(CPFiscalParticipant, (pid, year_id)))

    def test_both_confirmed_and_rejected_faro_reviews_are_preserved(self):
        for same_person in (True, False):
            pid, _ = self.create_record()
            with Session(self.engine) as db:
                faro = Participant(expediente_num=f'FE-2026-TEST-{pid:04d}', nombre='Persona', apellido_paterno='Faro')
                db.add(faro)
                db.flush()
                db.add(CPIdentityReview(cp_participant_id=pid, faro_participant_id=faro.participant_id,
                    is_same_person=same_person, reviewed_from='community', reviewed_by_user_id=self.admin_id))
                db.commit()
                faro_id = faro.participant_id
            token = self.login()
            response = self.client.post(f'/community/participants/{pid}/delete', data={'token': token})
            self.assertIn('error=', response.headers['location'])
            self.assert_record_intact(pid)
            with Session(self.engine) as db:
                self.assertIsNotNone(db.get(Participant, faro_id))
                self.assertIsNotNone(db.scalar(select(CPIdentityReview).where(CPIdentityReview.cp_participant_id == pid)))

    def test_legacy_attendance_and_grades_block_deletion_without_fiscal_copy(self):
        for kind in ('asistencias', 'notas escolares'):
            with self.subTest(kind=kind):
                pid, _ = self.create_record()
                with Session(self.engine) as db:
                    year = create_fiscal_year(db, f'FY{pid}', 'Fiscal', date(2024, 1, 1), date(2024, 12, 31))
                    if kind == 'asistencias':
                        activity = create_activity(db, program_id=self.voca_id, code=f'ACT{pid}',
                            description='Actividad de prueba', fiscal_year_ids=[year.fiscal_year_id])
                        session = create_activity_session(db, fiscal_year_id=year.fiscal_year_id,
                            program_id=self.voca_id, activity_id=activity.activity_id,
                            session_date=date(2024, 2, 1), actor_user_id=self.admin_id)
                        db.add(CPAttendance(session_id=session.session_id, participant_id=pid, is_present=False))
                    else:
                        report = create_grade_report(db, fiscal_year_id=year.fiscal_year_id, program_id=self.voca_id,
                            report_year=2024, report_month=2, actor_user_id=self.admin_id)
                        db.add(CPGradeItem(report_id=report.report_id, participant_id=pid, grade_level='8'))
                    db.commit()
                token = self.login()
                response = self.client.post(f'/community/participants/{pid}/delete', data={'token': token})
                self.assertEqual(response.status_code, 303)
                error = parse_qs(urlparse(response.headers['location']).query)['error'][0]
                self.assertIn(kind, error)
                self.assert_record_intact(pid)

    def test_unexpected_reference_rolls_back_profile_and_program_cleanup(self):
        pid, _ = self.create_record()
        with self.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE cp_test_reference (participant_id INTEGER REFERENCES cp_participants(participant_id))')
            conn.exec_driver_sql('INSERT INTO cp_test_reference (participant_id) VALUES (?)', (pid,))
        token = self.login()
        response = self.client.post(f'/community/participants/{pid}/delete', data={'token': token})
        self.assertEqual(response.status_code, 303)
        self.assertIn('error=', response.headers['location'])
        self.assert_record_intact(pid)


if __name__ == '__main__':
    unittest.main()
