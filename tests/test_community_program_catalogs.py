"""Program administration and independent defaults copied from Faro."""
import unittest
from types import SimpleNamespace

from sqlalchemy import delete, event, func, select
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session

import test_community_routes as fixture
from app.models.catalog_type import CatalogType
from app.models.catalog_option import CatalogOption
from app.models.community import CPProgram, CPParticipantProgram
from app.models.community_activity import CPActivity
from app.models.community_catalog import CPCatalogType, CPCatalogOption
from app.services.community_catalog import form_catalogs, validate_categories
from app.services.community import create_participant, update_program


class CommunityProgramCatalogTests(unittest.TestCase):
    def setUp(self):
        fixture.CommunityRouteTests.setUp(self)

        def check_mssql(state):
            if state.is_select and state.session.get_bind() is self.engine:
                sql = str(state.statement.compile(dialect=mssql.dialect()))
                self.assertNotRegex(sql, r'\bIS\s+(?:NOT\s+)?(?:[01]\b|TRUE\b|FALSE\b)')
        event.listen(Session, 'do_orm_execute', check_mssql)
        self.addCleanup(event.remove, Session, 'do_orm_execute', check_mssql)

    tearDown = fixture.CommunityRouteTests.tearDown
    token = fixture.CommunityRouteTests.token
    login = fixture.CommunityRouteTests.login
    participant_data = fixture.CommunityRouteTests.participant_data

    def test_program_create_edit_and_delete_persist_municipality(self):
        token = self.login()
        response = self.client.post('/community/programs', data={
            'token': token, 'code': 'TEST', 'name': 'Programa de prueba', 'municipality': 'Mayagüez'})
        self.assertEqual(response.status_code, 303)
        with Session(self.engine) as db:
            program = db.scalar(select(CPProgram).where(CPProgram.code == 'TEST'))
            program_id = program.program_id
            self.assertEqual(program.municipality, 'Mayagüez')
        response = self.client.post(f'/community/programs/{program_id}/edit', data={
            'token': token, 'code': 'TEST-2', 'name': 'Nombre editado', 'municipality': 'San Juan'})
        self.assertEqual(response.status_code, 303)
        page = self.client.get('/community/programs')
        self.assertIn('Nombre editado', page.text)
        with Session(self.engine) as db:
            program = db.get(CPProgram, program_id)
            self.assertEqual((program.code, program.municipality), ('TEST-2', 'San Juan'))
        self.assertEqual(self.client.post(f'/community/programs/{program_id}/delete', data={'token': token}).status_code, 303)
        with Session(self.engine) as db:
            self.assertIsNone(db.get(CPProgram, program_id))

    def test_existing_record_locks_code_but_allows_name_and_town(self):
        token = self.login()
        self.client.post('/community/participants', data=self.participant_data(token))
        path = f'/community/programs/{self.voca_id}/edit'
        response = self.client.post(path, data={'token': token, 'code': 'NEW', 'name': 'Nuevo', 'municipality': 'Ponce'})
        self.assertIn('error=', response.headers['location'])
        response = self.client.post(path, data={'token': token, 'code': 'VOCA', 'name': 'VOCA actualizado', 'municipality': 'Ponce'})
        self.assertNotIn('error=', response.headers['location'])
        with Session(self.engine) as db:
            program = db.get(CPProgram, self.voca_id)
            self.assertEqual((program.code, program.name, program.municipality), ('VOCA', 'VOCA actualizado', 'Ponce'))
            record = db.scalar(select(CPParticipantProgram).where(CPParticipantProgram.program_id == self.voca_id))
            self.assertEqual(record.record_number, 'CP-2026-VOCA-0001')
        response = self.client.post(f'/community/programs/{self.voca_id}/delete', data={'token': token})
        self.assertIn('error=', response.headers['location'])

    def test_cannot_delete_configuration_or_user_assignments(self):
        token = self.login()
        with Session(self.engine) as db:
            db.add(CPActivity(program_id=self.icp_id, code='ACT', code_key='ACT', is_active=False))
            db.commit()
        for program_id in (self.icp_id, self.tanf_id):
            response = self.client.post(f'/community/programs/{program_id}/delete', data={'token': token})
            self.assertEqual(response.status_code, 303)
            self.assertIn('error=', response.headers['location'])
            with Session(self.engine) as db:
                self.assertIsNotNone(db.get(CPProgram, program_id))

    def test_program_writes_validate_csrf_permissions_code_and_town(self):
        token = self.login(self.user_id)
        data = {'token': token, 'code': 'ICP', 'name': 'Alterado', 'municipality': 'Ponce'}
        for action in ('edit', 'delete'):
            self.assertEqual(self.client.post(f'/community/programs/{self.icp_id}/{action}', data=data).status_code, 403)
        data['token'] = self.login()
        response = self.client.post(f'/community/programs/{self.icp_id}/edit', data={**data, 'code': 'voca'})
        self.assertIn('error=', response.headers['location'])
        for path in ('/community/programs', f'/community/programs/{self.icp_id}/edit'):
            response = self.client.post(path, data={**data, 'code': 'TEST', 'municipality': 'No existe'})
            self.assertIn('error=', response.headers['location'])
        for action in ('edit', 'delete'):
            self.assertEqual(self.client.post(f'/community/programs/{self.icp_id}/{action}', data={**data, 'token': 'invalid'}).status_code, 403)
        with Session(self.engine) as db:
            self.assertEqual(db.get(CPProgram, self.icp_id).name, 'Programa ICP')

    def seed_catalogs(self):
        from app.services.community_catalog import seed_community_catalogs
        CatalogType.__table__.create(self.engine)
        CatalogOption.__table__.create(self.engine)
        with Session(self.engine) as db:
            category = CatalogType(key='Relación familiar', name='Relación familiar', is_active=True)
            status = CatalogType(key='estatus_participante', name='Estatus', is_active=True)
            db.add_all([category, status])
            db.flush()
            db.add_all([
                CatalogOption(catalog_type_id=category.catalog_type_id, value='miembro_familia', label='Miembro de familia', sort_order=2),
                CatalogOption(catalog_type_id=category.catalog_type_id, value='jefe_familia', label='Jefe de familia', sort_order=1),
                CatalogOption(catalog_type_id=category.catalog_type_id, value='retirado', label='Retirado', sort_order=0, is_active=False),
                CatalogOption(catalog_type_id=status.catalog_type_id, value='Activo', label='Activo', sort_order=1),
            ])
            existing = CPCatalogType(field_key='relacion_familiar', label='Relación familiar')
            db.add(existing)
            db.flush()
            db.add(CPCatalogOption(catalog_type_id=existing.catalog_type_id, value='miembro_familia'))
            db.flush()
            seed_community_catalogs(db)
            db.commit()

    def test_faro_defaults_keep_values_labels_order_and_status_mapping(self):
        self.seed_catalogs()
        self.login()
        page = self.client.get('/community/participants/new')
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context['catalog_options']['relacion_familiar'], ['jefe_familia', 'miembro_familia'])
        self.assertEqual(page.context['catalog_options']['estatus'], ['Activo'])
        self.assertIn('value="jefe_familia"', page.text)
        self.assertIn('>Jefe de familia</option>', page.text)
        with Session(self.engine) as db:
            validate_categories(db, {'relacion_familiar': 'jefe_familia'})
            with self.assertRaises(ValueError):
                validate_categories(db, {'relacion_familiar': 'retirado'})

    def test_seed_restarts_keep_independent_community_choices(self):
        self.seed_catalogs()
        from app.services.community_catalog import seed_community_catalogs
        with Session(self.engine) as db:
            option = db.scalar(select(CPCatalogOption).where(CPCatalogOption.value == 'jefe_familia'))
            option.is_active = False
            category_id = option.catalog_type_id
            db.add(CPCatalogOption(catalog_type_id=category_id, value='personalizado'))
            db.flush()
            seed_community_catalogs(db)
            db.commit()
            choices = form_catalogs(db)['catalog_options']['relacion_familiar']
            self.assertNotIn('jefe_familia', choices)
            self.assertIn('personalizado', choices)
            validate_categories(db, {'relacion_familiar': 'jefe_familia'}, SimpleNamespace(relacion_familiar='jefe_familia'))

    def test_all_78_municipalities_available_in_participant_and_program_forms(self):
        self.seed_catalogs()
        self.login()
        page = self.client.get('/community/participants/new')
        towns = page.context['catalog_options']['pueblo']
        self.assertEqual(len(towns), 78)
        self.assertEqual(len(set(towns)), 78)
        for town in ('Adjuntas', 'Añasco', 'Ceiba', 'Culebra', 'Loíza', 'Río Grande', 'Vieques', 'Yauco'):
            self.assertIn(town, towns)
        self.assertIn('name="pueblo"', page.text)
        page = self.client.get('/community/programs')
        self.assertEqual(tuple(towns), tuple(page.context['municipalities']))

    def test_program_number_uses_fresh_code_after_context_loaded_old_code(self):
        with Session(self.engine) as db:
            loaded = db.get(CPProgram, self.icp_id)
            self.assertEqual(loaded.code, 'ICP')
            with Session(self.engine) as editor:
                update_program(editor, self.icp_id, 'ICP-NEW', 'ICP', 'Ponce')
                editor.commit()
            participant = create_participant(db, actor_user_id=self.admin_id, exp_year=2026,
                program_ids=[self.icp_id], fields={'nombre': 'Prueba', 'apellido_paterno': 'Prueba', 'genero': 'F'})
            number = db.scalar(select(CPParticipantProgram.record_number).where(
                CPParticipantProgram.participant_id == participant.participant_id))
            self.assertEqual(number, 'CP-2026-ICP-NEW-0001')

    def test_catalog_seed_respects_outer_startup_transaction(self):
        self.seed_catalogs()
        from app.services.community_catalog import seed_community_catalogs
        with self.engine.begin() as conn:
            conn.execute(delete(CPCatalogOption))
            conn.execute(delete(CPCatalogType))
        # Closing the ORM session must not undo the migration's outer transaction.
        for commit in (False, True):
            with self.engine.connect() as conn:
                outer = conn.begin()
                with Session(bind=conn) as db:
                    seed_community_catalogs(db)
                self.assertGreater(conn.scalar(select(func.count()).select_from(CPCatalogOption)), 78)
                outer.commit() if commit else outer.rollback()
            with Session(self.engine) as db:
                count = db.scalar(select(func.count()).select_from(CPCatalogOption))
                self.assertGreater(count, 78) if commit else self.assertEqual(count, 0)


if __name__ == '__main__':
    unittest.main()
