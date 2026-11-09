import os
import unittest
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

for key, value in {'DB_SERVER':'test-server', 'DB_NAME':'test-db', 'DB_USER':'test-user',
                   'DB_PASSWORD':'test-password', 'SESSION_SECRET':'certification-tests-only-secret-at-least-32-characters'}.items():
    os.environ.setdefault(key, value)

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from openpyxl import load_workbook
from pypdf import PdfReader
from app.api.routes import reports, certification
from app.api.deps import get_db
from app.core.auth import get_current_user
from app.services.certification_report import build_certification_report, require_exportable, _totals
from app.services.certification_exports import certification_pdf, certification_excel, certification_pages
import test_full_monthly_report_data as fixtures


class CertificationReportTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
        self.fixture = fixtures.FullMonthlyReportDataTests()
        with patch.object(fixtures, 'create_engine', return_value=engine):
            self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db = self.fixture.db
        self.tables = self.fixture.tables
        self.user = SimpleNamespace(role='admin', username='admin', user_id=1, residential_id=None)
        self.db.execute(self.tables['proposal_report_programs'].update().values(code='1A'))
        self.db.commit()

    def build(self, **overrides):
        args = dict(selected_proposals=[1,2], month=7, year=2026, employee_id=0, authorized_name='Facilitador de prueba')
        args.update(overrides)
        return build_certification_report(self.db, self.user, **args)

    def client(self):
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key='tests-only')
        app.include_router(certification.router, prefix='/ui/reports')
        app.include_router(reports.router, prefix='/ui/reports')
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: self.user
        return TestClient(app)

    def test_catalog_and_confirmed_counts_match_bonafide(self):
        self.assertIn({'value':'certificacion', 'label':'Certificación'}, reports.REPORT_OPTIONS)
        data = self.build()
        self.assertEqual(data['people_count'], 2)
        self.assertEqual(len(data['rows']), 3)
        self.assertEqual(data['totals'], {'1A':3,'2B':0,'3C':0,'4D':0,'total':3,'vca':0,'unclassified':0})
        self.assertEqual([s['totals']['total'] for s in data['sections']], [2,1])
        for residence in (-1,-2):
            certification_data = self.build(employee_id=residence)
            bonafide = reports._build_bonafide_context(self.db, self.user, [1,2], 7, 2026, residence)
            self.assertEqual([r['expediente'] for r in certification_data['rows']], [r['expediente'] for r in bonafide['rows']])

    def test_program_comes_from_each_proposal_configuration_not_activity_prefix(self):
        table = self.tables['proposal_report_programs']
        self.db.execute(table.update().where(table.c.program_id==2).values(code='2-B'))
        self.assertEqual({k:self.build()['totals'][k] for k in ('1A','2B','total')}, {'1A':2,'2B':1,'total':3})

    def test_repeated_population_mapping_does_not_multiply_attendances(self):
        self.fixture.insert('proposal_report_program_populations', program_population_id=3, program_id=1,
                            population_group_id=1, is_active=True)
        self.fixture.insert('proposal_report_program_population_activity_codes', program_population_id=3, activity_code_id=10)
        self.assertEqual(self.build()['totals']['1A'], 3)

    def test_legacy_assignments_apply_only_without_active_population_structure(self):
        self.fixture.insert('proposal_report_program_activities',program_activity_id=8,program_id=1,code='legacy',is_active=True)
        self.fixture.insert('proposal_report_program_activity_codes',program_activity_id=8,activity_code_id=10)
        self.assertEqual(self.build()['totals']['total'],3)
        populations=self.tables['proposal_report_program_populations']
        self.db.execute(populations.update().where(populations.c.program_id==1).values(is_active=False))
        self.assertEqual(self.build()['totals']['1A'],3)
        self.assertFalse(self.build()['issues'])

    def test_all_queries_compile_for_sql_server(self):
        from sqlalchemy import event
        from sqlalchemy.dialects import mssql
        statements=[]
        def compile_statement(connection, statement, multiparams, params, options):
            statements.append(str(statement.compile(dialect=mssql.dialect())))
        event.listen(self.fixture.engine,'before_execute',compile_statement)
        try:
            self.build()
        finally:
            event.remove(self.fixture.engine,'before_execute',compile_statement)
        self.assertTrue(statements)
        self.assertTrue(all(sql.lstrip().startswith('SELECT') for sql in statements))
        self.assertTrue(any('attendance.attended = 1' in sql for sql in statements))

    def test_unclassified_or_ambiguous_programs_cannot_emit_incomplete_certification(self):
        table=self.tables['proposal_report_programs']
        self.db.execute(table.update().where(table.c.program_id==2).values(is_active=False))
        data=self.build()
        self.assertEqual(data['totals']['unclassified'],1)
        self.assertEqual(data['issues'][0]['activity_code'],'1.a.2')
        with self.assertRaises(HTTPException) as caught: require_exportable(data)
        self.assertEqual(caught.exception.status_code,409)
        self.fixture.insert('proposal_report_programs', program_id=3, proposal_id=1, code='4D', is_active=True)
        self.fixture.insert('proposal_report_program_populations', program_population_id=3, program_id=3, population_group_id=1,is_active=True)
        self.fixture.insert('proposal_report_program_population_activity_codes',program_population_id=3,activity_code_id=10)
        self.assertEqual(self.build()['totals']['unclassified'],3)
        with self.client() as client:
            for suffix in ('/pdf','/pdf/download','/excel'):
                self.assertEqual(client.get('/ui/reports/certificacion'+suffix+'?proposal_id=1&month=7&year=2026&employee_id=0').status_code,409)

    def test_transfer_retains_both_historical_addresses_and_file_numbers(self):
        self.fixture.insert('persons',person_id=1,legacy_participant_id=1)
        for identifier, residential, start, end, apt, number in (
                (1,1,None,date(2026,7,16),'A2','ORIGEN-0080'),
                (2,2,date(2026,7,16),None,'10','DESTINO-0081')):
            self.fixture.insert('proposal_participants',proposal_participant_id=identifier,person_id=1,proposal_id=1,
                residential_id=residential,valid_from=start,valid_until=end,apart=apt,edificio='2',
                expediente_num=number,nombre='Nombre histórico',genero='F',vca='Sí',is_active=True)
        sessions=self.tables['activity_sessions']
        self.db.execute(sessions.update().where(sessions.c.session_id==2).values(proposal_id=1))
        people=self.tables['participants']
        self.db.execute(people.update().where(people.c.participant_id==1).values(residential_id=2,apart='999',expediente_num='ACTUAL'))
        rows={r['residential_id']:r for r in self.build(selected_proposals=[1])['rows'] if r['participant_id']==1}
        self.assertEqual((rows[1]['expediente'],rows[1]['apartamento'],rows[1]['total']),('ORIGEN-0080','A2',1))
        self.assertEqual((rows[2]['expediente'],rows[2]['apartamento'],rows[2]['total']),('DESTINO-0081','10',1))
        self.assertTrue(rows[1]['vca'])

    def test_same_four_roles_with_residential_context_cannot_escape_scope(self):
        for role in ('admin','supervisor','viewer','user'):
            self.user.role=role
            self.user.residential_id=1
            self.user._active_residential_id=1
            with self.subTest(role=role):
                data=self.build(employee_id=-2)
                self.assertEqual([s['residential_id'] for s in data['sections']],[1])
                self.assertFalse(data['can_choose_scope'])
                with self.client() as client:
                    query='?proposal_id=1&proposal_id=2&month=7&year=2026&employee_id=-2&authorized_name=Otro'
                    screen=client.get('/ui/reports/certificacion'+query)
                    self.assertEqual(screen.status_code,200)
                    self.assertIn('Expediente',screen.text)
                    self.assertNotIn('Residencial 2',screen.text)
                    pdf=client.get('/ui/reports/certificacion/pdf'+query)
                    self.assertEqual(pdf.status_code,200)
                    self.assertIn('no-store',pdf.headers['cache-control'])
                    text=''.join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
                    self.assertNotIn('Residencial 2',text)
                    if role=='viewer': self.assertIn('Usuario no autorizado',text)
                    xlsx=client.get('/ui/reports/certificacion/excel'+query)
                    self.assertEqual(xlsx.status_code,200)
                    self.assertIn('attachment;',xlsx.headers['content-disposition'])

    def test_empty_and_invalid_filters_are_controlled(self):
        with self.client() as client:
            for query in ('','?proposal_id=&month=&year=&employee_id='):
                self.assertEqual(client.get('/ui/reports/certificacion'+query).status_code,200)
            for query in ('?proposal_id=1&month=13&year=2026','?proposal_id=x','?month=abc',
                          '?period_type=custom&start_date=2026-08-01&end_date=2026-07-01'):
                self.assertEqual(client.get('/ui/reports/certificacion'+query).status_code,422)
            self.assertEqual(client.get('/ui/reports/certificacion/pdf?proposal_id=&month=&year=').status_code,422)
            self.assertEqual(client.get('/ui/reports/certificacion/pdf?proposal_id=1&month=8&year=2026&employee_id=0').status_code,404)
        data=self.build(period_type='custom',start_date='2026-07-31',end_date='2026-07-31')
        self.assertEqual(data['totals']['total'],1)

    def test_center_redirect_preserves_all_proposals_and_signer(self):
        with self.client() as client:
            for output,suffix in (('screen',''),('pdf','/pdf'),('excel','/excel')):
                response=client.get('/ui/reports/run',params=[('report_key','certificacion'),('proposal_id','1'),('proposal_id','2'),
                    ('month','7'),('year','2026'),('employee_id','0'),('authorized_name','Ana & José'),('output',output)],follow_redirects=False)
                self.assertEqual(response.status_code,303)
                parsed=urlparse(response.headers['location'])
                self.assertEqual(parsed.path,'/ui/reports/certificacion'+suffix)
                self.assertEqual(parse_qs(parsed.query)['proposal_id'],['1','2'])
                self.assertEqual(parse_qs(parsed.query)['authorized_name'],['Ana & José'])

    def test_pdf_two_pages_keep_official_columns_and_cumulative_totals(self):
        data=self.build(employee_id=-1)
        base=data['rows'][0]
        rows=[]
        for index in range(1,73):
            rows.append({**base,'index':index,'nombre':f'Participante de ejemplo {index}', 'expediente':f'EXPEDIENTE-{index}',
                'vca':index in (1,37),'counts':{'1A':2,'2B':0,'3C':1,'4D':0},'total':3,'unclassified':0})
        data['sections'][0]['rows']=rows
        data['rows']=rows
        data['totals']=_totals(rows)
        pages=certification_pages(data)
        self.assertEqual([len(p['entries']) for p in pages],[36,36])
        self.assertEqual([p['totals']['total'] for p in pages],[108,216])
        reader=PdfReader(BytesIO(certification_pdf(data)))
        self.assertEqual(len(reader.pages),2)
        for index,page in enumerate(reader.pages,1):
            self.assertEqual(tuple(page.mediabox),(0,0,612,792))
            text=page.extract_text()
            self.assertIn(f'Página {index} de 2',text)
            self.assertIn('Firma Facilitador de Servicios:',text)
            self.assertNotIn('EXPEDIENTE-',text)
            self.assertTrue(page.images)
        self.assertIn('TOTAL PÁGINA 1-2',reader.pages[1].extract_text())
        self.assertIn('216',reader.pages[1].extract_text())

    def test_long_names_are_wrapped_and_not_lost_at_page_boundary(self):
        data=self.build(employee_id=-1)
        row=data['rows'][0]
        data['sections'][0]['rows']=[{**row,'index':i,'nombre':('María de los Ángeles Rodríguez Sánchez ' * 3)+str(i)} for i in range(1,37)]
        pages=certification_pages(data)
        self.assertGreater(len(pages),1)
        self.assertEqual(sum(len(page['entries']) for page in pages),36)
        self.assertTrue(all(sum(entry[2] for entry in page['entries'])<=522 for page in pages))
        text=''.join(page.extract_text() for page in PdfReader(BytesIO(certification_pdf(data))).pages)
        self.assertIn('Sánchez 36',' '.join(text.split()))

    def test_excel_has_file_numbers_numeric_counts_and_literal_text(self):
        data=self.build(employee_id=-1)
        data['rows'][0]['nombre']='=HYPERLINK("example")'
        sheet=load_workbook(BytesIO(certification_excel(data))).active
        self.assertEqual(sheet['B5'].value,'Expediente')
        self.assertEqual(sheet['B6'].value,'TEST-1')
        self.assertEqual(sheet['C6'].data_type,'s')
        self.assertEqual(sheet['K6'].value,1)
        self.assertEqual(sheet['O8'].value,2)
        self.assertEqual(sheet.print_title_rows,'$1:$5')

    def test_anonymous_request_requires_login(self):
        with self.client() as client:
            del client.app.dependency_overrides[get_current_user]
            response=client.get('/ui/reports/certificacion',follow_redirects=False)
            self.assertIn(response.status_code,(303,401,307))


if __name__=='__main__': unittest.main()
