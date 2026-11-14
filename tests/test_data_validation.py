import unittest
from datetime import date
from types import SimpleNamespace
from sqlalchemy import select
from fastapi import HTTPException
from tests.test_participant_transfers import ParticipantTransferTests
from app.models.data_validation import DataValidationIssue, DataValidationEvent
from app.models.base import Base
from app.models.proposal_participant import ProposalParticipant
from app.models.person import Person
from app.models.participant import Participant
from app.models.attendance import Attendance
from app.models.participant_profile_field import ParticipantProfileField
from app.services import data_validation as service


class DataValidationTests(unittest.TestCase):
    fixture_class = ParticipantTransferTests

    def setUp(self):
        self.f = self.fixture_class()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.db, self.user = self.f.db, self.f.actor
        Base.metadata.create_all(self.f.engine, tables=[DataValidationIssue.__table__, DataValidationEvent.__table__])
        self.filters = dict(proposal_id=self.f.proposal.proposal_id, residential_id=None,
                            year=2026, months=(9,), today=date(2026,11,14))

    def review(self, **changes):
        return service.review(self.db, self.user, **{**self.filters, **changes})

    def issue(self, rule, **changes):
        return next(row for row in self.review(**changes)['findings'] if row['rule']==rule)

    def test_records_ignore_months_and_get_does_not_write(self):
        september = self.review()
        other = self.review(year=2025, months=(1,2))
        self.assertTrue(any(row['rule']=='birth_missing' for row in other['findings']))
        self.assertFalse(any(row['kind']=='attendance' for row in other['findings']))
        self.assertTrue(any(row['rule']=='hours' for row in september['findings']))
        self.assertEqual(self.db.scalars(select(DataValidationIssue)).all(), [])
        self.assertEqual(self.db.scalars(select(DataValidationEvent)).all(), [])

    def test_all_missing_record_fields_are_detected_together(self):
        labels = {
            'apellido_paterno': 'Primer apellido', 'edificio': 'Edificio', 'apart': 'Apartamento',
            'grupo_familiar': 'Grupo familiar', 'composicion_familiar': 'Composición familiar',
            'relacion_familiar': 'Relación familiar', 'escolaridad_participante': 'Escolaridad del participante',
            'fuente_ingreso_principal': 'Fuente de ingreso principal', 'rango_ingreso': 'Rango de ingreso',
            'vca': 'VCA', 'primera_vez': 'Participa por primera vez', 'estatus': 'Estatus',
        }
        for field in labels:
            setattr(self.f.old, field, '  ')
        self.db.commit()
        findings = {row['rule']: row for row in self.review(year=2025, months=(1,))['findings']}
        for field, label in labels.items():
            with self.subTest(field=field):
                self.assertIn('missing_' + field, findings)
                self.assertEqual(findings['missing_' + field]['title'], label + ' sin registrar')
        self.assertNotIn('missing_inicial', findings)
        self.assertNotIn('missing_apellido_materno', findings)
        self.assertNotIn('missing_is_head_of_household', findings)

    def test_completeness_accepts_zero_no_and_preserves_other_pending_fields(self):
        self.f.old.edificio = '0'
        self.f.old.apart = 'A-02'
        self.f.old.vca = 'NO'
        self.f.old.primera_vez = 'NO'
        self.db.commit()
        service.mutate(self.db, self.user, 'revalidate', self.filters)
        self.db.commit()
        self.f.old.grupo_familiar = '1'
        self.db.commit()
        service.mutate(self.db, self.user, 'revalidate', self.filters)
        self.db.commit()
        findings = {row['rule']: row for row in self.review()['findings']}
        self.assertEqual(findings['missing_grupo_familiar']['status'], 'resolved')
        self.assertEqual(findings['birth_missing']['status'], 'pending')
        for rule in ('missing_edificio', 'missing_apart', 'missing_vca', 'missing_primera_vez'):
            self.assertNotIn(rule, findings)

    def test_missing_location_is_checked_in_each_stay_without_using_current_values(self):
        self.f.old.edificio = None
        self.f.old.apart = None
        self.f.move()
        self.db.commit()
        findings = [r for r in self.review()['findings'] if r['rule'] in {'missing_edificio', 'missing_apart'}]
        self.assertEqual({r['rule'] for r in findings}, {'missing_edificio', 'missing_apart'})
        self.assertTrue(all(r['records'][0]['historical'] for r in findings))
        self.assertTrue(all(r['records'][0]['id'] == self.f.old.proposal_participant_id for r in findings))

    def test_only_confirmed_attendance_and_past_sessions(self):
        self.f.attendance.attended=False
        future=self.f.make_session(self.f.a.residential_id, date(2027,9,1))
        self.db.commit()
        self.assertTrue(any(row['rule']=='no_participations' for row in self.review()['findings']))
        self.assertFalse(any(row['kind']=='attendance' for row in self.review(year=2027)['findings']))

    def test_followup_cannot_close_without_source_correction(self):
        issue=self.issue('birth_missing')
        service.mutate(self.db,self.user,'assign',self.filters,targets=[issue['token']],
                       assignee='residential',due_on=date(2026,11,18),note='Revisar el expediente')
        self.db.commit()
        self.assertEqual(self.issue('birth_missing')['status'],'review')
        service.mutate(self.db,self.user,'revalidate',self.filters)
        self.db.commit()
        self.assertEqual(self.issue('birth_missing')['status'],'review')
        self.f.old.fecha_nacimiento=date(2010,4,12);self.db.commit()
        service.mutate(self.db,self.user,'revalidate',self.filters);self.db.commit()
        self.assertEqual(self.issue('birth_missing')['status'],'resolved')
        self.f.old.fecha_nacimiento=None;self.db.commit()
        self.assertEqual(self.issue('birth_missing')['status'],'pending')

    def test_transfers_keep_sources_and_do_not_create_duplicate_people(self):
        old_attendance_id=self.f.attendance.attendance_id
        self.f.move();self.db.commit()
        findings=self.review()['findings']
        self.assertFalse(any(row['kind']=='duplicate' for row in findings))
        self.assertTrue(any(row['records'] and row['records'][0]['historical'] for row in findings))
        self.assertEqual(self.db.get(Attendance,old_attendance_id).proposal_participant_id,self.f.old.proposal_participant_id)

    def test_duplicate_names_normalize_but_other_proposals_are_not_duplicates(self):
        self.f.old.fecha_nacimiento=date(2010,4,12)
        person=Person(nombre=' ANA ',apellido_paterno='PRUÉBA',fecha_nacimiento=date(2010,4,12))
        self.db.add(person);self.db.flush()
        self.db.add(ProposalParticipant(person_id=person.person_id,proposal_id=self.f.proposal.proposal_id,
            residential_id=self.f.b.residential_id,nombre=' ANA ',apellido_paterno='PRUÉBA',
            fecha_nacimiento=date(2010,4,12),genero='F',expediente_num='DUP-TEST'))
        self.db.commit()
        self.assertEqual(len([r for r in self.review()['findings'] if r['kind']=='duplicate']),1)
        issue=self.issue('duplicate')
        service.mutate(self.db,self.user,'assign',self.filters,targets=[issue['token']],
            assignee='residential',due_on=date(2026,11,18))
        self.db.commit()
        self.assertEqual(self.issue('duplicate')['assignee'],'supervision')
        filtered=self.review(residential_id=self.f.a.residential_id)
        self.assertEqual(filtered['counts']['residentials'],1)
        self.assertEqual([r['id'] for r in filtered['residential_rows']],[self.f.a.residential_id])
        self.user.role='user';self.user._active_residential_id=self.f.a.residential_id
        self.assertFalse(any(r['kind']=='duplicate' for r in self.review()['findings']))

    def test_scope_viewer_csrf_independent_service_guard_and_optional_fields(self):
        self.user.role='user';self.user._active_residential_id=self.f.a.residential_id
        with self.assertRaises(HTTPException):self.review(residential_id=self.f.b.residential_id)
        self.assertFalse(any('apellido_materno'==r['rule'] for r in self.review()['findings']))
        self.user.role='viewer'
        with self.assertRaises(HTTPException):service.mutate(self.db,self.user,'revalidate',self.filters)

    def test_exception_requires_supervisor_reason_and_reopens_on_change(self):
        issue=self.issue('hours')
        with self.assertRaises(HTTPException):
            service.mutate(self.db,self.user,'justify',self.filters,targets=[issue['token']],note=' ')
        service.mutate(self.db,self.user,'justify',self.filters,targets=[issue['token']],note='Evidencia revisada.')
        self.db.commit()
        self.assertEqual(self.issue('hours')['status'],'justified')
        self.f.session.hours=-1;self.db.commit()
        self.assertEqual(self.issue('hours')['status'],'pending')

    def test_stale_followup_and_transaction_rollback(self):
        issue=self.issue('hours')
        kwargs=dict(targets=[issue['token']],assignee='residential',due_on=date(2026,11,18),note='Revisar')
        service.mutate(self.db,self.user,'assign',self.filters,**kwargs);self.db.commit()
        with self.assertRaises(HTTPException):service.mutate(self.db,self.user,'assign',self.filters,**kwargs)
        self.db.rollback()
        current=self.issue('hours')
        service.mutate(self.db,self.user,'justify',self.filters,targets=[current['token']],note='Revisión')
        self.db.rollback()
        self.assertEqual(self.issue('hours')['status'],'review')

    def test_required_custom_field_and_residential_totals(self):
        self.db.add(ParticipantProfileField(field_key='contacto_prueba',label='Contacto requerido',is_required=True))
        self.db.commit()
        self.assertTrue(any(r['rule'].startswith('profile_') for r in self.review()['findings']))
        view=self.review()
        self.assertEqual(view['counts']['open'],sum(r['open'] for r in view['residential_rows']))

    def test_revalidation_does_not_close_other_months(self):
        service.mutate(self.db,self.user,'revalidate',self.filters);self.db.commit()
        before=self.issue('hours')
        service.mutate(self.db,self.user,'revalidate',{**self.filters,'months':(10,)})
        self.db.commit()
        after=self.issue('hours')
        self.assertEqual((after['status'],after['revision']),(before['status'],before['revision']))

    def test_saved_cross_residential_duplicate_is_never_exposed_to_facilitator(self):
        self.f.old.fecha_nacimiento=date(2010,4,12)
        other=Person(nombre='Ana',apellido_paterno='Prueba',fecha_nacimiento=date(2010,4,12))
        self.db.add(other);self.db.flush()
        self.db.add(ProposalParticipant(person_id=other.person_id,proposal_id=self.f.proposal.proposal_id,
            residential_id=None,nombre='Ana',apellido_paterno='Prueba',fecha_nacimiento=date(2010,4,12),
            genero='F',expediente_num='UNASSIGNED-TEST'))
        self.db.commit()
        service.mutate(self.db,self.user,'revalidate',self.filters);self.db.commit()
        self.assertTrue(any(r['kind']=='duplicate' for r in self.review()['findings']))
        self.user.role='user';self.user._active_residential_id=self.f.a.residential_id
        self.assertFalse(any(r['kind']=='duplicate' for r in self.review()['findings']))

    def test_many_records_use_subqueries_instead_of_large_parameter_lists(self):
        participants=[Participant(nombre='Nombre '+str(i),apellido_paterno='Sintético',
            expediente_num='LOAD-'+str(i),residential_id=self.f.a.residential_id) for i in range(2101)]
        self.db.add_all(participants);self.db.flush()
        people=[Person(nombre=p.nombre,apellido_paterno=p.apellido_paterno,legacy_participant_id=p.participant_id) for p in participants]
        self.db.add_all(people);self.db.flush()
        self.db.add_all([ProposalParticipant(person_id=p.person_id,proposal_id=self.f.proposal.proposal_id,
            residential_id=self.f.a.residential_id,nombre=p.nombre,apellido_paterno=p.apellido_paterno,
            genero='F',fecha_nacimiento=date(2010,1,1),expediente_num='TEST-'+str(p.person_id)) for p in people])
        self.db.commit()
        self.assertTrue(self.review()['findings'])
