import json
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

import test_community_fiscal as fixture
from app.core.community_access import CommunityContext
from app.models.community import CPParticipant, CPParticipantProgram
from app.models.community_catalog import CPProfileField, CPProfileValue
from app.models.community_activity import CPActivity, CPFiscalActivity
from app.models.community_fiscal import CPFiscalParticipant, CPFiscalEnrollment
from app.models.community_operations import CPActivitySession, CPAttendance, CPGradeReport, CPGradeItem
from app.services.community import associate_participant_programs, create_fiscal_year, create_participant, create_program
from app.services.community_fiscal import enroll_participant, set_fiscal_status, set_snapshot_freeze, sync_participants


class CommunityFiscalManagementTests(fixture.CommunityFiscalRouteTests):
    """Exercise fiscal management through its routes and real temporary storage."""

    def page(self, **params):
        return self.client.get('/community/fiscal-participants', params={
            'fiscal_year_id': self.year.fiscal_year_id, **params})

    def post(self, suffix='/sync', **data):
        return self.client.post('/community/fiscal-participants' + suffix, data={
            'token': 'fiscal-test-token', 'fiscal_year_id': self.year.fiscal_year_id,
            'participant_ids': [self.person.participant_id], **data})

    def test_available_lists_distinguish_selected_year_from_no_year(self):
        other = create_participant(self.db, actor_user_id=self.actor.user_id, exp_year=2024,
            program_ids=[self.voca.program_id], fields={'nombre': 'Nueva', 'apellido_paterno': 'Prueba', 'genero': 'F'})
        following = create_fiscal_year(self.db, '2025', 'Siguiente', date(2025, 1, 1), date(2025, 12, 31))
        self.sync(following)
        self.db.commit()
        response = self.page()
        self.assertEqual(response.status_code, 200)
        self.assertEqual({r['participant'].participant_id for r in response.context['available_rows']},
                         {other.participant_id, self.person.participant_id})
        never = self.page(available_filter='never')
        self.assertEqual([r['participant'].participant_id for r in never.context['available_rows']], [other.participant_id])
        self.post(mode='add')
        assigned = self.page(sync_filter='all')
        self.assertEqual([r['participant'].participant_id for r in assigned.context['assigned_rows']], [self.person.participant_id])
        self.assertEqual([r['participant'].participant_id for r in assigned.context['available_rows']], [other.participant_id])

    def test_pending_details_show_old_new_profile_and_new_program(self):
        self.sync()
        field = CPProfileField(field_key='contacto', label='Contacto familiar', field_type='text')
        self.db.add(field)
        self.db.flush()
        self.db.add(CPProfileValue(participant_id=self.person.participant_id, field_id=field.field_id, value='Tía'))
        program = create_program(self.db, 'ICP', 'Programa ICP')
        associate_participant_programs(self.db, participant_id=self.person.participant_id,
                                      actor_user_id=self.actor.user_id, program_ids=[program.program_id])
        self.context = CommunityContext(self.actor, 'supervisor', (self.voca, self.tanf, program))
        self.person.pueblo = 'San Juan'
        self.db.commit()
        response = self.page(sync_filter='pending')
        row = response.context['assigned_rows'][0]
        changes = {change['label']: change for change in row['changes']}
        self.assertEqual(changes['Pueblo']['before'], 'Ponce')
        self.assertEqual(changes['Pueblo']['after'], 'San Juan')
        self.assertIn('Tía', response.text)
        self.assertIn('Programa añadido', response.text)
        self.assertIn('ICP', response.text)
        self.assertEqual(self.post(mode='pending').status_code, 303)
        self.assertEqual(self.page(sync_filter='pending').context['assigned_rows'], [])
        self.assertEqual(list(self.db.scalars(select(CPFiscalEnrollment))), [])

    def test_legacy_snapshot_without_program_list_is_not_falsely_outdated(self):
        self.sync()
        row = self.db.get(CPFiscalParticipant, (self.person.participant_id, self.year.fiscal_year_id))
        old = json.loads(row.snapshot_json)
        old.pop('program_ids', None)
        old['vca'] = 'NO'
        row.snapshot_json = json.dumps(old)
        self.db.commit()
        self.assertEqual(self.page(sync_filter='pending').context['assigned_rows'], [])
        association = self.db.get(CPParticipantProgram, (self.person.participant_id, self.tanf.program_id))
        association.created_at = row.updated_at + timedelta(seconds=1)
        self.db.commit()
        self.assertIn('Programa añadido', self.page(sync_filter='pending').text)

    def test_add_does_not_overwrite_existing_snapshot_and_sync_changes_only_selected_year(self):
        self.sync()
        following = create_fiscal_year(self.db, '2025', 'Siguiente', date(2025, 1, 1), date(2025, 12, 31))
        self.sync(following)
        self.person.pueblo = 'San Juan'
        self.db.commit()
        self.post(mode='add')
        self.assertEqual(json.loads(self.db.get(CPFiscalParticipant,
            (self.person.participant_id, self.year.fiscal_year_id)).snapshot_json)['pueblo'], 'Ponce')
        self.post(mode='pending')
        self.assertEqual(json.loads(self.db.get(CPFiscalParticipant,
            (self.person.participant_id, self.year.fiscal_year_id)).snapshot_json)['pueblo'], 'San Juan')
        self.assertEqual(json.loads(self.db.get(CPFiscalParticipant,
            (self.person.participant_id, following.fiscal_year_id)).snapshot_json)['pueblo'], 'Ponce')

    def test_remove_unused_year_keeps_record_programs_and_other_year(self):
        self.sync()
        following = create_fiscal_year(self.db, '2025', 'Siguiente', date(2025, 1, 1), date(2025, 12, 31))
        self.sync(following)
        self.db.commit()
        response = self.post(f'/{self.person.participant_id}/remove')
        self.assertEqual(response.status_code, 303)
        self.assertNotIn('error', parse_qs(urlparse(response.headers['location']).query))
        self.assertIsNone(self.db.get(CPFiscalParticipant, (self.person.participant_id, self.year.fiscal_year_id)))
        self.assertIsNotNone(self.db.get(CPFiscalParticipant, (self.person.participant_id, following.fiscal_year_id)))
        self.assertIsNotNone(self.db.get(CPParticipant, self.person.participant_id))
        self.assertIsNotNone(self.db.get(CPParticipantProgram, (self.person.participant_id, self.voca.program_id)))

    def test_remove_refuses_enrollment_history_and_frozen_year(self):
        self.sync()
        set_snapshot_freeze(self.db, self.year.fiscal_year_id, frozen=True, actor_user_id=self.actor.user_id)
        self.db.commit()
        self.assertIn('error=', self.post(f'/{self.person.participant_id}/remove').headers['location'])
        set_snapshot_freeze(self.db, self.year.fiscal_year_id, frozen=False, actor_user_id=self.actor.user_id)
        enroll_participant(self.db, start_date=date(2024, 2, 1), **self.arguments())
        self.db.commit()
        self.assertIn('error=', self.post(f'/{self.person.participant_id}/remove').headers['location'])
        self.assertIsNotNone(self.db.get(CPFiscalParticipant, (self.person.participant_id, self.year.fiscal_year_id)))

    def test_search_filters_and_return_context_are_preserved(self):
        self.sync()
        self.db.commit()
        self.assertEqual(len(self.page(q='María Rivera', sync_filter='all').context['assigned_rows']), 1)
        self.assertEqual(self.page(q='Otra persona').context['assigned_rows'], [])
        response = self.post(return_query=f'q=Mar%C3%ADa&program_id={self.voca.program_id}&sync_filter=all')
        query = parse_qs(urlparse(response.headers['location']).query)
        self.assertEqual(query['q'], ['María'])
        self.assertEqual(query['program_id'], [str(self.voca.program_id)])

    def test_removal_checks_role_csrf_and_scope(self):
        self.sync()
        self.db.commit()
        suffix = f'/{self.person.participant_id}/remove'
        self.assertEqual(self.post(suffix, token='wrong').status_code, 403)
        self.context = CommunityContext(self.actor, 'user', (self.voca, self.tanf))
        self.assertEqual(self.post(suffix).status_code, 403)
        self.context = CommunityContext(self.actor, 'supervisor', (self.voca, self.tanf), self.voca.program_id)
        self.assertIn('error=', self.post(suffix).headers['location'])
        self.assertIsNotNone(self.db.get(CPFiscalParticipant, (self.person.participant_id, self.year.fiscal_year_id)))

    def test_removal_preserves_attendance_and_grade_history_without_enrollment(self):
        self.sync()
        activity = CPActivity(program_id=self.voca.program_id, code='A1', code_key='a1')
        self.db.add(activity)
        self.db.flush()
        self.db.add(CPFiscalActivity(activity_id=activity.activity_id, fiscal_year_id=self.year.fiscal_year_id,
                                    program_id=self.voca.program_id))
        self.db.flush()
        session = CPActivitySession(activity_id=activity.activity_id, fiscal_year_id=self.year.fiscal_year_id,
            program_id=self.voca.program_id, session_date=date(2024, 2, 1), created_by_user_id=self.actor.user_id)
        self.db.add(session)
        self.db.flush()
        attendance = CPAttendance(session_id=session.session_id, participant_id=self.person.participant_id, is_present=False)
        self.db.add(attendance)
        self.db.commit()
        self.assertIn('error=', self.post(f'/{self.person.participant_id}/remove').headers['location'])
        self.assertIsNotNone(self.page(sync_filter='all').context['assigned_rows'][0]['remove_reason'])
        # Independently exercise grade history, with no enrollment or attendance.
        self.db.delete(attendance)
        report = CPGradeReport(fiscal_year_id=self.year.fiscal_year_id, program_id=self.voca.program_id,
            report_month=2, report_year=2024, created_by_user_id=self.actor.user_id)
        self.db.add(report)
        self.db.flush()
        self.db.add(CPGradeItem(report_id=report.report_id, participant_id=self.person.participant_id))
        self.db.commit()
        self.assertIn('error=', self.post(f'/{self.person.participant_id}/remove').headers['location'])
        self.assertIsNotNone(self.db.get(CPFiscalParticipant, (self.person.participant_id, self.year.fiscal_year_id)))
        self.assertIsNotNone(self.db.get(CPGradeItem, (report.report_id, self.person.participant_id)))

    def test_closed_and_frozen_years_reject_all_snapshot_actions(self):
        self.sync()
        self.person.pueblo = 'San Juan'
        set_snapshot_freeze(self.db, self.year.fiscal_year_id, frozen=True, actor_user_id=self.actor.user_id)
        self.db.commit()
        for closed in (False, True):
            if closed:
                set_fiscal_status(self.db, self.year.fiscal_year_id, closed=True, actor_user_id=self.actor.user_id)
                self.db.commit()
            for mode in ('sync', 'add', 'pending'):
                with self.subTest(closed=closed, mode=mode):
                    self.assertIn('error=', self.post(mode=mode).headers['location'])
            self.assertIn('error=', self.post(f'/{self.person.participant_id}/remove').headers['location'])
            page = self.page(sync_filter='all')
            self.assertIn('solo lectura', page.text)
            self.assertNotIn('>Sync</button>', page.text)
            self.assertNotIn('>Quitar</button>', page.text)
            self.assertEqual(json.loads(self.db.get(CPFiscalParticipant,
                (self.person.participant_id, self.year.fiscal_year_id)).snapshot_json)['pueblo'], 'Ponce')

    def test_visible_pending_sync_does_not_update_other_pages_or_add_new_people(self):
        people = [self.person]
        for number in range(51):
            people.append(create_participant(self.db, actor_user_id=self.actor.user_id, exp_year=2024,
                program_ids=[self.voca.program_id], fields={'nombre': f'Persona {number}',
                    'apellido_paterno': 'Prueba', 'genero': 'F', 'pueblo': 'Ponce'}))
        ids = [person.participant_id for person in people]
        sync_participants(self.db, self.year.fiscal_year_id, ids, actor_user_id=self.actor.user_id)
        for person in people:
            person.pueblo = 'San Juan'
        available = create_participant(self.db, actor_user_id=self.actor.user_id, exp_year=2024,
            program_ids=[self.voca.program_id], fields={'nombre': 'Disponible', 'apellido_paterno': 'Prueba', 'genero': 'F'})
        self.db.commit()
        page = self.page(sync_filter='pending', assigned_page=2)
        self.assertEqual(page.context['assigned_total'], 52)
        visible = [row['participant'].participant_id for row in page.context['assigned_rows']]
        self.assertEqual(len(visible), 2)
        self.post(mode='pending', participant_ids=visible + [available.participant_id])
        self.assertEqual(self.page(sync_filter='pending').context['assigned_total'], 50)
        self.assertIsNone(self.db.get(CPFiscalParticipant, (available.participant_id, self.year.fiscal_year_id)))
        for pid in ids:
            snapshot = json.loads(self.db.get(CPFiscalParticipant, (pid, self.year.fiscal_year_id)).snapshot_json)
            self.assertEqual(snapshot['pueblo'], 'San Juan' if pid in visible else 'Ponce')

    def test_profile_label_change_is_explained_and_dashboard_counts_new_program(self):
        from app.services.community_participants import registration_dashboard
        field = CPProfileField(field_key='contacto', label='Tutor', field_type='text')
        self.db.add(field)
        self.db.flush()
        self.db.add(CPProfileValue(participant_id=self.person.participant_id, field_id=field.field_id, value='Tía'))
        self.sync()
        field.label = 'Contacto familiar'
        self.db.commit()
        changes = self.page().context['assigned_rows'][0]['changes']
        self.assertTrue(any(change['before'] == 'Tutor' and change['after'] == 'Contacto familiar' for change in changes))
        self.post()
        program = create_program(self.db, 'ICP', 'ICP')
        associate_participant_programs(self.db, participant_id=self.person.participant_id,
            actor_user_id=self.actor.user_id, program_ids=[program.program_id])
        self.context = CommunityContext(self.actor, 'admin', (self.voca, self.tanf, program))
        self.db.commit()
        self.assertEqual(registration_dashboard(self.db, self.context)['totals']['pending_sync_count'], 1)
