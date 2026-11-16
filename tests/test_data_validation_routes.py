import re
import unittest
from datetime import date
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select
from tests.test_data_validation import DataValidationTests
from app.api.routes import data_validation as routes
from app.api.deps import get_db
from app.models.base import Base
from app.models.platform_permission import PlatformPermission
from app.models.user_platform_permission import UserPlatformPermission
from app.models.user_residential import UserResidential
from app.models.data_validation import DataValidationIssue, DataValidationEvent
from app.core.platform_permissions import ACCESS_FARO, ACCESS_AUTOMATION


class DataValidationRoutes(unittest.TestCase):
    def setUp(self):
        self.source=DataValidationTests();self.source.setUp();self.addCleanup(self.source.doCleanups)
        self.f=self.source.f;self.db=self.f.db;self.user=self.f.actor
        Base.metadata.create_all(self.f.engine,tables=[PlatformPermission.__table__,UserPlatformPermission.__table__,UserResidential.__table__])
        for key in (ACCESS_FARO,ACCESS_AUTOMATION):
            perm=PlatformPermission(key=key,name=key,is_active=True)
            self.db.add(perm);self.db.flush()
            self.db.add(UserPlatformPermission(user_id=self.user.user_id,permission_id=perm.permission_id))
        self.db.add(UserResidential(user_id=self.user.user_id,residential_id=self.f.a.residential_id))
        self.db.commit()
        app=FastAPI();app.add_middleware(SessionMiddleware,secret_key='data-validation-test-only')
        app.include_router(routes.router);app.dependency_overrides[get_db]=lambda:self.db
        @app.get('/test/login')
        def login(request:Request):
            request.session.clear();request.session.update(user_id=self.user.user_id,session_version=self.user.session_version)
        self.client=TestClient(app);self.addCleanup(self.client.close);self.client.get('/test/login')
        self.url='/automatizaciones/faro/validacion'
        self.params=dict(proposal_id=self.f.proposal.proposal_id,year=2026,months=9)

    def form(self):
        response=self.client.get(self.url,params=self.params)
        self.assertEqual(response.status_code,200,response.text)
        csrf=re.search('name="csrf_token" value="([^"]+)"',response.text)[1]
        tokens=re.findall('name="targets" value="([^"]+)"',response.text)
        return response,dict(**self.params,csrf_token=csrf,targets=tokens[0])

    def test_authenticated_filters_supervision_and_readonly_get(self):
        page,_=self.form()
        self.assertIn('Vista de supervisión',page.text)
        self.assertIn(self.f.proposal.name,page.text)
        self.assertNotIn('Datos ficticios',page.text)
        self.assertEqual(page.headers['cache-control'],'no-store')
        self.assertEqual(self.db.scalars(select(DataValidationIssue)).all(),[])
        self.assertEqual(self.client.get(self.url+'?proposal_id=&residential_id=&year=&months=').status_code,200)
        for invalid in ({'year':'bad'},{'months':'13'},{'year':1999}):
            self.assertEqual(self.client.get(self.url,params={**self.params,**invalid}).status_code,422)
        self.assertIn('Seguimiento',self.client.get(self.url,params={**self.params,'view':'residentials'}).text)

    def test_record_groups_and_detail_include_all_errors_even_outside_status_filter(self):
        from app.services import data_validation as service
        from app.models.participant_profile_field import ParticipantProfileField

        self.f.old.apellido_paterno = ''
        self.f.old.edificio = None
        self.f.old.apart = None
        self.db.add_all([ParticipantProfileField(field_key=f'required_{i}', label=f'Campo requerido {i}',
            is_required=True) for i in range(28)])
        self.db.commit()
        page, form = self.form()
        self.assertEqual(page.text.count(f'data-record-group="{self.f.old.proposal_participant_id}"'), 1)
        for title in ('Primer apellido sin registrar', 'Edificio sin registrar', 'Apartamento sin registrar',
                      'Grupo familiar sin registrar', 'Campo requerido 27 sin registrar'):
            self.assertIn(title, page.text)
        building = self.source.issue('missing_edificio')
        service.mutate(self.db, self.user, 'assign', self.source.filters, targets=[building['token']],
            assignee='residential', due_on=date(2099, 11, 18))
        self.db.commit()
        surname = self.source.issue('missing_apellido_paterno')
        response = self.client.get(self.url, params={**self.params, 'finding': surname['key'], 'status': 'pending'})
        self.assertEqual(response.status_code, 200)
        dialog = re.search(r'<section[^>]+data-record-findings.*?</section>', response.text, re.S)[0]
        self.assertIn('Todos los hallazgos de este expediente', dialog)
        for title in ('Primer apellido sin registrar', 'Edificio sin registrar', 'Apartamento sin registrar',
                      'Grupo familiar sin registrar', 'Campo requerido 27 sin registrar'):
            self.assertIn(title, dialog)
        self.assertIn('En revisión', dialog)
        self.assertIn(f'finding={building["key"]}', dialog)
        self.assertNotIn(self.f.other.expediente_num, dialog)

    def test_one_record_row_across_proposals_with_historical_number_separate(self):
        from app.models.proposal import Proposal
        from app.models.proposal_participant import ProposalParticipant
        from app.services.proposal_participant_sync import get_proposal_participant_update_values

        self.f.move()
        other_proposal = Proposal(code='OTHER', name='Otra propuesta de prueba', is_active=True)
        self.db.add(other_proposal)
        self.db.flush()
        other_stay = ProposalParticipant(person_id=self.f.person.person_id,
            proposal_id=other_proposal.proposal_id, residential_id=self.f.b.residential_id,
            **get_proposal_participant_update_values(self.f.participant))
        other_stay.grupo_familiar = None
        self.db.add(other_stay)
        self.db.commit()
        response = self.client.get(self.url, params={**self.params, 'proposal_id': ''})
        self.assertEqual(response.status_code, 200)
        groups = re.findall(r'<tr[^>]*data-record-group="[^"]+".*?</tr>', response.text, re.S)
        self.assertEqual(len(groups), 2)
        current = self.db.scalar(select(ProposalParticipant).where(
            ProposalParticipant.proposal_id == self.f.proposal.proposal_id,
            ProposalParticipant.valid_until.is_(None)))
        destination = next(row for row in groups if 'Número en propuesta: FE-2026-B-0002' in row)
        self.assertIn(self.f.proposal.name, destination)
        self.assertIn(other_proposal.name, destination)
        issue = next(r for r in self.source.review(proposal_id=None)['findings']
                     if r['rule'] == 'birth_missing' and r['records'][0]['id'] == current.proposal_participant_id)
        detail = self.client.get(self.url, params={**self.params, 'proposal_id': '', 'finding': issue['key']})
        related = re.search(r'<section[^>]+data-record-findings.*?</section>', detail.text, re.S)[0]
        self.assertIn(other_proposal.name, related)
        self.assertIn(self.f.proposal.name, related)
        self.assertNotIn('FE-2026-A-0001', related)
        filtered = self.client.get(self.url, params={**self.params, 'proposal_id': other_proposal.proposal_id})
        filtered_groups = re.findall(r'<tr[^>]*data-record-group="[^"]+".*?</tr>', filtered.text, re.S)
        self.assertEqual(len(filtered_groups), 1)
        self.assertNotIn(self.f.proposal.name, filtered_groups[0])
        self.user.role = 'user'
        self.db.commit()
        response = self.client.get(self.url, params={**self.params, 'proposal_id': ''})
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'data-record-group="{self.f.old.proposal_participant_id}"', response.text)
        self.assertNotIn(f'data-record-group="{other_stay.proposal_participant_id}"', response.text)

    def test_same_number_for_different_people_is_not_merged(self):
        from app.models.person import Person
        from app.models.proposal_participant import ProposalParticipant

        person = Person(nombre='Otra persona', apellido_paterno='Distinta')
        self.db.add(person)
        self.db.flush()
        self.db.add(ProposalParticipant(person_id=person.person_id, proposal_id=self.f.proposal.proposal_id,
            residential_id=self.f.a.residential_id, expediente_num=self.f.old.expediente_num,
            nombre='Otra persona', apellido_paterno='Distinta'))
        self.db.commit()
        page, _ = self.form()
        groups = re.findall(r'<tr[^>]*data-record-group="[^"]+".*?</tr>', page.text, re.S)
        self.assertEqual(len(groups), 2)
        self.assertTrue(any('Otra persona' in row for row in groups))

    def test_current_and_proposal_numbers_are_distinct_and_finalized_is_visible(self):
        from app.models.proposal import Proposal
        from app.models.proposal_participant import ProposalParticipant
        from app.services.proposal_participant_sync import get_proposal_participant_update_values
        from app.services import data_validation as service

        self.f.old.expediente_num = 'FE-2025-ERA-0101'
        self.f.participant.expediente_num = 'FE-2025-ERA-0103'
        self.f.participant.nombre = 'Nombre Corregido'
        self.f.participant.apellido_paterno = 'Actual'
        self.f.participant.inicial = None
        self.f.participant.apellido_materno = None
        self.f.person.nombre = 'Nombre desactualizado en Person'
        self.f.proposal.name = '2025-000094-B'
        self.f.proposal.status = 'finalized'
        current_proposal = Proposal(code='NEW', name='2025-000094-C', status='active')
        self.db.add(current_proposal)
        self.db.flush()
        current = ProposalParticipant(person_id=self.f.person.person_id,
            proposal_id=current_proposal.proposal_id, residential_id=self.f.a.residential_id,
            **get_proposal_participant_update_values(self.f.participant))
        current.grupo_familiar = None
        self.db.add(current)
        self.db.commit()
        service.mutate(self.db, self.user, 'revalidate', self.source.filters)
        self.db.commit()
        saved = [(r.issue_key, r.fingerprint, r.revision, r.evidence_json) for r in self.db.scalars(select(DataValidationIssue))]
        original = self.source.review(proposal_id=None)
        fingerprints = {r['key']: r['fingerprint'] for r in original['findings']}
        params = {**self.params, 'proposal_id': ''}
        response = self.client.get(self.url, params=params)
        self.assertEqual(response.status_code, 200, response.text)
        rows = re.findall(r'<tr[^>]*data-record-group="[^"]+".*?</tr>', response.text, re.S)
        self.assertEqual(len(rows), 1, 'One current person must not repeat because proposal numbers changed')
        old_row = rows[0]
        self.assertIn('Expediente actual', old_row)
        self.assertIn('<strong>FE-2025-ERA-0103</strong>', old_row)
        first_cell = old_row.split('</td>', 1)[0]
        self.assertIn('Nombre Corregido Actual', first_cell)
        self.assertNotIn('Ana Prueba', first_cell)
        self.assertNotIn('Nombre desactualizado en Person', old_row)
        self.assertIn('Nombre en propuesta: Ana Prueba', old_row)
        self.assertIn('Número en propuesta: FE-2025-ERA-0101', old_row)
        self.assertIn('Propuesta finalizada', old_row)
        self.assertNotIn('Inscripción vigente', old_row)
        self.assertIn('Número en propuesta: FE-2025-ERA-0103', old_row)
        self.assertIn('Propuesta activa', old_row)
        issue = next(r for r in original['findings'] if r['rule'] == 'missing_grupo_familiar'
                     and r['records'][0]['id'] == self.f.old.proposal_participant_id)
        detail = self.client.get(self.url, params={**params, 'finding': issue['key']})
        dialog = re.search(r'<dialog[^>]+id="dq-detail".*?</dialog>', detail.text, re.S)[0]
        for label in ('Expediente actual', 'FE-2025-ERA-0103', 'Nombre Corregido Actual',
                      'Nombre en propuesta: Ana Prueba', 'Número en propuesta: FE-2025-ERA-0101', 'Propuesta finalizada'):
            self.assertIn(label, dialog)
        self.assertEqual(self.f.old.expediente_num, 'FE-2025-ERA-0101')
        self.assertEqual(self.f.old.nombre, 'Ana')
        self.assertEqual(self.f.old.apellido_paterno, 'Prueba')
        self.assertEqual(self.f.participant.expediente_num, 'FE-2025-ERA-0103')
        self.assertEqual(saved, [(r.issue_key, r.fingerprint, r.revision, r.evidence_json)
                                for r in self.db.scalars(select(DataValidationIssue))])
        self.assertEqual(fingerprints, {r['key']: r['fingerprint'] for r in self.source.review(proposal_id=None)['findings']})

    def test_historical_number_is_preserved_and_current_number_respects_scope(self):
        self.f.move()
        self.f.participant.nombre = 'Nombre privado del destino'
        self.db.commit()
        response = self.client.get(self.url, params=self.params)
        old_row = re.search(rf'<tr[^>]*data-record-group="{self.f.old.proposal_participant_id}".*?</tr>', response.text, re.S)[0]
        self.assertIn('Expediente actual', old_row)
        self.assertIn('FE-2026-B-0002', old_row)
        self.assertIn('Nombre privado del destino', old_row.split('</td>', 1)[0])
        self.assertIn('Nombre en propuesta: Ana Prueba', old_row)
        self.assertIn('Número en propuesta: FE-2026-A-0001', old_row)
        self.assertIn('Histórico · solo consulta', old_row)
        self.user.role = 'user'
        self.db.commit()
        response = self.client.get(self.url, params=self.params)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('Expediente actual no disponible', response.text)
        self.assertIn('FE-2026-A-0001', response.text)
        self.assertNotIn('FE-2026-B-0002', response.text)
        self.assertNotIn('Nombre privado del destino', response.text)
        self.assertIn('Nombre en propuesta: Ana Prueba', response.text)

    def test_historical_stay_is_separate_even_when_proposal_number_matches_current(self):
        self.f.move()
        self.f.old.expediente_num = self.f.participant.expediente_num
        self.db.commit()
        response = self.client.get(self.url, params=self.params)
        self.assertEqual(response.status_code, 200)
        rows = re.findall(r'<tr[^>]*data-record-group="[^"]+".*?</tr>', response.text, re.S)
        self.assertEqual(len(rows), 2, 'A historical stay must not merge into the current file')
        historical = next(row for row in rows if f'data-record-group="{self.f.old.proposal_participant_id}"' in row)
        self.assertIn('Histórico · solo consulta', historical)

    def test_reused_proposal_number_never_merges_two_distinct_current_people(self):
        from app.models.person import Person
        from app.models.proposal import Proposal
        from app.models.proposal_participant import ProposalParticipant
        from app.services.proposal_participant_sync import get_proposal_participant_update_values

        # Ana kept 0001 in the old proposal, but now uses 0003. Bruno now uses 0001.
        self.f.participant.expediente_num = 'FE-2026-A-0003'
        self.f.participant.exp_seq4 = '0003'
        self.db.flush()
        self.f.other.expediente_num = 'FE-2026-A-0001'
        self.f.other.residential_id = self.f.a.residential_id
        self.f.other.nombre = 'Bruno'
        self.f.other.apellido_paterno = 'Actual'
        person = Person(legacy_participant_id=self.f.other.participant_id,
                        nombre='Bruno', apellido_paterno='Actual')
        current_proposal = Proposal(code='NEW', name='Propuesta actual', status='active')
        self.f.proposal.status = 'finalized'
        self.db.add_all([person, current_proposal]); self.db.flush()
        older = ProposalParticipant(person_id=person.person_id, proposal_id=self.f.proposal.proposal_id,
            residential_id=self.f.a.residential_id, **get_proposal_participant_update_values(self.f.other))
        older.expediente_num = 'FE-2026-A-0009'
        self.db.add(older)
        for identity, participant in ((self.f.person, self.f.participant), (person, self.f.other)):
            self.db.add(ProposalParticipant(person_id=identity.person_id,
                proposal_id=current_proposal.proposal_id, residential_id=self.f.a.residential_id,
                **get_proposal_participant_update_values(participant)))
        self.db.commit()
        response = self.client.get(self.url, params={**self.params, 'proposal_id': ''})
        self.assertEqual(response.status_code, 200)
        rows = re.findall(r'<tr[^>]*data-record-group="[^"]+".*?</tr>', response.text, re.S)
        self.assertEqual(len(rows), 2)
        ana = next(row for row in rows if 'Ana Prueba' in row.split('</td>', 1)[0])
        bruno = next(row for row in rows if 'Bruno Actual' in row.split('</td>', 1)[0])
        self.assertIn('<strong>FE-2026-A-0003</strong>', ana)
        self.assertIn('<strong>FE-2026-A-0001</strong>', bruno)
        self.assertNotIn('Bruno Actual', ana)
        self.assertNotIn('Ana Prueba', bruno)
        self.assertIn('Número en propuesta: FE-2026-A-0001', ana)
        self.assertIn('Número en propuesta: FE-2026-A-0003', ana)
        self.assertIn('Número en propuesta: FE-2026-A-0009', bruno)
        self.assertIn('Número en propuesta: FE-2026-A-0001', bruno)
        detail = self.client.get(self.url, params={**self.params, 'proposal_id': '',
            'finding': self.source.issue('birth_missing')['key']})
        related = re.search(r'<section[^>]+data-record-findings.*?</section>', detail.text, re.S)[0]
        self.assertIn('Ana Prueba', related)
        self.assertNotIn('Bruno Actual', related)
        self.assertIn(f'/ui/new-list/{self.f.participant.participant_id}/expediente', detail.text)

    def test_missing_current_link_does_not_invent_a_current_file(self):
        self.f.person.legacy_participant_id = None
        self.db.commit()
        page, _ = self.form()
        self.assertIn('Expediente actual no disponible', page.text)
        self.assertIn(self.f.old.expediente_num, page.text)
        self.assertIn('Nombre en propuesta: Ana Prueba', page.text)

    def test_report_style_month_and_year_selectors_preserve_multiple_months(self):
        response = self.client.get(self.url, params={**self.params, 'months': [9, 10], 'year': 2025})
        self.assertEqual(response.status_code, 200)
        self.assertIn('/static/js/report-proposals.js', response.text)
        self.assertIn('/static/css/report-proposals.css', response.text)
        months = re.search(r'<select[^>]+name="months"[^>]*>.*?</select>', response.text, re.S)[0]
        self.assertIn('multiple', months)
        self.assertIn('data-report-multiselect', months)
        self.assertRegex(months, r'<option value="9" selected>Septiembre</option>')
        self.assertRegex(months, r'<option value="10" selected>Octubre</option>')
        self.assertNotIn('<details class="dq-months"', response.text)
        years = re.search(r'<select[^>]+name="year"[^>]*>.*?</select>', response.text, re.S)[0]
        self.assertIn('<option value="2025" selected>2025</option>', years)

    def test_record_and_activity_views_separate_findings_and_keep_session_errors_together(self):
        from app.models.attendance import Attendance

        for attendance in self.db.scalars(select(Attendance).where(Attendance.session_id == self.f.session.session_id)):
            attendance.attended = False
        self.db.commit()
        records = self.client.get(self.url, params={**self.params, 'view': 'records'})
        self.assertIn('Fecha de nacimiento', records.text)
        self.assertNotIn('Horas de sesión faltantes o inválidas', records.text)
        self.assertNotIn('Sesión sin participaciones confirmadas', records.text)
        activities = self.client.get(self.url, params={**self.params, 'view': 'activities'})
        self.assertEqual(activities.status_code, 200)
        groups = re.findall(r'<tr[^>]*data-session-group="[^"]+".*?</tr>', activities.text, re.S)
        self.assertEqual(len(groups), 1)
        self.assertIn('Horas de sesión faltantes o inválidas', groups[0])
        self.assertIn('Sesión sin participaciones confirmadas', groups[0])
        self.assertNotIn('data-record-group=', activities.text)
        hours = self.source.issue('hours')
        detail = self.client.get(self.url, params={**self.params, 'view': 'activities', 'finding': hours['key']})
        self.assertIn('Todos los hallazgos de esta actividad', detail.text)
        self.assertIn(f'/ui/listado/{self.f.session.session_id}', detail.text)
        legacy = self.client.get(self.url, params={**self.params, 'view': 'findings', 'kind': 'attendance'})
        self.assertIn('data-session-group=', legacy.text)
        empty = self.client.get(self.url, params={**self.params, 'view': 'activities', 'months': 1})
        self.assertNotIn('data-session-group=', empty.text)
        self.assertIn('No hay hallazgos', empty.text)

    def test_activity_navigation_survives_filter_forms_assignment_and_invalid_submission(self):
        from urllib.parse import parse_qs, urlsplit

        response, form = self.form()
        hours = self.source.issue('hours')
        params = {**self.params, 'months': [9, 10], 'view': 'activities', 'status': 'all'}
        page = self.client.get(self.url, params=params)
        for markup in re.findall(r'<form.*?</form>', page.text, re.S):
            self.assertIn('name="view" value="activities"', markup)
            self.assertIn('name="months"', markup)
        data = {**form, **params, 'targets': hours['token'], 'assignee': 'residential', 'due_on': 'bad'}
        invalid = self.client.post(self.url + '/assign', data=data)
        self.assertEqual(invalid.status_code, 422)
        self.assertIn('name="view" value="activities"', invalid.text)
        result = self.client.post(self.url + '/assign', data={**data, 'due_on': '2099-11-18'}, follow_redirects=False)
        self.assertEqual(result.status_code, 303)
        query = parse_qs(urlsplit(result.headers['location']).query)
        self.assertEqual(query['view'], ['activities'])
        self.assertEqual(query['months'], ['9', '10'])
        self.assertEqual(query['status'], ['all'])
        updated = self.client.get(result.headers['location'])
        self.assertIn('En revisión', updated.text)
        self.assertNotIn('data-record-group=', updated.text)
        revalidated = self.client.post(self.url + '/revalidate', data={**form, **params}, follow_redirects=False)
        self.assertEqual(parse_qs(urlsplit(revalidated.headers['location']).query)['view'], ['activities'])

    def test_residential_navigation_and_scoped_activity_access(self):
        from html import unescape

        overview = self.client.get(self.url, params={**self.params, 'view': 'residentials'})
        links = re.findall(r'href="([^"]+)"[^>]*>Ver (expedientes|actividades)</a>', overview.text)
        self.assertEqual({label for _, label in links}, {'expedientes', 'actividades'})
        for link, label in links:
            response = self.client.get(unescape(link))
            self.assertEqual(response.status_code, 200)
            self.assertIn('data-record-group=' if label == 'expedientes' else 'data-session-group=', response.text)
        self.user.role = 'user'
        self.db.commit()
        activities = self.client.get(self.url, params={**self.params, 'view': 'activities'})
        self.assertEqual(activities.status_code, 200)
        self.assertIn('Mi residencial', activities.text)
        self.assertEqual(self.client.get(self.url, params={**self.params, 'view': 'activities',
            'residential_id': self.f.b.residential_id}).status_code, 403)
        self.user.role = 'viewer'
        self.db.commit()
        readonly = self.client.get(self.url, params={**self.params, 'view': 'activities'})
        self.assertNotIn('data-bulk', readonly.text)
        self.assertNotIn('Revalidar datos', readonly.text)

    def test_activity_pagination_keeps_session_errors_on_the_same_page(self):
        from app.models.activity_session import ActivitySession

        for index in range(26):
            self.db.add(ActivitySession(control_number=f'QA-{index:02}',
                session_date=date(2026, 9, 15), proposal_id=self.f.session.proposal_id,
                residential_id=self.f.a.residential_id, activity_code_id=self.f.session.activity_code_id,
                employee_id=self.f.session.employee_id, hours=None))
        self.db.commit()
        seen = set()
        for page_number, expected_count in ((1, 25), (2, 2)):
            response = self.client.get(self.url, params={**self.params, 'view': 'activities', 'page': page_number})
            rows = re.findall(r'<tr[^>]*data-session-group="([^"]+)".*?</tr>', response.text, re.S)
            self.assertEqual(len(rows), expected_count)
            self.assertFalse(seen.intersection(rows))
            seen.update(rows)
            for row in re.findall(r'<tr[^>]*data-session-group="[^"]+".*?</tr>', response.text, re.S):
                if 'QA-' in row:
                    self.assertIn('Horas de sesión faltantes o inválidas', row)
                    self.assertIn('Sesión sin participaciones confirmadas', row)

    def test_mutations_csrf_permissions_and_audit(self):
        _,form=self.form()
        data={**form,'assignee':'residential','due_on':'2099-11-18','note':'Prueba <script>alert(1)</script>'}
        self.assertEqual(self.client.post(self.url+'/assign',data={**data,'csrf_token':'bad'}).status_code,403)
        result=self.client.post(self.url+'/assign',data=data,follow_redirects=False)
        self.assertEqual(result.status_code,303,result.text)
        issue=self.db.scalars(select(DataValidationIssue)).one()
        detail=self.client.get(self.url,params={**self.params,'finding':issue.issue_key})
        self.assertIn('&lt;script&gt;',detail.text)
        self.assertNotIn('<script>alert(1)</script>',detail.text)
        self.assertEqual(self.client.post(self.url+'/assign',data=data).status_code,409)
        self.user.role='viewer';self.db.commit()
        self.assertEqual(self.client.post(self.url+'/revalidate',data=form).status_code,403)
        self.assertNotIn('data-bulk',self.client.get(self.url,params=self.params).text)

    def test_revoked_session_and_both_application_permissions_required(self):
        self.client.get('/test/login');self.user.session_version+=1;self.db.commit()
        self.assertEqual(self.client.get(self.url,follow_redirects=False).status_code,303)
        for permission in (ACCESS_AUTOMATION,ACCESS_FARO):
            self.client.get('/test/login')
            perm=self.db.scalar(select(PlatformPermission).where(PlatformPermission.key==permission))
            perm.is_active=False;self.db.commit()
            self.assertEqual(self.client.get(self.url,follow_redirects=False).status_code,403)
            perm.is_active=True;self.db.commit()

    def test_facilitator_scope_and_forged_issue_are_rejected(self):
        _,form=self.form()
        self.user.role='user';self.db.commit()
        self.assertEqual(self.client.get(self.url,params={**self.params,'residential_id':self.f.b.residential_id}).status_code,403)
        page=self.client.get(self.url,params=self.params)
        self.assertEqual(page.status_code,200,page.text)
        self.assertNotIn(self.f.b.name+'</option>',page.text)
        self.assertEqual(self.client.post(self.url+'/justify',data={**form,'note':'test'}).status_code,403)
        self.assertEqual(self.client.post(self.url+'/assign',data={**form,'targets':'forged','assignee':'residential','due_on':'2099-11-18'}).status_code,409)
        self.assertEqual(self.db.scalars(select(DataValidationEvent)).all(),[])

    def test_proposal_with_validation_audit_cannot_be_deleted(self):
        from unittest.mock import patch
        from app.api.routes import admin
        from app.models.monthly_attendance import AttendanceMonth
        from app.models.notification import FaroAnnouncement
        Base.metadata.create_all(self.f.engine,tables=[FaroAnnouncement.__table__,AttendanceMonth.__table__])
        _,form=self.form()
        self.client.post(self.url+'/revalidate',data=form)
        with patch.object(admin,'verify_password',return_value=True):
            response=admin.admin_delete_proposal(self.f.proposal.proposal_id,admin_password='test',
                delete_confirmation='ELIMINAR',db=self.db,current_user=self.user)
        self.assertEqual(response.status_code,303)
        self.assertIn('validaci%C3%B3n',response.headers['location'])
        self.assertTrue(self.db.scalars(select(DataValidationEvent)).all())

    def enable_expediente_routes(self):
        from unittest.mock import patch
        from fastapi import Depends
        from app.api.routes import ui
        from app.core.residential_scope import require_faro_access

        self.client.app.include_router(ui.router, prefix='/ui', dependencies=[Depends(require_faro_access)])
        connection = self.db.connection().connection.driver_connection
        connection.create_function('year', 1, lambda value: date.fromisoformat(value).year if value else None)
        connection.create_function('month', 1, lambda value: date.fromisoformat(value).month if value else None)
        community = patch.object(ui.settings, 'COMMUNITY_ENABLED', False)
        community.start()
        self.addCleanup(community.stop)

    def finding_links(self, finding, label):
        from html import unescape

        detail = self.client.get(self.url, params={**self.params, 'finding': finding['key']})
        self.assertEqual(detail.status_code, 200, detail.text)
        links = re.findall(r'href="([^"]+)"[^>]*>' + re.escape(label) + r'</a>', detail.text)
        self.assertTrue(links, detail.text)
        return [unescape(link) for link in links]

    def test_open_record_from_finding_reaches_real_expediente_for_each_role(self):
        self.enable_expediente_routes()
        for role in ('admin', 'supervisor', 'user', 'viewer'):
            with self.subTest(role=role):
                self.user.role = role
                self.db.commit()
                self.assertEqual(self.client.get(self.url, params=self.params).status_code, 200)
                link, = self.finding_links(self.source.issue('birth_missing'), 'Abrir expediente')
                response = self.client.get(link)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn(self.f.participant.expediente_num, response.text)
                if role in ('user', 'viewer'):
                    foreign = self.client.get(f'/ui/new-list/{self.f.other.participant_id}/expediente')
                    self.assertEqual(foreign.status_code, 403)

    def test_duplicate_comparison_links_open_both_real_records(self):
        from app.models.person import Person
        from app.models.proposal_participant import ProposalParticipant

        self.enable_expediente_routes()
        self.f.old.fecha_nacimiento = date(2010, 4, 12)
        person = Person(legacy_participant_id=self.f.other.participant_id, nombre='Ana', apellido_paterno='Prueba')
        self.db.add(person)
        self.db.flush()
        self.db.add(ProposalParticipant(person_id=person.person_id, proposal_id=self.f.proposal.proposal_id,
            residential_id=self.f.b.residential_id, nombre='Ana', apellido_paterno='Prueba',
            fecha_nacimiento=date(2010, 4, 12), genero='F', expediente_num=self.f.other.expediente_num))
        self.db.commit()
        records = self.client.get(self.url, params={**self.params, 'view': 'records', 'kind': 'duplicate'})
        self.assertIn('Comparar', records.text)
        self.assertNotIn('data-record-group=', records.text)
        activities = self.client.get(self.url, params={**self.params, 'view': 'activities'})
        self.assertNotIn('>Comparar</a>', activities.text)
        links = self.finding_links(self.source.issue('duplicate'), 'Consultar expediente')
        self.assertEqual(len(links), 2)
        for link, record in zip(links, (self.f.participant, self.f.other)):
            response = self.client.get(link)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn(record.expediente_num, response.text)

    def test_historical_finding_opens_readonly_history_in_origin(self):
        self.enable_expediente_routes()
        self.f.move()
        self.user.role = 'user'
        self.db.commit()
        self.form()
        link, = self.finding_links(self.source.issue('birth_missing'), 'Consultar historial')
        response = self.client.get(link)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('FE-2026-A-0001', response.text)
        self.assertIn('Solo lectura', response.text)
        self.assertNotIn('FE-2026-B-0002', response.text)
        self.assertNotIn('/edit', response.text)
