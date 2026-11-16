"""General spelling suggestions must be confirmed and preserve query meaning."""
import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from tests import test_farogpt_reports as fixtures
from app.services import farogpt_spelling, farogpt_reports


class SpellingProposalTests(unittest.TestCase):
    def test_unlisted_insertions_omissions_replacements_and_transpositions(self):
        vocabulary = [phrase for aliases in farogpt_reports.ALIASES.values() for phrase in aliases]
        for word in ('participantes', 'actividades', 'confirmaciones', 'expedientes', 'embarazos'):
            variants = (word[:3] + word[4:], word[:3] + 'z' + word[3:],
                        word[:3] + 'z' + word[4:], word[:3] + word[4] + word[3] + word[5:])
            for variant in variants:
                with self.subTest(word=word, variant=variant):
                    self.assertIn(word, farogpt_spelling.propose(variant, vocabulary))

    def test_input_and_output_stay_bounded(self):
        self.assertEqual(farogpt_spelling.propose('x' * 801, ['notas']), [])
        alternatives = farogpt_spelling.propose('juio juio juio', ['junio', 'julio'])
        self.assertEqual(len(alternatives), 3)
        self.assertTrue(all(len(value) <= 800 for value in alternatives))


class FaroGPTSpellingTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.FaroGPTExpandedReportsTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_multiple_unlisted_typos_are_corrected_in_one_question(self):
        response = self.f.ask('cuatnos participntes no duplciados en juino 2026')
        self.assertEqual(response['type'], 'clarification')
        self.assertNotIn('value', response)
        corrected = 'cuantos participantes no duplicados en junio 2026'
        self.assertIn(corrected, response['suggestions'])
        result = self.f.result(corrected, context=response['context'])
        self.assertEqual(result['context']['metric'], 'no_duplicado')
        self.assertEqual(result['value'], 1)
        self.assertEqual(result['period'], 'Junio 2026')

    def test_missing_period_and_typo_followup_keep_field_and_scope(self):
        first = self.f.ask('notsa A R1 propuesta 1')
        self.assertIn('notas A R1 propuesta 1', first['suggestions'])
        pending = self.f.ask(first['suggestions'][0], context=first['context'])
        self.assertIn('mes o meses', pending['message'])
        correction = self.f.ask('juilo 2026', context=pending['context'])
        self.assertEqual(correction['context'], pending['context'])
        self.assertIn('julio 2026', correction['suggestions'])
        result = self.f.result('julio 2026', context=correction['context'])
        self.assertEqual(result['context']['metric'], 'notes')
        self.assertEqual(result['context']['field'], 'A')
        self.assertEqual(result['context']['proposal_id'], 1)
        self.assertEqual(result['context']['residential_id'], 1)

    def test_ambiguous_month_requires_choice_and_does_not_change_known_months(self):
        response = self.f.ask('no duplicados juio 2026')
        self.assertNotIn('value', response)
        self.assertEqual(set(response['suggestions']), {
            'no duplicados junio 2026', 'no duplicados julio 2026'})
        for month in ('junio', 'julio'):
            result = self.f.result(f'no duplicados {month} 2026')
            self.assertEqual(result['context']['month'], 6 if month == 'junio' else 7)

    def test_field_vocabulary_and_accents_preserve_grade(self):
        response = self.f.ask('Notsa A en matemticas julio 2026')
        corrected = 'notas A en matematicas julio 2026'
        self.assertIn(corrected, response['suggestions'])
        result = self.f.result(corrected, context=response['context'])
        self.assertEqual(result['context']['field'], 'math_a')
        self.assertEqual(result['value'], 1)

    def test_names_identifiers_numbers_and_unknown_restrictions_are_preserved(self):
        for question, protected in (
            ('actividdades 2.B.5 agosto 2026 propuesta 006', '2.B.5 agosto 2026 propuesta 006'),
            ('notsa residencial Notaz julio 2026', 'residencial Notaz'),
            ('notsa en Notaz julio 2026', 'en Notaz'),
            ('notsa propuesta Infrome julio 2026', 'propuesta Infrome'),
            ('notsa julio 2026 menores de 18 años', 'menores de 18 años'),
        ):
            with self.subTest(question=question):
                response = self.f.ask(question)
                self.assertNotIn('value', response)
                self.assertTrue(response['suggestions'], response)
                self.assertTrue(all(protected in suggestion for suggestion in response['suggestions']))
        rejected = self.f.ask('notas julio 2026 menores de 18 años')
        self.assertEqual(rejected['type'], 'clarification')
        self.assertNotIn('value', rejected)

    def test_valid_field_question_is_not_rewritten(self):
        result = self.f.result('notas promedio A julio 2026')
        self.assertEqual(result['context']['field'], 'A')

    def test_correction_does_not_bypass_residential_scope(self):
        user = SimpleNamespace(role='supervisor', _active_residential_id=2, username='scoped')
        response = self.f.ask('no duplciados global julio 2026', user=user)
        self.assertNotIn('value', response)
        result = self.f.result(response['suggestions'][0], context=response['context'], user=user)
        self.assertEqual(result['context']['residential_id'], 2)
        self.assertEqual(result['value'], 1)
        with self.assertRaises(HTTPException):
            self.f.ask('no duplciados julio 2026', context={'residential_id': 1}, user=user)
