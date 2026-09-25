"""Registration dashboard, filtered list and export share Community access rules."""
import csv
import io
import json
import unittest
from datetime import date
from types import SimpleNamespace

from sqlalchemy.orm import Session

import test_community_routes as fixture
from app.models.community_catalog import CPProfileField, CPProfileValue
from app.models.community_fiscal import CPFiscalParticipant
from app.services.community import create_fiscal_year, create_participant, update_participant
from app.services.community_fiscal import set_fiscal_status, sync_participants
from app.services.community_participants import filtered_query, roster_filters


class CommunityParticipantListTests(unittest.TestCase):
    setUp = fixture.CommunityRouteTests.setUp
    tearDown = fixture.CommunityRouteTests.tearDown
    token = fixture.CommunityRouteTests.token
    login = fixture.CommunityRouteTests.login
    participant_data = fixture.CommunityRouteTests.participant_data

    def seed(self):
        with Session(self.engine) as db:
            year = create_fiscal_year(db, 'TEST', 'Año de prueba', date(2025, 1, 1), date(2025, 12, 31))
            first = create_participant(db, actor_user_id=self.admin_id, exp_year=2026,
                program_ids=[self.voca_id, self.tanf_id], fields={
                    'nombre': 'Ana', 'apellido_paterno': 'Rivera', 'genero': 'F',
                    'fecha_nacimiento': '2000-05-12', 'telefono': '(787)-555-0100', 'pueblo': 'Ponce'})
            second = create_participant(db, actor_user_id=self.admin_id, exp_year=2026,
                program_ids=[self.tanf_id], fields={'nombre': '=Persona', 'apellido_paterno': 'Prueba', 'genero': 'M'})
            hidden = create_participant(db, actor_user_id=self.admin_id, exp_year=2026,
                program_ids=[self.icp_id], fields={'nombre': 'Reservado', 'apellido_paterno': 'ICP', 'genero': 'F'})
            sync_participants(db, year.fiscal_year_id, [first.participant_id], actor_user_id=self.admin_id)
            update_participant(db, participant_id=first.participant_id, fields={'pueblo': 'Mayagüez'})
            db.commit()
            self.first_id, self.second_id, self.hidden_id = first.participant_id, second.participant_id, hidden.participant_id
            self.year_id = year.fiscal_year_id

    def test_dashboard_deduplicates_people_and_keeps_program_scope(self):
        self.seed()
        self.login(self.user_id)
        page = self.client.get('/community/participants')
        self.assertEqual(page.status_code, 200, page.text)
        dashboard = page.context['dashboard']
        self.assertEqual(dashboard['totals'], {'registered_count': 2, 'assigned_count': 1, 'pending_sync_count': 1})
        by_id = {row['program_id']: row for row in dashboard['program_rows']}
        self.assertEqual(by_id[self.voca_id]['registered_count'], 1)
        self.assertEqual(by_id[self.tanf_id]['registered_count'], 2)
        self.assertEqual(by_id[self.tanf_id]['pending_sync_count'], 1)
        self.assertNotIn(self.icp_id, by_id)
        self.assertNotIn('Reservado', page.text)
        self.assertNotIn(f'/participants/{self.first_id}/edit', page.text)

    def test_closed_years_are_excluded_and_reopened_frozen_snapshots_are_not_pending(self):
        self.seed()
        self.login()
        with Session(self.engine) as db:
            set_fiscal_status(db, self.year_id, closed=True, actor_user_id=self.admin_id)
            db.commit()
        self.assertEqual(self.client.get('/community/participants').context['dashboard']['totals']['assigned_count'], 0)
        with Session(self.engine) as db:
            set_fiscal_status(db, self.year_id, closed=False, actor_user_id=self.admin_id)
            db.commit()
        totals = self.client.get('/community/participants').context['dashboard']['totals']
        self.assertEqual(totals['assigned_count'], 1)
        self.assertEqual(totals['pending_sync_count'], 0)

    def test_profile_only_change_is_pending_and_sync_clears_it(self):
        self.seed()
        self.login()
        with Session(self.engine) as db:
            field = CPProfileField(field_key='contacto', label='Contacto', field_type='text', is_required=False, is_active=True, sort_order=0)
            db.add(field)
            db.flush()
            value = CPProfileValue(participant_id=self.first_id, field_id=field.field_id, value='Anterior')
            db.add(value)
            db.flush()
            sync_participants(db, self.year_id, [self.first_id], actor_user_id=self.admin_id)
            value.value = 'Actual'
            db.commit()
        self.assertEqual(self.client.get('/community/participants').context['dashboard']['totals']['pending_sync_count'], 1)
        with Session(self.engine) as db:
            sync_participants(db, self.year_id, [self.first_id], actor_user_id=self.admin_id)
            db.commit()
        self.assertEqual(self.client.get('/community/participants').context['dashboard']['totals']['pending_sync_count'], 0)

    def test_retired_vca_in_legacy_snapshot_does_not_require_sync(self):
        self.seed()
        self.login()
        with Session(self.engine) as db:
            sync_participants(db, self.year_id, [self.first_id], actor_user_id=self.admin_id)
            snapshot = db.get(CPFiscalParticipant, (self.first_id, self.year_id))
            values = json.loads(snapshot.snapshot_json)
            self.assertNotIn('vca', values)
            values['vca'] = 'SI'
            legacy_snapshot = json.dumps(values)
            snapshot.snapshot_json = legacy_snapshot
            db.commit()
        self.assertEqual(self.client.get('/community/participants').context['dashboard']['totals']['pending_sync_count'], 0)
        with Session(self.engine) as db:
            self.assertEqual(db.get(CPFiscalParticipant, (self.first_id, self.year_id)).snapshot_json, legacy_snapshot)

    def test_filters_pagination_and_export_preserve_scope_and_do_not_duplicate(self):
        self.seed()
        self.login(self.user_id)
        filtered = self.client.get('/community/participants', params={'program_id': self.voca_id, 'age_min': 18})
        self.assertEqual([p.participant_id for p in filtered.context['participants']], [self.first_id])
        self.assertEqual(filtered.context['total'], 1)
        exact = self.client.get('/community/participants', params={'expediente_num': ' cp-2026-0001 '})
        self.assertEqual(exact.context['total'], 1)
        self.assertEqual(self.client.get('/community/participants', params={'expediente_num': '0001'}).context['total'], 0)
        for path in ('/community/participants', '/community/participants/export.csv'):
            self.assertEqual(self.client.get(path, params={'program_id': self.icp_id}).status_code, 403)
        page = self.client.get('/community/participants', params={'per_page': 1, 'page': 2, 'program_id': self.tanf_id})
        self.assertEqual(page.context['page'], 2)
        self.assertEqual(len(page.context['participants']), 1)
        self.assertEqual(page.context['total'], 2)
        export = self.client.get('/community/participants/export.csv', params={'program_id': self.tanf_id, 'per_page': 1, 'page': 2})
        self.assertEqual(export.status_code, 200, export.text)
        rows = list(csv.DictReader(io.StringIO(export.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows), 2)
        self.assertEqual({r['Número de expediente'] for r in rows}, {'CP-2026-0001', 'CP-2026-0002'})
        self.assertIn("'=Persona", [r['Nombre'] for r in rows])

    def test_registration_error_keeps_fields_programs_and_list_and_viewer_cannot_edit(self):
        self.seed()
        token = self.login()
        page = self.client.post('/community/participants', data=self.participant_data(token, nombre='', pueblo='Ponce'))
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn('Participantes registrados', page.text)
        self.assertIn('Datos de expediente', page.text)
        self.assertEqual(page.context['values']['program_ids'], [self.voca_id, self.tanf_id])
        self.assertEqual(page.context['values']['pueblo'], 'Ponce')
        self.login(self.viewer_id)
        page = self.client.get('/community/participants')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('id="participant-register-card"', page.text)
        self.assertNotIn('/edit"', page.text)
        self.assertEqual(self.client.get('/community/participants/export.csv').status_code, 200)

    def test_age_filter_respects_birthday_and_leap_day(self):
        with Session(self.engine) as db:
            for name, birthday in [('CumpleHoy', '2008-02-28'), ('CumpleMañana', '2008-02-29')]:
                create_participant(db, actor_user_id=self.admin_id, exp_year=2026, program_ids=[self.voca_id],
                    fields={'nombre': name, 'apellido_paterno': 'Prueba', 'genero': 'F', 'fecha_nacimiento': birthday})
            db.commit()
            context = SimpleNamespace(visible_program_ids={self.voca_id})
            filters = roster_filters({'age_min': '18', 'age_max': '18'}, context)
            result = db.scalars(filtered_query(context, filters, today=date(2026, 2, 28))).all()
            self.assertEqual([p.nombre for p in result], ['CumpleHoy'])
            result = db.scalars(filtered_query(context, filters, today=date(2026, 3, 1))).all()
            self.assertEqual({p.nombre for p in result}, {'CumpleHoy', 'CumpleMañana'})

    def test_selected_context_applies_to_summary_list_and_export(self):
        self.seed()
        self.login(self.user_id, program=self.voca_id)
        page = self.client.get('/community/participants')
        self.assertEqual(page.context['dashboard']['totals']['registered_count'], 1)
        self.assertEqual([row['program_id'] for row in page.context['dashboard']['program_rows']], [self.voca_id])
        self.assertEqual(page.context['total'], 1)
        export = self.client.get('/community/participants/export.csv')
        rows = list(csv.DictReader(io.StringIO(export.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['Programas'], 'VOCA')
        self.assertEqual(self.client.get('/community/participants/export.csv', params={'program_id': self.tanf_id}).status_code, 403)
