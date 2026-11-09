import unittest
from datetime import date
from sqlalchemy import select, func
from app.models.activity_code import ActivityCode
from app.models.attendance import Attendance
from app.models.participant_profile_field import ParticipantProfileField
from app.models.participant_profile_field_value import ParticipantProfileFieldValue
from app.models.proposal_participant import ProposalParticipant
from fastapi import Request
from tests import test_participant_transfer_routes as fixtures

class ParticipantHistoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ParticipantTransferRouteTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.f=self.fixture.fixture
        self.client=self.fixture.client
        @self.client.app.get('/_test_history_scope/{residential_id}')
        def scope(residential_id:int,request:Request):
            self.f.actor.role='user' if residential_id else 'admin'
            self.f.actor._active_residential_id=residential_id or None
            if residential_id:request.session['active_residential_id']=residential_id
            else:request.session.pop('active_residential_id',None)
            return {'ok':True}
        field=ParticipantProfileField(field_key='telefono',label='Teléfono histórico',field_type='phone')
        self.f.db.add(field); self.f.db.flush()
        self.phone=ParticipantProfileFieldValue(participant_id=self.f.participant.participant_id,
            participant_profile_field_id=field.participant_profile_field_id,value='(787)-555-0101')
        self.f.db.add(self.phone); self.f.db.commit()
        self.audit=self.f.move()
        self.f.db.commit()
        self.path=f'/ui/new-list/{self.f.participant.participant_id}/history/{self.audit.transfer_id}'
        self.scope(self.f.a.residential_id)

    def scope(self,residential_id):
        self.client.get(f'/_test_history_scope/{residential_id}')

    def test_source_participants_include_readonly_historical_entry(self):
        result=self.client.get('/ui/new-list')
        self.assertEqual(result.status_code,200)
        self.assertIn('FE-2026-A-0001',result.text)
        self.assertIn(self.path,result.text)
        self.assertNotIn(f'/ui/new-list/{self.f.participant.participant_id}/edit',result.text)

    def test_source_can_view_history_without_opening_current_record(self):
        result=self.client.get(self.path)
        self.assertEqual(result.status_code,200)
        self.assertIn('FE-2026-A-0001',result.text)
        self.assertIn('Solo lectura',result.text)
        self.assertIn('2.b.5',result.text)
        self.assertNotIn('FE-2026-B-0002',result.text)
        self.assertEqual(self.client.get(f'/ui/new-list/{self.f.participant.participant_id}/edit').status_code,403)

    def add_attendance(self,residential_id,day,code,attended=True):
        activity=ActivityCode(code=code,description='Servicio '+code)
        self.f.db.add(activity);self.f.db.flush()
        session=self.f.make_session(residential_id,day)
        session.activity_code_id=activity.activity_code_id
        self.f.db.add(Attendance(session_id=session.session_id,participant_id=self.f.participant.participant_id,attended=attended))
        self.f.db.commit()

    def test_source_cannot_see_destination_or_outside_dates_even_with_forged_filters(self):
        self.add_attendance(self.f.a.residential_id,date(2026,9,30),'ORIGEN-ULTIMO')
        self.add_attendance(self.f.b.residential_id,date(2026,10,1),'DESTINO-PRIVADO')
        self.add_attendance(self.f.a.residential_id,date(2026,10,2),'FUERA-ESTANCIA')
        self.add_attendance(self.f.a.residential_id,date(2026,9,29),'AUSENTE',False)
        self.f.participant.nombre='NOMBRE ACTUAL EN BV'
        self.f.participant.edificio='EDIFICIO BV'
        self.phone.value='(787)-999-9999'
        self.f.db.commit()
        response=self.client.get(self.path,params={'participation_from_date':'2000-01-01',
            'participation_to_date':'2099-12-31','residential_id':self.f.b.residential_id})
        self.assertEqual(response.status_code,200)
        for value in ('ORIGEN-ULTIMO','2.b.5','(787)-555-0101'):self.assertIn(value,response.text)
        for value in ('DESTINO-PRIVADO','FUERA-ESTANCIA','AUSENTE','NOMBRE ACTUAL EN BV','EDIFICIO BV','(787)-999-9999'):
            self.assertNotIn(value,response.text)

    def test_all_roles_in_origin_have_readonly_history_and_cannot_modify_current_record(self):
        for role in ('admin','supervisor','user','viewer'):
            self.f.actor.role=role
            with self.subTest(role=role):
                response=self.client.get(self.path)
                self.assertEqual(response.status_code,200)
                self.assertNotIn('Editar participante',response.text)
                self.assertNotIn('/edit',response.text)
                self.assertNotIn('/delete',response.text)
                self.assertNotIn('/ui/listado/',response.text)
                self.assertEqual(self.client.post(self.path,data={'nombre':'Cambio'}).status_code,405)
                self.assertEqual(self.client.get(f'/ui/new-list/{self.f.participant.participant_id}/edit').status_code,403)
                self.assertEqual(self.client.post(f'/ui/new-list/{self.f.participant.participant_id}/delete').status_code,403)
        self.assertEqual(self.f.participant.nombre,'Ana')

    def test_other_residential_and_other_participant_cannot_open_origin_history(self):
        self.scope(self.f.b.residential_id)
        self.assertEqual(self.client.get(self.path).status_code,403)
        self.scope(self.f.a.residential_id)
        self.assertEqual(self.client.get(f'/ui/new-list/{self.f.other.participant_id}/history/{self.audit.transfer_id}').status_code,404)
        self.assertEqual(self.client.get(self.path+'999').status_code,404)
        self.scope(0)
        self.assertEqual(self.client.get(self.path).status_code,200)

    def test_old_transfer_without_profile_copy_does_not_use_current_contact(self):
        self.audit.profile_snapshot_json=None
        self.phone.value='(787)-999-9999'
        self.f.participant.nombre='NOMBRE NUEVO'
        self.f.db.commit()
        response=self.client.get(self.path)
        self.assertEqual(response.status_code,200)
        self.assertIn('no tiene una copia histórica',response.text)
        self.assertNotIn('(787)-999-9999',response.text)
        self.assertNotIn('NOMBRE NUEVO',response.text)
        self.assertIn('Ana',response.text)

    def test_historical_list_filters_original_number_and_does_not_count_as_current(self):
        response=self.client.get('/ui/new-list',params={'expediente_num':' fe-2026-a-0001 '})
        self.assertEqual(response.status_code,200)
        self.assertIn(self.path,response.text)
        self.assertIn('Mostrando 0 de 0 participantes',response.text)
        self.assertNotIn(self.path,self.client.get('/ui/new-list?expediente_num=FE-2026-B-0002').text)
        self.scope(self.f.b.residential_id)
        result=self.client.get('/ui/new-list')
        self.assertIn('FE-2026-B-0002',result.text)
        self.assertNotIn(self.path,result.text)

    def test_returns_and_second_departure_keep_separate_stays(self):
        self.scope(0)
        second=self.f.move(destination_id=self.f.a.residential_id,expected_residential_id=self.f.b.residential_id,effective_date=date(2026,10,10))
        self.f.db.commit()
        self.scope(self.f.a.residential_id)
        current=self.client.get('/ui/new-list')
        self.assertNotIn(self.path,current.text)
        self.assertIn(f'/ui/new-list/{self.f.participant.participant_id}/edit',current.text)
        self.add_attendance(self.f.a.residential_id,date(2026,10,11),'SEGUNDA-ESTANCIA')
        self.scope(0)
        third=self.f.move(expected_residential_id=self.f.a.residential_id,effective_date=date(2026,10,20))
        self.f.db.commit()
        self.scope(self.f.a.residential_id)
        latest=f'/ui/new-list/{self.f.participant.participant_id}/history/{third.transfer_id}'
        result=self.client.get(latest)
        self.assertIn('SEGUNDA-ESTANCIA',result.text)
        self.assertNotIn('2.b.5',result.text)
        self.assertIn(self.path,result.text)
        old=self.client.get(self.path)
        self.assertNotIn('SEGUNDA-ESTANCIA',old.text)
        self.assertIn('2.b.5',old.text)
        self.assertIn(latest,self.client.get('/ui/new-list').text)

    def test_history_pagination_keeps_boundary_and_empty_filters_work(self):
        self.f.db.add_all([Attendance(participant_id=self.f.participant.participant_id,
            session_id=self.f.session.session_id,attended=True) for _ in range(29)])
        self.f.db.commit()
        response=self.client.get(self.path+'?participation_page=2&participation_proposal_id=&participation_from_date=&participation_to_date=')
        self.assertEqual(response.status_code,200)
        self.assertIn('Página 2 de 2',response.text)
        self.assertIn('30 participaciones',response.text)
        self.assertEqual(self.client.get('/ui/new-list?history_page=').status_code,200)
        self.assertEqual(self.client.get(self.path+'?participation_page=abc').status_code,422)

    def test_multiple_proposals_show_one_archived_person(self):
        from app.models.proposal import Proposal
        from app.services.proposal_participant_sync import get_proposal_participant_update_values
        proposal=Proposal(code='006',name='Otra propuesta')
        self.f.db.add(proposal);self.f.db.flush()
        self.f.db.add(ProposalParticipant(person_id=self.f.person.person_id,proposal_id=proposal.proposal_id,
            residential_id=self.f.a.residential_id,valid_until=self.audit.effective_date,
            **get_proposal_participant_update_values(self.f.old)))
        self.f.db.commit()
        from app.services.participant_history import residential_history_page
        result=residential_history_page(self.f.db,self.f.a.residential_id)
        self.assertEqual(result['total'],1)
        self.assertEqual(len(result['rows']),1)

    def test_historical_list_pagination_preserves_filters_and_original_date_of_birth(self):
        from app.models.participant import Participant
        from app.models.person import Person
        from app.services.proposal_participant_sync import get_proposal_participant_update_values
        from app.services.participant_history import residential_history_page
        self.scope(0)
        other=Participant(residential_id=self.f.a.residential_id,nombre='Bea',apellido_paterno='Zeta',
            expediente_num='FE-2026-A-0010',exp_year=2026,exp_seq4='0010',fecha_nacimiento=date(2010,6,1))
        self.f.db.add(other);self.f.db.flush()
        person=Person(legacy_participant_id=other.participant_id,nombre=other.nombre,apellido_paterno=other.apellido_paterno)
        self.f.db.add(person);self.f.db.flush()
        self.f.db.add(ProposalParticipant(person_id=person.person_id,proposal_id=self.f.proposal.proposal_id,
            residential_id=self.f.a.residential_id,**get_proposal_participant_update_values(other)))
        self.f.db.commit()
        audit=self.f.move(participant_id=other.participant_id)
        other.fecha_nacimiento=date(2020,1,1)
        self.f.db.commit()
        self.scope(self.f.a.residential_id)
        first=residential_history_page(self.f.db,self.f.a.residential_id,per_page=1)
        last=residential_history_page(self.f.db,self.f.a.residential_id,page=99,per_page=1)
        self.assertEqual((first['total'],first['pages'],last['page']),(2,2,2))
        self.assertEqual(first['rows'][0]['audit'].transfer_id,self.audit.transfer_id)
        self.assertEqual(last['rows'][0]['audit'].transfer_id,audit.transfer_id)
        original_age=residential_history_page(self.f.db,self.f.a.residential_id,
            born_before=date(2011,1,1),born_after=date(2009,1,1))
        self.assertEqual(original_age['total'],1)
        self.assertEqual(original_age['rows'][0]['audit'].transfer_id,audit.transfer_id)
        page=self.client.get('/ui/new-list?per_page=1&history_page=2')
        self.assertEqual(page.status_code,200)
        self.assertIn('Página 2 de 2',page.text)
        self.assertIn('FE-2026-A-0010',page.text)
        self.assertNotIn('FE-2026-A-0001',page.text)

    def test_foreign_residential_filter_cannot_expose_archives(self):
        self.scope(self.f.b.residential_id)
        response=self.client.get('/ui/new-list',params={'residential_id':self.f.a.residential_id})
        self.assertEqual(response.status_code,200)
        self.assertNotIn(self.path,response.text)
        self.assertNotIn('FE-2026-A-0001',response.text)

    def test_snapshot_text_is_escaped(self):
        import json
        data=json.loads(self.audit.profile_snapshot_json)
        data['fields'][0]['value']='<script>alert("x")</script>'
        self.audit.profile_snapshot_json=json.dumps(data)
        self.f.db.commit()
        response=self.client.get(self.path)
        self.assertIn('&lt;script&gt;',response.text)
        self.assertNotIn('<script>alert(',response.text)

if __name__=='__main__':unittest.main()
