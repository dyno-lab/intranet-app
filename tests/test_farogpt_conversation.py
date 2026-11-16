"""Guided periods, current proposal selection and bounded typo tolerance."""
import unittest
from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from tests import test_farogpt_activity_codes as fixtures
from app.services import farogpt


class FaroGPTConversationTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.FaroGPTActivityCodeTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.db = self.f.db
        self.user = self.f.f.actor
        self.active = self.f.f.proposal
        self.inactive = self.f.other_proposal

    def ask(self, question, context=None, user=None):
        return farogpt.answer(self.db, user or self.user, question, context or {}, today=date(2026, 11, 14))

    def result(self, question, **kwargs):
        result = self.ask(question, **kwargs)
        self.assertEqual(result['type'], 'result', result)
        return result

    def test_missing_period_asks_months_and_keeps_activity_and_current_proposal(self):
        pending = self.ask('Cuántas act 2.b.5 se hicieron')
        self.assertEqual(pending['type'], 'clarification')
        self.assertIn('mes o meses', pending['message'])
        self.assertIn(self.active.name, pending['message'])
        self.assertEqual(pending['context']['activity_code'], '2.b.5')
        self.assertEqual(pending['context']['proposal_id'], self.active.proposal_id)
        result = self.result('agosto y septiembre de 2026', context=pending['context'])
        self.assertEqual(result['value'], 4)
        self.assertEqual(result['context']['months'], [8, 9])
        self.assertEqual(result['proposal'], self.active.name)
        self.assertEqual(result['tables'][0]['rows'][0][1], 3)
        self.assertEqual(result['tables'][0]['rows'][1][1], 1)

    def test_requested_activity_spellings_are_accepted(self):
        for spelling in ('act', 'ACT.', 'actividadss', 'actididades', 'actvidades', 'actividades', 'atividades'):
            with self.subTest(spelling=spelling):
                self.assertEqual(self.result(f'Cuántas {spelling} 2.b.5 agosto 2026')['value'], 3)

    def test_count_with_tengo_completes_after_june_answer(self):
        self.active.name = '2025-000094-C'
        self.f.f.session.session_date = date(2026, 6, 10)
        self.db.commit()
        pending = self.ask('Cuántos participantes únicos tengo en Chavier')
        self.assertEqual(pending['type'], 'clarification')
        self.assertIn('Propuesta: 2025-000094-C.', pending['message'])
        result = self.result('junio 2026', context=pending['context'])
        self.assertEqual(result['value'], 1)
        self.assertEqual(result['context']['proposal_id'], self.active.proposal_id)
        self.assertEqual(result['context']['residential_id'], self.f.f.a.residential_id)
        self.assertEqual((result['context']['month'], result['context']['year']), (6, 2026))

    def test_named_summary_recovers_from_pending_unsupported_terms(self):
        self.active.name = '2025-000094-C'
        self.f.f.session.session_date = date(2026, 6, 10)
        self.db.commit()
        pending = self.ask('Participantes únicos en Chavier menores de 18 años')
        self.assertEqual(pending['type'], 'clarification')
        rejected = self.ask('junio 2026', context=pending['context'])
        self.assertEqual(rejected['type'], 'clarification')
        self.assertNotIn('value', rejected)
        self.assertEqual(rejected['suggestions'], ['Resumen de Participantes únicos Junio 2026'])
        # A month-only reply must still preserve the unsupported age restriction.
        self.assertEqual(self.ask('junio 2026', context=rejected['context'])['type'], 'clarification')
        # An explicit named summary is a new request, including the bot's own suggestion.
        result = self.result(rejected['suggestions'][0], context=rejected['context'])
        self.assertEqual(result['value'], 1)
        self.assertEqual(result['context']['proposal_id'], self.active.proposal_id)
        self.assertEqual(result['context']['residential_id'], self.f.f.a.residential_id)
        self.assertIsNone(result['context']['pending_terms'])
        self.assertEqual(self.result('Resumen de Participantes únicos Junio 2026',
                                    context=result['context'])['value'], 1)

    def test_summary_recovery_still_validates_new_qualifiers(self):
        pending = self.ask('Participantes únicos en Chavier menores de 18 años')
        rejected = self.ask('junio 2026', context=pending['context'])
        result = self.ask('Resumen de Participantes únicos Junio 2026 mujeres', context=rejected['context'])
        self.assertEqual(result['type'], 'clarification')
        self.assertNotIn('value', result)

    def test_named_summary_can_replace_a_different_pending_report(self):
        pending = self.ask('Actividades en Chavier')
        self.assertEqual(pending['type'], 'clarification')
        result = self.result('Resumen de Participantes únicos Junio 2026', context=pending['context'])
        self.assertEqual(result['context']['metric'], 'people')
        self.assertIsNone(result['context']['field'])
        self.assertEqual(result['context']['residential_id'], self.f.f.a.residential_id)
        self.assertEqual(result['context']['proposal_id'], self.active.proposal_id)

    def test_exact_reported_question_completes_without_rejecting_verb_phrase(self):
        self.f.f.code.code = '1.a.2'
        self.db.commit()
        question = 'Cuantas actividades 1.a.2 se a realizado'
        pending = self.ask(question)
        self.assertEqual(pending['type'], 'clarification')
        self.assertIn('mes o meses', pending['message'])
        self.assertEqual(pending['context']['activity_code'], '1.a.2')
        result = self.result('agosto 2026', context=pending['context'])
        self.assertEqual(result['value'], 3)
        self.assertEqual(result['context']['activity_code'], '1.a.2')
        self.assertEqual(self.result(question, context=result['context'])['value'], 3)

    def test_performed_activity_expressions_accept_correct_and_common_spelling(self):
        self.f.f.code.code = '1.a.2'
        self.db.commit()
        for expression in ('se a realizado', 'se ha realizado', 'se han realizado', 'han realizado',
                           'se ha hecho', 'se han hecho', 'se realizó', 'realizada', 'realizado'):
            with self.subTest(expression=expression):
                result = self.result(f'Cuantas actividades 1.a.2 {expression} en agosto 2026')
                self.assertEqual(result['value'], 3)
                self.assertEqual(result['context']['proposal_id'], self.active.proposal_id)

    def test_verb_tolerance_preserves_unsupported_qualifiers(self):
        for qualifier in ('no se ha realizado', 'se a realizado solo mujeres'):
            with self.subTest(qualifier=qualifier):
                result = self.ask(f'Cuantas actividades 2.b.5 {qualifier} agosto 2026')
                self.assertEqual(result['type'], 'clarification')
                self.assertNotIn('value', result)

    def test_finalized_proposal_is_not_current_even_if_active_flag_is_true(self):
        self.active.status = 'finalized'
        self.inactive.is_active = True
        self.db.commit()
        result = self.result('actividades 2.b.5 agosto 2026')
        self.assertEqual(result['value'], 1)
        self.assertEqual(result['context']['proposal_id'], self.inactive.proposal_id)
        self.assertEqual(self.result('actividades 2.b.5 agosto 2026 propuesta 005')['value'], 3)
        self.assertEqual(self.result('actividades 2.b.5 agosto 2026 todas las propuestas')['value'], 4)

    def test_multiple_current_proposals_ask_instead_of_picking_arbitrarily(self):
        self.inactive.is_active = True
        self.db.commit()
        pending = self.ask('cuántas act 2.b.5 agosto y septiembre 2026')
        self.assertEqual(pending['type'], 'clarification')
        self.assertIn('varias propuestas', pending['message'])
        self.assertNotIn('value', pending)
        self.assertEqual(pending['context']['months'], [8, 9])
        self.assertEqual(self.result('propuesta 006', context=pending['context'])['value'], 1)

    def test_no_current_proposal_does_not_silently_use_historical_records(self):
        self.active.status = 'finalized'
        self.db.commit()
        pending = self.ask('act 2b5 agosto 2026')
        self.assertEqual(pending['type'], 'clarification')
        self.assertIn('No hay una propuesta vigente', pending['message'])
        self.assertEqual(self.result('propuesta 005', context=pending['context'])['value'], 3)

    def test_explicit_proposal_persists_and_can_be_reset_to_current(self):
        first = self.result('act 2b5 agosto 2026 propuesta 006')
        self.assertEqual(self.result('y septiembre', context=first['context'])['value'], 0)
        current = self.result('propuesta vigente', context=first['context'])
        self.assertEqual((current['value'], current['context']['proposal_id']), (3, self.active.proposal_id))

    def test_list_and_range_of_months_are_not_confused(self):
        nonconsecutive = self.result('act 2b5 julio y septiembre 2026')
        self.assertEqual(nonconsecutive['value'], 2)
        self.assertEqual(nonconsecutive['context']['months'], [7, 9])
        inclusive = self.result('act 2b5 de julio a septiembre 2026')
        self.assertEqual(inclusive['value'], 5)
        self.assertEqual(inclusive['context']['months'], [7, 8, 9])
        self.assertEqual(self.ask('act 2b5 de diciembre a enero 2026')['type'], 'clarification')
        self.assertEqual(self.ask('act 2b5 diciembre 2025 y enero 2026')['type'], 'clarification')

    def test_year_is_requested_without_losing_month_selection(self):
        pending = self.ask('act 2b5 agosto y septiembre')
        self.assertEqual(pending['type'], 'clarification')
        self.assertIn('año', pending['message'])
        self.assertEqual(self.result('2026', context=pending['context'])['value'], 4)

    def test_unknown_qualifiers_survive_clarification_instead_of_being_dropped(self):
        pending = self.ask('act 2b5 menores de 18 años')
        result = self.ask('agosto 2026', pending['context'])
        self.assertEqual(result['type'], 'clarification')
        self.assertNotIn('value', result)

    def test_total_unique_people_is_not_sum_of_monthly_unique_counts(self):
        self.f.f.session.session_date = date(2026, 9, 2)
        from app.models.attendance import Attendance
        august = self.f.f.make_session(self.f.f.a.residential_id, date(2026, 8, 2))
        self.db.add(Attendance(session_id=august.session_id, attended=True,
                              participant_id=self.f.f.participant.participant_id,
                              proposal_participant_id=self.f.f.old.proposal_participant_id))
        self.db.commit()
        result = self.result('participantes únicos 2b5 agosto y septiembre 2026')
        self.assertEqual(result['value'], 1)
        self.assertEqual(sum(row[3] for row in result['tables'][0]['rows']), 2)

    def test_month_list_round_trips_and_malformed_filters_fail(self):
        result = self.result('act 2b5 agosto y septiembre 2026')
        self.assertEqual(parse_qs(urlsplit(result['report_url']).query)['months'], ['8', '9'])
        self.assertEqual(farogpt.summary(self.db, self.user, result['context']), result)
        for months in ([0, 8], [8, 13], [], list(range(1, 14))):
            with self.subTest(months=months), self.assertRaises(HTTPException):
                farogpt.summary(self.db, self.user, {'metric': 'activities', 'year': 2026, 'months': months})

    def test_scoped_supervisor_cannot_escape_residential_using_multiple_months(self):
        user = SimpleNamespace(role='supervisor', _active_residential_id=self.f.f.b.residential_id)
        result = self.result('act 2b5 global agosto y septiembre 2026', user=user)
        self.assertEqual(result['value'], 1)
        self.assertEqual(result['context']['residential_id'], self.f.f.b.residential_id)

    def test_year_only_full_year_and_return_to_single_month(self):
        pending = self.ask('act 2b5 2026')
        self.assertEqual(pending['type'], 'clarification')
        self.assertEqual(self.result('agosto', context=pending['context'])['value'], 3)
        full_year = self.result('act 2b5 todo el año 2026')
        self.assertEqual(full_year['context']['months'], list(range(1, 13)))
        single = self.result('y agosto', context=full_year['context'])
        self.assertEqual(single['value'], 3)
        self.assertIsNone(single['context']['months'])

    def test_all_proposals_persist_until_explicit_change(self):
        pending = self.ask('act 2b5 todas las propuestas')
        result = self.result('agosto y septiembre 2026', context=pending['context'])
        self.assertEqual(result['value'], 5)
        self.assertEqual(result['context']['proposal_scope'], 'all')
        current = self.result('propuesta vigente', context=result['context'])
        self.assertEqual(current['value'], 4)
        self.assertEqual(current['context']['proposal_scope'], 'auto')

    def test_multiple_months_and_activity_code_remain_when_comparing(self):
        first = self.result('act 2b5 agosto y septiembre 2026')
        result = self.result('comparar con junio y julio 2026', context=first['context'])
        self.assertEqual(result['comparison']['value'], 1)
        self.assertEqual(result['comparison']['difference'], 3)
        self.assertEqual(result['context'], first['context'])


if __name__ == '__main__':
    unittest.main()
