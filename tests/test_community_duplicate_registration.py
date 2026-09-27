"""Duplicate warnings require explicit confirmation before creating another record."""
import unittest
import time
from datetime import date
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import test_community_routes as fixture
from app.models.community import CPParticipant, CPSequence
from app.models.community_catalog import CPProfileField
from app.services.community import create_participant


class CommunityDuplicateRegistrationTests(unittest.TestCase):
    setUp = fixture.CommunityRouteTests.setUp
    tearDown = fixture.CommunityRouteTests.tearDown
    login = fixture.CommunityRouteTests.login
    token = fixture.CommunityRouteTests.token
    participant_data = fixture.CommunityRouteTests.participant_data

    def existing(self, **changes):
        fields = dict(nombre='Ana', apellido_paterno='Rivera', apellido_materno='Soto',
                      fecha_nacimiento=date(2000, 5, 12), genero='F', telefono='(787)-555-0110',
                      direccion_fisica='Direccion privada', email='privado@example.com')
        fields.update(changes)
        with Session(self.engine) as db:
            person = create_participant(db, actor_user_id=self.admin_id, exp_year=2026,
                                        program_ids=[self.icp_id], fields=fields)
            db.commit()
            return person.participant_id, person.expediente_num

    def count(self):
        with Session(self.engine) as db:
            return db.scalar(select(func.count()).select_from(CPParticipant))

    def test_warning_precedes_creation_and_preserves_values_across_programs(self):
        pid, number = self.existing(nombre='María Elena', apellido_paterno='Díaz')
        with Session(self.engine) as db:
            field = CPProfileField(field_key='contacto', label='Contacto familiar', field_type='text',
                                   is_required=False, is_active=True, sort_order=0)
            db.add(field)
            db.commit()
            profile_key = f'profile_{field.field_id}'
        token = self.login(self.user_id)
        data = self.participant_data(token, nombre='  MARIA   ELENA ', apellido_paterno=' DIAZ ',
                                     apellido_materno='Distinto', inicial='R', **{profile_key: 'Dato ingresado'})
        page = self.client.post('/community/participants', data=data)
        self.assertEqual(page.status_code, 200, page.text)
        self.assertEqual(self.count(), 1)
        self.assertEqual([row.participant_id for row in page.context['duplicate_matches']], [pid])
        self.assertIn(number, page.text)
        for private in ('Direccion privada', 'privado@example.com', '(787)-555-0110'):
            self.assertNotIn(private, page.text)
        self.assertEqual(page.context['values']['program_ids'], [self.voca_id, self.tanf_id])
        self.assertEqual(page.context['values'][profile_key], 'Dato ingresado')
        self.assertIn('id="participant-duplicate-dialog"', page.text)
        self.assertIn('Sí, crear otro expediente', page.text)
        with Session(self.engine) as db:
            self.assertEqual(db.get(CPSequence, 2026).last_value, 1)

    def test_explicit_confirmation_creates_another_record_once(self):
        self.existing()
        token = self.login()
        data = self.participant_data(token)
        page = self.client.post('/community/participants', data=data)
        confirmation = page.context['duplicate_confirmation']
        confirmed = self.client.post('/community/participants', data={**data, 'duplicate_confirmation': confirmation})
        self.assertEqual(confirmed.status_code, 303, confirmed.text)
        self.assertEqual(self.count(), 2)
        with Session(self.engine) as db:
            self.assertEqual(set(db.scalars(select(CPParticipant.expediente_num))), {'CP-2026-0001', 'CP-2026-0002'})
        replay = self.client.post('/community/participants', data={**data, 'duplicate_confirmation': confirmation})
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(len(replay.context['duplicate_matches']), 2)
        self.assertEqual(self.count(), 2)

    def test_revising_data_can_create_a_non_matching_person_without_confirmation(self):
        self.existing()
        token = self.login()
        data = self.participant_data(token)
        self.assertEqual(self.client.post('/community/participants', data=data).status_code, 200)
        for changed in ({'nombre': 'Otra'}, {'apellido_paterno': 'Otro'}, {'fecha_nacimiento': '2000-05-13'}):
            response = self.client.post('/community/participants', data={**data, **changed})
            self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(self.count(), 4)

    def test_missing_birth_date_does_not_infer_duplicate_and_invalid_date_is_rejected(self):
        self.existing(fecha_nacimiento=None)
        token = self.login()
        response = self.client.post('/community/participants', data=self.participant_data(token, fecha_nacimiento=''))
        self.assertEqual(response.status_code, 303, response.text)
        bad = self.client.post('/community/participants', data=self.participant_data(token, fecha_nacimiento='bad-date'))
        self.assertEqual(bad.status_code, 200)
        self.assertTrue(bad.context['form_error'])
        self.assertEqual(self.count(), 2)

    def test_review_and_expired_confirmation_keep_the_form_without_creating(self):
        self.existing()
        token = self.login()
        data = self.participant_data(token)
        page = self.client.post('/community/participants', data=data)
        confirmation = page.context['duplicate_confirmation']
        review = self.client.post('/community/participants', data={**data, 'duplicate_action': 'review'})
        self.assertEqual(review.status_code, 200)
        self.assertNotIn('id="participant-duplicate-dialog"', review.text)
        self.assertEqual(review.context['values']['nombre'], 'Ana')
        with patch('itsdangerous.timed.time.time', return_value=time.time() + 901):
            expired = self.client.post('/community/participants', data={**data, 'duplicate_confirmation': confirmation})
        self.assertEqual(expired.status_code, 200)
        self.assertTrue(expired.context['duplicate_matches'])
        self.assertEqual(self.count(), 1)

    def test_confirmation_cannot_be_forged_or_reused_for_another_identity_or_user(self):
        self.existing()
        self.existing(nombre='Beatriz')
        token = self.login()
        data = self.participant_data(token)
        page = self.client.post('/community/participants', data=data)
        confirmation = page.context['duplicate_confirmation']
        for changed in ({'duplicate_confirmation': 'yes'},
                        {'duplicate_confirmation': confirmation + 'tampered'},
                        {'duplicate_confirmation': confirmation, 'nombre': 'Beatriz'}):
            warning = self.client.post('/community/participants', data={**data, **changed})
            self.assertEqual(warning.status_code, 200)
            self.assertTrue(warning.context['duplicate_matches'])
        user_token = self.login(self.user_id)
        warning = self.client.post('/community/participants', data=self.participant_data(
            user_token, duplicate_confirmation=confirmation))
        self.assertEqual(warning.status_code, 200)
        self.assertEqual(self.count(), 2)

    def test_csrf_viewer_and_program_permissions_still_apply_before_warning(self):
        self.existing()
        token = self.login(self.user_id)
        for changed in ({'token': 'bad'}, {'program_ids': [self.icp_id]}):
            response = self.client.post('/community/participants', data={**self.participant_data(token), **changed})
            self.assertEqual(response.status_code, 403)
        viewer_token = self.login(self.viewer_id)
        response = self.client.post('/community/participants', data=self.participant_data(viewer_token))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.count(), 1)

    def test_lookup_matches_name_and_surnames_together_and_record_number(self):
        pid, number = self.existing()
        self.login(self.user_id)
        for term in ('Ana', 'Rivera', 'ANA RIVERA', 'Ana Rivera Soto', '  Rivera   Ana ', number):
            with self.subTest(term=term):
                page = self.client.get('/community/participants/lookup', params={'q': term})
                self.assertEqual([row.participant_id for row in page.context['matches']], [pid])
                self.assertNotIn('privado@example.com', page.text)
        for term in ('Ana Otro', '___', '%%%'):
            page = self.client.get('/community/participants/lookup', params={'q': term})
            self.assertEqual(page.context['matches'], [])

    def test_list_search_and_export_match_full_name_with_program_scope(self):
        pid, number = self.existing()
        self.login()
        page = self.client.get('/community/participants', params={'q': 'Ana Rivera Soto'})
        self.assertEqual([p.participant_id for p in page.context['participants']], [pid])
        self.assertIn(number, self.client.get('/community/participants/export.csv', params={'q': 'Ana Rivera'}).text)
        self.login(self.user_id)
        page = self.client.get('/community/participants', params={'q': 'Ana Rivera'})
        self.assertEqual(page.context['total'], 0)
        self.assertNotIn(number, self.client.get('/community/participants/export.csv', params={'q': 'Ana Rivera'}).text)
