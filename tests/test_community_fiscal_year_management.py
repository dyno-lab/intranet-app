import unittest
from datetime import date
from urllib.parse import parse_qs, urlparse
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

import test_community_routes as fixture
from app.models.community import CPFiscalYear, CPParticipant, CPUserAccess
from app.models.community_fiscal import CPFiscalState, CPFiscalParticipant
from app.models.community_activity import CPActivity, CPFiscalActivity
from app.models.community_operations import CPActivitySession, CPGradeReport
from app.db.community_fiscal_schema import COMMUNITY_FISCAL_SCHEMA_SQL
from app.services.community import create_fiscal_year, create_participant
from app.services.community_fiscal import set_fiscal_lock, sync_participants
from app.services.community_years import closing_months


class CommunityFiscalYearManagementTests(unittest.TestCase):
    tearDown = fixture.CommunityRouteTests.tearDown
    token = fixture.CommunityRouteTests.token
    login = fixture.CommunityRouteTests.login

    def setUp(self):
        fixture.CommunityRouteTests.setUp(self)
        with Session(self.engine) as db:
            year = create_fiscal_year(db, '2024', 'Año de prueba', date(2024, 1, 15), date(2024, 12, 20))
            db.commit()
            self.year_id = year.fiscal_year_id
        self.csrf = self.login()

    def post(self, operation, **data):
        return self.client.post(f'/community/fiscal-years/{self.year_id}/{operation}', data={
            'token': self.csrf, 'return_to': 'fiscal-years', **data})

    def test_year_list_has_management_controls_and_calendar_months(self):
        page = self.client.get('/community/fiscal-years')
        self.assertEqual(page.status_code, 200)
        for text in ('Editar', 'Cerrar año fiscal', 'Cerrar períodos', 'Copiar año fiscal', 'Participantes',
                     'Febrero 2024', '20/12/2024'):
            self.assertIn(text, page.text)
        self.assertIn('value="2024-02-29"', page.text)
        self.assertIn('value="2024-12-20"', page.text)

    def test_closing_from_years_records_note_and_reopening_preserves_locks(self):
        with Session(self.engine) as db:
            set_fiscal_lock(db, self.year_id, locked_through=date(2024, 2, 29), actor_user_id=self.admin_id)
            db.commit()
        response = self.post('status', action='close', closure_note='Informes completados')
        self.assertEqual(urlparse(response.headers['location']).path, '/community/fiscal-years')
        with Session(self.engine) as db:
            state = db.get(CPFiscalState, self.year_id)
            self.assertEqual(db.get(CPFiscalYear, self.year_id).status, 'closed')
            self.assertTrue(state.snapshots_frozen)
            self.assertEqual(state.closure_note, 'Informes completados')
            self.assertEqual(state.closed_by_user_id, self.admin_id)
            closed_at = state.closed_at
            self.assertIsNotNone(closed_at)
        self.post('status', action='reopen')
        with Session(self.engine) as db:
            state = db.get(CPFiscalState, self.year_id)
            self.assertEqual(db.get(CPFiscalYear, self.year_id).status, 'active')
            self.assertTrue(state.snapshots_frozen)
            self.assertEqual(state.locked_through, date(2024, 2, 29))
            self.assertEqual(state.closed_at, closed_at)
        self.post('freeze', action='unfreeze')
        with Session(self.engine) as db:
            self.assertFalse(db.get(CPFiscalState, self.year_id).snapshots_frozen)

    def test_month_closure_note_can_be_changed_and_months_reopened(self):
        response = self.post('periods', locked_through='2024-02-29', period_lock_note='Febrero entregado')
        self.assertEqual(urlparse(response.headers['location']).path, '/community/fiscal-years')
        with Session(self.engine) as db:
            state = db.get(CPFiscalState, self.year_id)
            self.assertEqual(state.locked_through, date(2024, 2, 29))
            self.assertEqual(state.period_lock_note, 'Febrero entregado')
        self.post('periods', locked_through='2024-01-31', period_lock_note='Revisión de febrero')
        self.post('periods', locked_through='', period_lock_note='')
        with Session(self.engine) as db:
            state = db.get(CPFiscalState, self.year_id)
            self.assertIsNone(state.locked_through)
            self.assertIsNone(state.period_lock_note)

    def test_invalid_closures_do_not_modify_the_year(self):
        for day in ('2024-02-28', '2023-12-31', '2025-01-31', 'bad-date'):
            with self.subTest(day=day):
                response = self.post('periods', locked_through=day)
                self.assertIn('error', parse_qs(urlparse(response.headers['location']).query))
        self.post('status', action='close')
        self.assertIn('error=', self.post('periods', locked_through='2024-02-29').headers['location'])

    def test_existing_sync_screen_return_is_preserved_and_unknown_target_is_not_redirected(self):
        response = self.post('freeze', action='freeze', return_to='https://example.com')
        self.assertEqual(urlparse(response.headers['location']).path, '/community/fiscal-participants')
        response = self.client.post(f'/community/fiscal-years/{self.year_id}/freeze', data={
            'token': self.csrf, 'action': 'unfreeze'})
        self.assertEqual(urlparse(response.headers['location']).path, '/community/fiscal-participants')

    def test_year_actions_require_community_admin_and_csrf(self):
        self.assertEqual(self.post('periods', token='wrong', locked_through='2024-02-29').status_code, 403)
        for role in ('supervisor', 'user', 'viewer'):
            with Session(self.engine) as db:
                db.get(CPUserAccess, self.user_id).role = role
                db.commit()
            self.csrf = self.login(self.user_id)
            self.assertEqual(self.client.get('/community/fiscal-years').status_code, 403)
            for action, fields in [('status', {'action': 'close'}), ('freeze', {'action': 'freeze'}),
                                   ('periods', {'locked_through': '2024-02-29'}),
                                   ('edit', {'code': 'X', 'name': 'X', 'start_date': '2024-01-15', 'end_date': '2024-12-20'})]:
                self.assertEqual(self.post(action, **fields).status_code, 403)

    def edit(self, **values):
        return self.post('edit', **{'code': '2024-A', 'name': 'Nombre corregido',
            'start_date': '2024-01-15', 'end_date': '2024-12-20', **values})

    def test_unused_year_can_edit_code_name_and_dates(self):
        response = self.edit(start_date='2024-01-01', end_date='2024-12-31')
        self.assertEqual(response.status_code, 303, response.text)
        self.assertNotIn('error=', response.headers['location'])
        with Session(self.engine) as db:
            year = db.get(CPFiscalYear, self.year_id)
            self.assertEqual((year.code, year.name, year.start_date, year.end_date),
                ('2024-A', 'Nombre corregido', date(2024, 1, 1), date(2024, 12, 31)))

    def test_synced_year_keeps_dates_but_allows_code_and_name_without_altering_snapshot(self):
        with Session(self.engine) as db:
            person = create_participant(db, actor_user_id=self.admin_id, exp_year=2024,
                program_ids=[self.voca_id], fields={'nombre': 'Ana', 'apellido_paterno': 'Rivera', 'genero': 'F'})
            sync_participants(db, self.year_id, [person.participant_id], actor_user_id=self.admin_id)
            db.commit()
            pid = person.participant_id
            saved = db.get(CPFiscalParticipant, (pid, self.year_id)).snapshot_json
        response = self.edit(start_date='2024-01-01')
        self.assertEqual(response.status_code, 303, response.text)
        self.assertIn('error=', response.headers['location'])
        self.assertNotIn('error=', self.edit().headers['location'])
        with Session(self.engine) as db:
            year = db.get(CPFiscalYear, self.year_id)
            self.assertEqual(year.code, '2024-A')
            self.assertEqual(year.start_date, date(2024, 1, 15))
            self.assertEqual(db.get(CPFiscalParticipant, (pid, self.year_id)).snapshot_json, saved)
            self.assertEqual(db.get(CPParticipant, pid).expediente_num, 'CP-2024-0001')

    def test_invalid_or_closed_year_edits_do_not_commit_partial_changes(self):
        for values in ({'end_date': '2024-01-01'}, {'start_date': 'bad-date'}):
            response = self.edit(**values)
            self.assertEqual(response.status_code, 303)
            self.assertIn('error=', response.headers['location'])
        self.post('status', action='close')
        self.assertIn('error=', self.edit().headers['location'])
        with Session(self.engine) as db:
            year = db.get(CPFiscalYear, self.year_id)
            self.assertEqual(year.code, '2024')
            self.assertEqual(year.name, 'Año de prueba')

    def test_duplicate_codes_and_overlong_notes_rollback(self):
        with Session(self.engine) as db:
            create_fiscal_year(db, 'TAKEN', 'Existente', date(2025, 1, 1), date(2025, 12, 31))
            db.commit()
        self.assertIn('error=', self.edit(code='taken').headers['location'])
        self.assertIn('error=', self.post('status', action='close', closure_note='X' * 501).headers['location'])
        self.assertIn('error=', self.post('periods', locked_through='2024-02-29', period_lock_note='X' * 501).headers['location'])
        with Session(self.engine) as db:
            year = db.get(CPFiscalYear, self.year_id)
            self.assertEqual((year.code, year.status), ('2024', 'active'))
            self.assertIsNone(db.get(CPFiscalState, self.year_id))

    def test_month_options_follow_fiscal_range_leap_year_and_today(self):
        year = SimpleNamespace(start_date=date(2025, 10, 1), end_date=date(2026, 9, 20))
        self.assertEqual([row['value'] for row in closing_months(year, date(2026, 2, 15))],
                         ['2025-10-31', '2025-11-30', '2025-12-31', '2026-01-31'])
        self.assertEqual(closing_months(year, date(2025, 9, 30)), [])
        self.assertEqual(closing_months(year, date(2026, 9, 20))[-1]['value'], '2026-09-20')
        leap = SimpleNamespace(start_date=date(2024, 2, 15), end_date=date(2024, 3, 1))
        self.assertEqual(closing_months(leap, date(2024, 2, 29))[0]['value'], '2024-02-29')

    def test_old_period_form_preserves_note_and_future_year_cannot_close_months(self):
        self.post('periods', locked_through='2024-02-29', period_lock_note='Conservar')
        self.client.post(f'/community/fiscal-years/{self.year_id}/periods', data={
            'token': self.csrf, 'locked_through': '2024-03-31'})
        with Session(self.engine) as db:
            self.assertEqual(db.get(CPFiscalState, self.year_id).period_lock_note, 'Conservar')
            future = create_fiscal_year(db, 'FUTURE', 'Futuro', date(date.today().year + 1, 1, 1), date(date.today().year + 1, 12, 31))
            db.commit()
            fyid = future.fiscal_year_id
        response = self.client.post(f'/community/fiscal-years/{fyid}/periods', data={
            'token': self.csrf, 'locked_through': f'{date.today().year + 1}-01-31'})
        self.assertIn('error=', response.headers['location'])

    def test_sessions_and_grade_reports_fix_dates_even_without_synced_participants(self):
        with Session(self.engine) as db:
            activity = CPActivity(program_id=self.voca_id, code='A', code_key='a')
            db.add(activity)
            db.flush()
            db.add(CPFiscalActivity(activity_id=activity.activity_id, fiscal_year_id=self.year_id, program_id=self.voca_id))
            db.flush()
            session = CPActivitySession(activity_id=activity.activity_id, fiscal_year_id=self.year_id,
                program_id=self.voca_id, session_date=date(2024, 3, 1), created_by_user_id=self.admin_id)
            db.add(session)
            db.commit()
            session_id = session.session_id
        self.assertIn('error=', self.edit(end_date='2024-12-31').headers['location'])
        with Session(self.engine) as db:
            db.delete(db.get(CPActivitySession, session_id))
            db.add(CPGradeReport(fiscal_year_id=self.year_id, program_id=self.voca_id, report_month=3,
                report_year=2024, created_by_user_id=self.admin_id))
            db.commit()
        self.assertIn('error=', self.edit(end_date='2024-12-31').headers['location'])

    def test_copy_closed_year_keeps_configuration_without_participants_or_locks(self):
        with Session(self.engine) as db:
            activity = CPActivity(program_id=self.voca_id, code='A', code_key='a')
            db.add(activity)
            db.flush()
            db.add(CPFiscalActivity(activity_id=activity.activity_id, fiscal_year_id=self.year_id,
                program_id=self.voca_id, goal_type='monthly_fixed', goal_value=10))
            person = create_participant(db, actor_user_id=self.admin_id, exp_year=2024,
                program_ids=[self.voca_id], fields={'nombre': 'Ana', 'apellido_paterno': 'Rivera', 'genero': 'F'})
            sync_participants(db, self.year_id, [person.participant_id], actor_user_id=self.admin_id)
            db.commit()
            activity_id = activity.activity_id
        self.post('status', action='close', closure_note='Cierre original')
        response = self.client.post('/community/fiscal-years', data={'token': self.csrf, 'copy_from': self.year_id,
            'code': 'COPY', 'name': 'Copia', 'start_date': '2025-01-01', 'end_date': '2025-12-31'})
        self.assertEqual(response.status_code, 303)
        self.assertNotIn('error=', response.headers['location'])
        with Session(self.engine) as db:
            copied = db.scalar(select(CPFiscalYear).where(CPFiscalYear.code == 'COPY'))
            self.assertEqual(copied.status, 'active')
            self.assertEqual(db.get(CPFiscalActivity, (activity_id, copied.fiscal_year_id)).goal_value, 10)
            self.assertIsNone(db.get(CPFiscalState, copied.fiscal_year_id))
            self.assertEqual(list(db.scalars(select(CPFiscalParticipant).where(CPFiscalParticipant.fiscal_year_id == copied.fiscal_year_id))), [])

    def test_close_metadata_schema_is_nullable_and_additive_for_existing_years(self):
        ddl = str(CreateTable(CPFiscalState.__table__).compile(dialect=mssql.dialect()))
        for column, sql_type in [('period_lock_note', 'NVARCHAR(500)'), ('closure_note', 'NVARCHAR(500)'),
                                 ('closed_at', 'DATETIMEOFFSET'), ('closed_by_user_id', 'INTEGER')]:
            self.assertTrue(CPFiscalState.__table__.c[column].nullable)
            self.assertIn(f'{column} {sql_type} NULL', ddl)
            self.assertIn(f"IF COL_LENGTH(N'dbo.cp_fiscal_states', N'{column}') IS NULL", COMMUNITY_FISCAL_SCHEMA_SQL)
        self.assertNotIn('DROP ', COMMUNITY_FISCAL_SCHEMA_SQL)
        self.assertNotIn('DELETE ', COMMUNITY_FISCAL_SCHEMA_SQL)
        self.assertNotIn('UPDATE ', COMMUNITY_FISCAL_SCHEMA_SQL)
        self.assertIn('FK_cp_fiscal_state_closer', COMMUNITY_FISCAL_SCHEMA_SQL)
