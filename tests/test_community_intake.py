"""Request dates, origin and emergency contact through real form routes."""
from datetime import date, timedelta
import json
import unittest

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import test_community_routes as fixture
from app.models.community import CPParticipant, CPSequence
from app.models.community_fiscal import CPFiscalParticipant
from app.services.community import create_participant, update_participant
from app.services.community_fiscal import build_participant_snapshot, comparable_snapshot, snapshot_changes


class CommunityIntakeTests(unittest.TestCase):
    setUp = fixture.CommunityRouteTests.setUp
    tearDown = fixture.CommunityRouteTests.tearDown
    token = fixture.CommunityRouteTests.token
    login = fixture.CommunityRouteTests.login
    participant_data = fixture.CommunityRouteTests.participant_data

    def data(self, token, **changes):
        values = self.participant_data(token, fecha_solicitud='2024-03-12',
            procedencia_solicitud='Autoreferido', emergencia_nombre='María Soto',
            emergencia_relacion='Hermana', emergencia_telefono='(787)-555-0199')
        values.update(changes)
        return values

    def test_create_reload_and_display_all_origins(self):
        token = self.login()
        for index, origin in enumerate(('Referido', 'Autoreferido', 'Identificado por personal'), 1):
            response = self.client.post('/community/participants', data=self.data(
                token, nombre=f'Prueba {index}', procedencia_solicitud=origin))
            self.assertEqual(response.status_code, 303, response.text)
            detail = self.client.get(response.headers['location'])
            self.assertEqual(detail.status_code, 200)
            for value in ('12/03/2024', origin, 'María Soto', 'Hermana', '(787)-555-0199'):
                self.assertIn(value, detail.text)
            with Session(self.engine) as db:
                person = db.get(CPParticipant, index)
                self.assertEqual(person.fecha_solicitud, date(2024, 3, 12))
                self.assertEqual(person.procedencia_solicitud, origin)
                self.assertEqual(person.emergencia_nombre, 'María Soto')
                self.assertEqual(person.emergencia_relacion, 'Hermana')
                self.assertEqual(person.emergencia_telefono, '(787)-555-0199')
                self.assertEqual(person.expediente_num, f'CP-2026-{index:04d}')
                self.assertNotEqual(person.created_at.date(), person.fecha_solicitud)
            edit = self.client.get(f'/community/participants/{index}/edit')
            self.assertIn('value="2024-03-12"', edit.text)
            self.assertIn(f'value="{origin}" selected', edit.text)

    def test_required_and_invalid_fields_preserve_form_without_consuming_number(self):
        token = self.login()
        cases = [
            ({'fecha_solicitud': ''}, 'fecha de solicitud'),
            ({'fecha_solicitud': '2024-02-30'}, 'fecha'),
            ({'fecha_solicitud': (date.today() + timedelta(days=1)).isoformat()}, 'futuro'),
            ({'procedencia_solicitud': ''}, 'procedencia'),
            ({'procedencia_solicitud': 'Otro'}, 'procedencia'),
            ({'emergencia_telefono': '123'}, 'emergencia'),
        ]
        for changes, error in cases:
            with self.subTest(changes=changes):
                response = self.client.post('/community/participants', data=self.data(token, **changes))
                self.assertEqual(response.status_code, 200)
                self.assertIn(error, response.context['form_error'].lower())
                self.assertEqual(response.context['values']['emergencia_nombre'], 'María Soto')
                self.assertIn('value="María Soto"', response.text)
                with Session(self.engine) as db:
                    self.assertEqual(db.scalar(select(func.count()).select_from(CPParticipant)), 0)
                    self.assertIsNone(db.get(CPSequence, 2026))

    def test_edit_persists_changes_and_allows_clearing_emergency_contact(self):
        token = self.login()
        self.assertEqual(self.client.post('/community/participants', data=self.data(token)).status_code, 303)
        response = self.client.post('/community/participants/1/edit', data=self.data(token,
            fecha_solicitud='2023-11-25', procedencia_solicitud='Referido',
            emergencia_nombre='', emergencia_relacion='', emergencia_telefono=''))
        self.assertEqual(response.status_code, 303, response.text)
        with Session(self.engine) as db:
            person = db.get(CPParticipant, 1)
            self.assertEqual(person.fecha_solicitud, date(2023, 11, 25))
            self.assertEqual(person.procedencia_solicitud, 'Referido')
            self.assertIsNone(person.emergencia_nombre)
            self.assertIsNone(person.emergencia_relacion)
            self.assertIsNone(person.emergencia_telefono)
            self.assertEqual(person.expediente_num, 'CP-2026-0001')
        detail = self.client.get('/community/participants/1')
        self.assertIn('25/11/2023', detail.text)
        self.assertIn('Contacto de emergencia', detail.text)
        self.assertIn('No informado', detail.text)
        for key in ('fecha_solicitud', 'procedencia_solicitud'):
            invalid = self.client.post('/community/participants/1/edit', data=self.data(token, **{key: ''}))
            self.assertEqual(invalid.status_code, 200)
            self.assertTrue(invalid.context['form_error'])
        with Session(self.engine) as db:
            self.assertEqual(db.get(CPParticipant, 1).fecha_solicitud, date(2023, 11, 25))

    def test_emergency_fields_are_individually_optional(self):
        token = self.login()
        for index, extra in enumerate(({}, {'emergencia_nombre': 'Contacto opcional'},
                                      {'emergencia_telefono': '(787)-555-0123'}), 1):
            data = self.data(token, nombre=f'Opcional {index}', emergencia_nombre='',
                             emergencia_relacion='', emergencia_telefono='')
            data.update(extra)
            self.assertEqual(self.client.post('/community/participants', data=data).status_code, 303)

    def test_legacy_record_remains_unknown_and_editable_until_completed(self):
        token = self.login()
        self.client.post('/community/participants', data=self.data(token))
        with Session(self.engine) as db:
            person = db.get(CPParticipant, 1)
            person.fecha_solicitud = person.procedencia_solicitud = None
            db.commit()
        page = self.client.get('/community/participants/1')
        self.assertIn('No informado', page.text)
        response = self.client.post('/community/participants/1/edit', data=self.data(token,
            fecha_solicitud='', procedencia_solicitud='', nombre='Nombre corregido'))
        self.assertEqual(response.status_code, 303)
        with Session(self.engine) as db:
            person = db.get(CPParticipant, 1)
            self.assertIsNone(person.fecha_solicitud)
            self.assertIsNone(person.procedencia_solicitud)
            self.assertEqual(person.nombre, 'Nombre corregido')
        response = self.client.post('/community/participants/1/edit', data=self.data(token))
        self.assertEqual(response.status_code, 303)

    def test_new_form_has_no_default_intake_values(self):
        self.login()
        page = self.client.get('/community/participants/new')
        self.assertIn('name="fecha_solicitud"', page.text)
        self.assertIn('name="procedencia_solicitud"', page.text)
        self.assertIn('Información de contacto', page.text)
        self.assertIn('Contacto de emergencia', page.text)
        self.assertNotIn('fecha_solicitud', page.context['values'])
        self.assertNotIn('procedencia_solicitud', page.context['values'])

    def test_service_requires_intake_and_preserves_optional_fields_when_omitted(self):
        with Session(self.engine) as db:
            fields = {'nombre': 'Servicio', 'apellido_paterno': 'Prueba', 'genero': 'F'}
            with self.assertRaises(ValueError):
                create_participant(db, actor_user_id=self.admin_id, exp_year=2026,
                                   program_ids=[self.voca_id], fields=fields)
            fields.update(fecha_solicitud='2024-03-12', procedencia_solicitud='Referido',
                          emergencia_nombre='Persona de contacto')
            person = create_participant(db, actor_user_id=self.admin_id, exp_year=2026,
                                        program_ids=[self.voca_id], fields=fields)
            db.commit()
            update_participant(db, participant_id=person.participant_id, fields={'nombre': 'Actualizado'})
            db.commit()
            self.assertEqual(person.emergencia_nombre, 'Persona de contacto')
            self.assertEqual(person.fecha_solicitud, date(2024, 3, 12))
            current = build_participant_snapshot(db, person)
            historical = dict(current)
            historical['fecha_solicitud'] = '2023-01-01'
            changes = snapshot_changes(CPFiscalParticipant(snapshot_json=json.dumps(historical)), current, [], {})
            self.assertIn({'label': 'Fecha de solicitud', 'before': '01/01/2023', 'after': '12/03/2024'}, changes)

    def test_legacy_snapshot_does_not_report_empty_intake_as_a_change(self):
        keys = ('fecha_solicitud', 'procedencia_solicitud', 'emergencia_nombre',
                'emergencia_relacion', 'emergencia_telefono')
        row = CPFiscalParticipant(snapshot_json=json.dumps({'program_ids': []}))
        original = row.snapshot_json
        normalized = comparable_snapshot(row, [])
        for key in keys:
            self.assertIn(key, normalized)
            self.assertIsNone(normalized[key])
        self.assertEqual(row.snapshot_json, original)


if __name__ == '__main__':
    unittest.main()
