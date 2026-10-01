"""Public registration paths must confirm exact cross-module matches before inserting."""
from datetime import date
import re
import unittest
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from fastapi import Depends

import test_community_routes as fixture
from app.core.config import settings
from app.models.community import CPParticipant, CPSequence
from app.models.community_identity import CPIdentityReview, CPIdentityReviewEvent
from app.models.participant import Participant
from app.models.residential import Residential
from app.services.community_identity_registration import prepare_registration_identity
from app.services.community_identity import reopen_identity_review
from app.services.community import create_participant
from app.api.routes import ui
from app.core.residential_scope import require_faro_access
from app.models.base import Base
from app.models.catalog_type import CatalogType
from app.models.catalog_option import CatalogOption
from app.models.participant_profile_field import ParticipantProfileField
from app.models.participant_profile_field_value import ParticipantProfileFieldValue
from app.models.platform_permission import PlatformPermission
from app.models.user_platform_permission import UserPlatformPermission


class IdentityRegistrationTests(unittest.TestCase):
    login = fixture.CommunityRouteTests.login
    token = fixture.CommunityRouteTests.token
    participant_data = fixture.CommunityRouteTests.participant_data

    def setUp(self):
        fixture.CommunityRouteTests.setUp(self)
        self.addCleanup(fixture.CommunityRouteTests.tearDown, self)
        with Session(self.engine) as db:
            residential = Residential(code='ZZ', name='Residencial privado', municipality='Ponce', rq_code='TEST', is_active=True)
            db.add(residential)
            db.flush()
            faro = Participant(expediente_num='FE-2026-ZZ-0001', residential_id=residential.residential_id,
                nombre='  ANA ', apellido_paterno='Rívera', apellido_materno='Distinto',
                fecha_nacimiento=date(2000, 5, 12), genero='F', edificio='NO-REVELAR', apart='NO-REVELAR')
            db.add(faro)
            db.commit()
            self.faro_id = faro.participant_id
            self.residential_id = residential.residential_id
        self.csrf = self.login()
        self.data = self.participant_data(self.csrf)

    def post(self, **changes):
        return self.client.post('/community/participants', data={**self.data, **changes})

    def confirmation(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        match = re.search(r'name="identity_confirmation" value="([^"]+)"', response.text)
        self.assertIsNotNone(match, response.text[:3000])
        return match.group(1)

    def test_exact_match_prompts_before_creating_or_consuming_number_and_preserves_fields(self):
        page = self.post(direccion_fisica='Dirección conservada')
        self.confirmation(page)
        self.assertIn('identity-registration-dialog', page.text)
        self.assertIn('gacosta@csifpr.org', page.text)
        self.assertIn('FE-2026-ZZ-0001', page.text)
        self.assertIn('Dirección conservada', page.text)
        self.assertNotIn('NO-REVELAR', page.text)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPParticipant)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(CPSequence)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(CPIdentityReview)), 0)

    def test_yes_saves_one_link_and_keeps_faro_unchanged(self):
        proof = self.confirmation(self.post())
        response = self.post(identity_confirmation=proof, identity_decision='yes', identity_candidate_id=self.faro_id)
        self.assertEqual(response.status_code, 303, response.text)
        with Session(self.engine) as db:
            person = db.scalar(select(CPParticipant))
            review = db.scalar(select(CPIdentityReview))
            self.assertEqual(person.expediente_num, 'CP-2026-0001')
            self.assertTrue(review.is_same_person)
            self.assertEqual(review.cp_participant_id, person.participant_id)
            self.assertEqual(review.faro_participant_id, self.faro_id)
            self.assertEqual(review.reviewed_by_user_id, self.admin_id)
            self.assertEqual(db.get(Participant, self.faro_id).apellido_materno, 'Distinto')
            self.assertEqual(db.get(Participant, self.faro_id).edificio, 'NO-REVELAR')
        roster = self.client.get('/community/participants')
        table = roster.text.split('id="participants-table-card"', 1)[1]
        self.assertEqual(table.count('Vinculado con Faro'), 1)
        self.assertNotIn('FE-2026-ZZ-0001', table)
        with Session(self.engine) as db:
            review = db.scalar(select(CPIdentityReview))
            reopen_identity_review(db, 'community', review.cp_participant_id, review.id,
                review.revision, self.admin_id, 'Confirmación incorrecta')
            db.commit()
        self.assertNotIn('Vinculado con Faro', self.client.get('/community/participants').text)

    def test_cancel_keeps_form_without_creating(self):
        proof = self.confirmation(self.post())
        response = self.post(identity_confirmation=proof, identity_action='edit')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('id="identity-registration-dialog"', response.text)
        self.assertIn('value="Ana"', response.text)
        with Session(self.engine) as db:
            self.assertIsNone(db.scalar(select(CPParticipant)))

    def test_no_saves_audited_rejection_without_a_confirmed_link(self):
        proof = self.confirmation(self.post())
        response = self.post(identity_confirmation=proof, identity_decision='no')
        self.assertEqual(response.status_code, 303)
        with Session(self.engine) as db:
            self.assertFalse(db.scalar(select(CPIdentityReview)).is_same_person)
            self.assertFalse(db.scalar(select(CPIdentityReviewEvent)).decision)
        self.assertNotIn('Vinculado con Faro', self.client.get('/community/participants').text)

    def test_pending_saves_and_expediente_offers_review(self):
        proof = self.confirmation(self.post())
        response = self.post(identity_confirmation=proof, identity_decision='pending')
        self.assertEqual(response.status_code, 303)
        page = self.client.get(response.headers['location'])
        self.assertIn('Revisar coincidencias con Faro', page.text)
        self.assertNotIn('Vinculado con Faro', self.client.get('/community/participants').text)
        with Session(self.engine) as db:
            self.assertIsNone(db.scalar(select(CPIdentityReview)))

    def test_multiple_candidates_require_explicit_choice(self):
        with Session(self.engine) as db:
            person = Participant(expediente_num='FE-2026-ZZ-0002', residential_id=self.residential_id,
                nombre='Ana', apellido_paterno='Rivera', fecha_nacimiento=date(2000, 5, 12), genero='F')
            db.add(person)
            db.commit()
            second_id = person.participant_id
        page = self.post()
        proof = self.confirmation(page)
        for radio in re.findall(r'<input[^>]+name="identity_candidate_id"[^>]*>', page.text):
            self.assertNotIn('checked', radio)
        self.confirmation(self.post(identity_confirmation=proof, identity_decision='yes'))
        response = self.post(identity_confirmation=proof, identity_decision='yes', identity_candidate_id=second_id)
        self.assertEqual(response.status_code, 303)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(CPIdentityReview)).faro_participant_id, second_id)

    def test_candidate_linked_by_other_employee_invalidates_old_proof(self):
        proof = self.confirmation(self.post())
        with Session(self.engine) as db:
            cp = create_participant(db, actor_user_id=self.admin_id, exp_year=2026, program_ids=[self.voca_id],
                fields={'nombre': 'Otra', 'apellido_paterno': 'Persona', 'genero': 'F'})
            db.add(CPIdentityReview(cp_participant_id=cp.participant_id, faro_participant_id=self.faro_id,
                is_same_person=True, reviewed_from='faro', reviewed_by_user_id=self.admin_id))
            db.commit()
        page = self.post(identity_confirmation=proof, identity_decision='yes', identity_candidate_id=self.faro_id)
        new_proof = self.confirmation(page)
        self.assertIn('Ya tiene un vínculo confirmado', page.text)
        self.confirmation(self.post(identity_confirmation=new_proof, identity_decision='yes', identity_candidate_id=self.faro_id))
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPParticipant)), 1)

    def test_expired_or_other_session_proof_cannot_confirm(self):
        proof = self.confirmation(self.post())
        import time
        with patch('itsdangerous.timed.time.time', return_value=time.time() + 901):
            self.confirmation(self.post(identity_confirmation=proof, identity_decision='yes', identity_candidate_id=self.faro_id))
        self.data['token'] = self.login()
        self.confirmation(self.post(identity_confirmation=proof, identity_decision='yes', identity_candidate_id=self.faro_id))
        with Session(self.engine) as db:
            self.assertIsNone(db.scalar(select(CPParticipant)))

    def test_failure_saving_link_rolls_back_participant_programs_and_sequence(self):
        proof = self.confirmation(self.post())
        from app.api.routes import community
        from sqlalchemy.exc import IntegrityError
        with patch.object(community, 'save_registration_identity', side_effect=IntegrityError('test', {}, Exception('conflict'))):
            response = self.post(identity_confirmation=proof, identity_decision='yes', identity_candidate_id=self.faro_id)
        self.assertEqual(response.status_code, 200)
        with Session(self.engine) as db:
            self.assertIsNone(db.scalar(select(CPParticipant)))
            self.assertIsNone(db.scalar(select(CPSequence)))

    def test_no_longer_matching_candidate_does_not_silently_save_confirmation(self):
        proof = self.confirmation(self.post())
        response = self.post(identity_confirmation=proof, identity_decision='yes', identity_candidate_id=self.faro_id, nombre='María')
        self.assertEqual(response.status_code, 200)
        self.assertIn('dejó de corresponder', response.text)
        with Session(self.engine) as db:
            self.assertIsNone(db.scalar(select(CPParticipant)))

    def test_local_duplicate_confirmation_survives_cross_module_prompt(self):
        with Session(self.engine) as db:
            create_participant(db, actor_user_id=self.admin_id, exp_year=2026, program_ids=[self.voca_id],
                fields={'nombre': 'Ana', 'apellido_paterno': 'Rivera', 'fecha_nacimiento': '2000-05-12', 'genero': 'F'})
            db.commit()
        local = self.post()
        duplicate = re.search(r'name="duplicate_confirmation" value="([^"]+)"', local.text).group(1)
        page = self.post(duplicate_confirmation=duplicate)
        proof = self.confirmation(page)
        self.assertIn(f'type="hidden" name="duplicate_confirmation" value="{duplicate}"', page.text)
        result = self.post(duplicate_confirmation=duplicate, identity_confirmation=proof,
            identity_decision='yes', identity_candidate_id=self.faro_id)
        self.assertEqual(result.status_code, 303)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPParticipant)), 2)

    def test_approximate_name_does_not_interrupt_creation(self):
        response = self.post(nombre='Anna')
        self.assertEqual(response.status_code, 303)
        self.assertNotIn('/identity', response.headers['location'])
        with Session(self.engine) as db:
            self.assertIsNotNone(db.scalar(select(CPParticipant)))
            self.assertIsNone(db.scalar(select(CPIdentityReview)))

    def test_changed_demographics_forged_id_or_stale_candidate_requires_confirmation(self):
        proof = self.confirmation(self.post())
        self.confirmation(self.post(identity_confirmation=proof, identity_decision='yes', identity_candidate_id=999))
        self.confirmation(self.post(identity_confirmation=proof, identity_decision='yes',
            identity_candidate_id=self.faro_id, apellido_materno='Cambio visible'))
        with Session(self.engine) as db:
            db.get(Participant, self.faro_id).apellido_materno = 'Actualizado'
            db.commit()
        self.confirmation(self.post(identity_confirmation=proof, identity_decision='yes', identity_candidate_id=self.faro_id))
        with Session(self.engine) as db:
            self.assertIsNone(db.scalar(select(CPParticipant)))

    def test_disabled_gate_uses_no_database(self):
        with patch.object(settings, 'COMMUNITY_ENABLED', False):
            self.assertEqual(prepare_registration_identity(None, 'faro', {}, {}, actor_user_id=1, csrf='test'), (None, None))


