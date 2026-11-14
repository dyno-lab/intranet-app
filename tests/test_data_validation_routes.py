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
