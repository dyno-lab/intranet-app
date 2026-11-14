import unittest
from datetime import date
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select

from tests.test_participant_transfers import ParticipantTransferTests
from app.models.attendance import Attendance
from app.models.proposal import Proposal
from app.models.proposal_participant import ProposalParticipant
from app.models.residential import Residential
from app.services import farogpt as service


class FaroGPTTests(unittest.TestCase):
    def setUp(self):
        self.f = ParticipantTransferTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.db = self.f.db
        self.user = self.f.actor
        self.f.a.name = 'Arístides Chavier'
        self.f.b.name = 'Bella Vista'
        self.db.commit()

    def ask(self, question, context=None, user=None):
        return service.answer(self.db, user or self.user, question, context or {}, today=date(2026, 11, 14))

    def test_example_real_count_and_exact_report_filters(self):
        result = self.ask('¿Cuántos participantes únicos para septiembre 2026 en residencial chavier?')
        self.assertEqual(result['type'], 'result')
        self.assertEqual(result['value'], 1)
        self.assertEqual(result['context'], dict(metric='people', field=None, month=9, year=2026,
            residential_id=self.f.a.residential_id, proposal_id=None))
        self.assertEqual(result['residential'], 'Arístides Chavier')
        self.assertIn('month=9', result['report_url'])
        self.assertIn('residential_id=', result['report_url'])
        self.assertNotIn('Ana', str(result))

    def test_unique_person_across_sessions_and_proposals_and_absences(self):
        second = self.f.make_session(self.f.a.residential_id, date(2026, 9, 15))
        self.db.add(Attendance(session_id=second.session_id, participant_id=self.f.participant.participant_id,
            proposal_participant_id=self.f.old.proposal_participant_id, attended=True))
        other = Proposal(code='006', name='Otra propuesta', is_active=False)
        self.db.add(other)
        self.db.flush()
        record = ProposalParticipant(person_id=self.f.person.person_id, proposal_id=other.proposal_id,
            residential_id=self.f.a.residential_id, nombre='Ana', apellido_paterno='Prueba')
        self.db.add(record)
        self.db.flush()
        third = self.f.make_session(self.f.a.residential_id, date(2026, 9, 16))
        third.proposal_id = other.proposal_id
        self.db.add(Attendance(session_id=third.session_id, proposal_participant_id=record.proposal_participant_id, attended=True))
        self.db.add(Attendance(session_id=third.session_id, participant_id=self.f.other.participant_id, attended=False))
        self.db.commit()
        self.assertEqual(self.ask('participantes únicos chavier septiembre 2026')['value'], 1)
        self.assertEqual(self.ask('participaciones chavier septiembre 2026')['value'], 3)
        self.assertEqual(self.ask('actividades chavier septiembre 2026')['value'], 3)
        filtered = self.ask('participaciones chavier septiembre 2026 propuesta 006')
        self.assertEqual(filtered['value'], 1)
        self.assertEqual(filtered['proposal'], 'Otra propuesta')

    def test_transfers_keep_the_residential_of_the_service(self):
        self.f.move()
        self.db.flush()
        current = self.db.scalar(select(ProposalParticipant).where(ProposalParticipant.valid_until.is_(None)))
        later = self.f.make_session(self.f.b.residential_id, date(2026, 10, 2))
        self.db.add(Attendance(session_id=later.session_id, proposal_participant_id=current.proposal_participant_id,
            participant_id=self.f.participant.participant_id, attended=True))
        self.db.commit()
        self.assertEqual(self.ask('participantes únicos Chavier septiembre 2026')['value'], 1)
        self.assertEqual(self.ask('participantes únicos Bella Vista septiembre 2026')['value'], 0)
        self.assertEqual(self.ask('participantes únicos Bella Vista octubre 2026')['value'], 1)

    def test_comparison_reuses_filters_and_counts_both_months(self):
        first = self.ask('participantes únicos Chavier septiembre 2026')
        result = self.ask('Compara con agosto de 2026', first['context'])
        self.assertEqual(result['value'], 1)
        self.assertEqual(result['comparison']['value'], 0)
        self.assertEqual(result['comparison']['difference'], 1)
        self.assertEqual(result['context'], first['context'])
        self.assertEqual(result['comparison']['period'], 'Agosto 2026')

    def test_missing_period_is_completed_in_conversation(self):
        pending = self.ask('Cuántos participantes únicos en Chavier')
        self.assertEqual(pending['type'], 'clarification')
        result = self.ask('marzo de 2026', pending['context'])
        self.assertEqual(result['type'], 'result')
        self.assertEqual(result['value'], 0)
        self.assertEqual(result['residential'], 'Arístides Chavier')

    def test_unknown_or_unsupported_filters_never_silently_return_a_total(self):
        for question in ('participantes únicos Residencial Desconocido marzo 2026',
                         'participantes únicos Chavier marzo 2026 menores de 18 años',
                         'participantes únicos Chavier marzo 2026 propuesta 999',
                         'participantes únicos Chavier marzo y abril 2026',
                         'participantes únicos Chavier marzo 2026 mujeres',
                         'participantes únicos Chavier del 5 al 10 de marzo 2026',
                         'asistencias Chavier marzo 2026',
                         'participantes únicos por residencial marzo 2026',
                         'participantes únicos en el residencial marzo 2026',
                         'participantes únicos de la propuesta marzo 2026',
                         'borra todos los participantes',
                         "SELECT * FROM users; DROP TABLE attendance"):
            with self.subTest(question=question):
                result = self.ask(question)
                self.assertEqual(result['type'], 'clarification')
                self.assertNotIn('value', result)

    def test_ambiguous_residential_requires_exact_name(self):
        self.db.add(Residential(code='CH2', name='Chavier Norte', municipality='Ponce', rq_code='CH2'))
        self.db.commit()
        self.assertEqual(self.ask('participantes únicos chavier marzo 2026')['type'], 'clarification')
        self.assertEqual(self.ask('participantes únicos Aristides Chavier septiembre 2026')['value'], 1)

    def test_scoped_supervisor_cannot_escape_active_residential(self):
        scoped = SimpleNamespace(role='supervisor', _active_residential_id=self.f.b.residential_id)
        result = self.ask('participantes únicos septiembre 2026', user=scoped)
        self.assertEqual(result['value'], 0)
        self.assertEqual(result['residential'], 'Bella Vista')
        self.assertEqual(self.ask('participantes únicos Chavier septiembre 2026', user=scoped)['type'], 'clarification')
        with self.assertRaises(HTTPException) as caught:
            service.summary(self.db, scoped, dict(metric='people', field=None, month=9, year=2026,
                residential_id=self.f.a.residential_id, proposal_id=None))
        self.assertEqual(caught.exception.status_code, 403)

    def test_invalid_context_or_missing_roles_never_query_metrics(self):
        for role in ('user', 'viewer', ''):
            with self.subTest(role=role), self.assertRaises(HTTPException):
                self.ask('participantes únicos septiembre 2026', user=SimpleNamespace(role=role))
        with self.assertRaises(HTTPException):
            service.summary(self.db, self.user, dict(metric='people', month=13, year=2026,
                residential_id=None, proposal_id=None))

    def test_legacy_attendance_is_counted_as_participation_not_invented_identity(self):
        self.db.add(Attendance(session_id=self.f.session.session_id,
            participant_id=self.f.other.participant_id, attended=True))
        self.db.commit()
        self.assertEqual(self.ask('participaciones septiembre 2026')['value'], 2)
        self.assertEqual(self.ask('participantes únicos septiembre 2026')['value'], 1)
        self.assertFalse(self.db.new)
        self.assertFalse(self.db.dirty)

    def test_comparison_requires_target_and_handles_january(self):
        first = self.ask('participantes únicos Chavier enero 2026')
        self.assertEqual(self.ask('compara', first['context'])['type'], 'clarification')
        compared = self.ask('compara con el mes anterior', first['context'])
        self.assertEqual(compared['comparison']['period'], 'Diciembre 2025')
        self.assertIn('diciembre de 2025', first['suggestions'][0])

    def test_current_month_and_complete_month_boundaries(self):
        self.f.session.session_date = date(2026, 3, 31)
        self.db.commit()
        self.assertEqual(self.ask('participantes únicos Chavier marzo 2026')['value'], 1)
        self.assertEqual(self.ask('participantes únicos Chavier abril 2026')['value'], 0)
        current = self.ask('actividades en Chavier este mes')
        self.assertEqual(current['period'], 'Noviembre 2026')
        self.assertEqual(current['value'], 0)


if __name__ == '__main__':
    unittest.main()