class FaroIdentityRegistrationTests(unittest.TestCase):
    login = fixture.CommunityRouteTests.login
    token = fixture.CommunityRouteTests.token
    confirmation = IdentityRegistrationTests.confirmation

    def setUp(self):
        fixture.CommunityRouteTests.setUp(self)
        self.addCleanup(fixture.CommunityRouteTests.tearDown, self)
        Base.metadata.create_all(self.engine, tables=[model.__table__ for model in
            (CatalogType, CatalogOption, ParticipantProfileField, ParticipantProfileFieldValue)])
        self.app.include_router(ui.router, prefix='/ui', dependencies=[Depends(require_faro_access)])
        # Only the unrelated proposal dashboard is stubbed; form rendering,
        # access checks, matching and both records use the real database paths.
        dashboard = patch.object(ui, '_build_new_list_dashboard', return_value={
            'totals': {'registered_count': 0, 'assigned_count': 0, 'pending_sync_count': 0},
            'show_residential_breakdown': False})
        dashboard.start()
        self.addCleanup(dashboard.stop)
        phase = patch.object(settings, 'PHASE2_EXPEDIENTE_ENABLED', True)
        phase.start()
        self.addCleanup(phase.stop)
        with Session(self.engine) as db:
            residential = Residential(code='ZZ', name='Prueba', municipality='Ponce', rq_code='TEST')
            db.add(residential)
            permission = PlatformPermission(key='access_faro', name='Faro')
            db.add(permission)
            db.flush()
            self.residential_id = residential.residential_id
            db.add(UserPlatformPermission(user_id=self.admin_id, permission_id=permission.permission_id))
            cp = create_participant(db, actor_user_id=self.admin_id, exp_year=2026, program_ids=[self.voca_id],
                fields={'nombre': 'Ana', 'apellido_paterno': 'Rivera', 'apellido_materno': 'Soto',
                        'fecha_nacimiento': '2000-05-12', 'genero': 'F', 'direccion_fisica': 'NO-REVELAR'})
            self.cp_id = cp.participant_id
            db.commit()
        self.csrf = self.login()
        self.data = {'token': self.csrf, 'residential_id': self.residential_id, 'exp_year': '2026',
            'exp_seq4': '0001', 'nombre': 'Ana', 'apellido_paterno': 'Rivera', 'apellido_materno': 'Distinto',
            'fecha_nacimiento': '2000-05-12', 'genero': 'F', 'edificio': '12', 'apart': '3', 'primera_vez': 'SI'}

    def post(self, **changes):
        return self.client.post('/ui/new-list/create', data={**self.data, **changes})

    def test_faro_prompt_preserves_form_and_confirms_reverse_link(self):
        page = self.post()
        proof = self.confirmation(page)
        self.assertIn('eyrivera@csifpr.org', page.text)
        self.assertIn('CP-2026-0001', page.text)
        self.assertNotIn('NO-REVELAR', page.text)
        self.assertIn('name="edificio" value="12"', page.text)
        self.assertIn('value="SI" selected', page.text)
        with Session(self.engine) as db:
            self.assertIsNone(db.scalar(select(Participant)))
        result = self.post(identity_confirmation=proof, identity_decision='yes', identity_candidate_id=self.cp_id)
        self.assertEqual(result.status_code, 303, result.text)
        with Session(self.engine) as db:
            faro = db.scalar(select(Participant))
            review = db.scalar(select(CPIdentityReview))
            self.assertEqual(faro.expediente_num, 'FE-2026-ZZ-0001')
            self.assertTrue(review.is_same_person)
            self.assertEqual(review.cp_participant_id, self.cp_id)
            self.assertEqual(review.faro_participant_id, faro.participant_id)
            self.assertEqual(review.reviewed_from, 'faro')
            self.assertEqual(db.get(CPParticipant, self.cp_id).direccion_fisica, 'NO-REVELAR')
        roster = self.client.get('/ui/new-list', params={'residential_id': self.residential_id})
        table = roster.text.split('id="participants-table-card"', 1)[1]
        self.assertEqual(table.count('Vinculado con Comunidad'), 1)
        self.assertNotIn('CP-2026-0001', table)
        with patch.object(settings, 'COMMUNITY_ENABLED', False):
            self.assertNotIn('Vinculado con Comunidad', self.client.get('/ui/new-list').text)
        with Session(self.engine) as db:
            review = db.scalar(select(CPIdentityReview))
            reopen_identity_review(db, 'faro', review.faro_participant_id, review.id,
                review.revision, self.admin_id, 'Confirmación incorrecta')
            db.commit()
        self.assertNotIn('Vinculado con Comunidad', self.client.get('/ui/new-list').text)

    def test_faro_cancel_and_pending(self):
        proof = self.confirmation(self.post())
        cancelled = self.post(identity_confirmation=proof, identity_action='edit')
        self.assertNotIn('id="identity-registration-dialog"', cancelled.text)
        self.assertIn('name="nombre" value="Ana"', cancelled.text)
        result = self.post(identity_confirmation=proof, identity_decision='pending')
        self.assertEqual(result.status_code, 303)
        self.assertNotIn('community-identity', result.headers['location'])
        self.assertNotIn('Vinculado con Comunidad', self.client.get('/ui/new-list').text)
        with Session(self.engine) as db:
            self.assertIsNotNone(db.scalar(select(Participant)))
            self.assertIsNone(db.scalar(select(CPIdentityReview)))

    def test_faro_number_used_while_dialog_open_keeps_entered_data(self):
        proof = self.confirmation(self.post())
        with Session(self.engine) as db:
            db.add(Participant(expediente_num='FE-2026-ZZ-0001', residential_id=self.residential_id,
                exp_year=2026, exp_seq4='0001', nombre='Otra', apellido_paterno='Persona', genero='F'))
            db.commit()
        response = self.post(identity_confirmation=proof, identity_decision='yes', identity_candidate_id=self.cp_id)
        self.assertEqual(response.status_code, 200)
        self.assertIn('sus datos se conservaron', response.text)
        self.assertIn('name="nombre" value="Ana"', response.text)
        self.assertIn('name="edificio" value="12"', response.text)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Participant)), 1)
            self.assertIsNone(db.scalar(select(CPIdentityReview)))

    def test_faro_reject_csrf_and_unauthorized_user_before_matching(self):
        self.assertEqual(self.post(token='bad').status_code, 403)
        self.login(self.user_id)
        self.assertEqual(self.post().status_code, 403)
        with Session(self.engine) as db:
            self.assertIsNone(db.scalar(select(Participant)))

    def test_disabled_community_leaves_faro_creation_available(self):
        with patch.object(settings, 'COMMUNITY_ENABLED', False):
            response = self.post(token='')
        self.assertEqual(response.status_code, 303, response.text)
        with Session(self.engine) as db:
            self.assertIsNotNone(db.scalar(select(Participant)))
            self.assertIsNone(db.scalar(select(CPIdentityReview)))
