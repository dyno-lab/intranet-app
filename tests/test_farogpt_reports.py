"""Natural language and report-source contracts, using real report fixtures."""
import json
import unittest
from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader, select_autoescape

from tests import test_farogpt_report_followups as fixtures
from app.api.routes import reports
from app.services import farogpt


class FaroGPTExpandedReportsTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.FaroGPTFollowupReportTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.db, self.user = self.f.db, self.f.user

    def ask(self, question, context=None, user=None):
        return farogpt.answer(self.db, user or self.user, question, context or {'proposal_scope': 'all'}, today=date(2026, 11, 14))

    def result(self, question, **kwargs):
        result = self.ask(question, **kwargs)
        self.assertEqual(result['type'], 'result', result)
        return result

    def test_global_aliases_return_union_not_sum_of_residential_uniques(self):
        for scope in ('global', 'todos los residenciales', 'a nivel global', 'a nivel general'):
            with self.subTest(scope=scope):
                result = self.result(f'Cuántos no duplicados {scope} julio 2026')
                self.assertEqual(result['value'], 3)  # Participant 1 occurs in both R1 and R2.
                self.assertEqual(result['context']['metric'], 'no_duplicado')
                self.assertIsNone(result['context']['residential_id'])
                self.assertIn('/ui/reports/no-duplicado?', result['source_url'])
        self.assertEqual(self.result('no duplicados R1 julio 2026')['value'], 3)
        self.assertEqual(self.result('no duplicados R2 julio 2026')['value'], 1)

    def test_global_followup_resets_residential_but_retains_proposal_and_month(self):
        first = self.result('no duplicados R2 julio 2026 propuesta 2')
        result = self.result('Y global', context=first['context'])
        self.assertIsNone(result['context']['residential_id'])
        self.assertEqual(result['context']['proposal_id'], 2)
        self.assertEqual(result['period'], 'Julio 2026')
        self.assertEqual(result['value'], 1)

    def test_every_operational_report_returns_aggregate_cards_and_source(self):
        for label, key in (('ADM', 'adm'), ('notas', 'notes'), ('embarazo', 'pregnancy'),
                           ('desercion', 'dropout'), ('visitas', 'visits'), ('cursos', 'courses'),
                           ('Bonafide', 'bonafide'), ('Certificacion', 'certification'), ('VCA', 'vca'),
                           ('Hoja de Cotejo', 'cotejo'), ('por programa', 'programs'),
                           ('Productividad', 'productivity'), ('Duplicados', 'duplicado'),
                           ('informe mensual completo', 'complete')):
            with self.subTest(report=key):
                result = self.result(f'Resumen de {label} global julio 2026')
                self.assertEqual(result['context']['metric'], key)
                self.assertTrue(result['cards'])
                self.assertIn('/ui/reports/', result['source_url'])
                serialized = json.dumps(result, ensure_ascii=False)
                for secret in ('TEST-1', 'PRIVATE-AGENCY', 'PRIVATE-REFERRAL', 'Participante 1'):
                    self.assertNotIn(secret, serialized)
        self.assertFalse(self.db.new or self.db.dirty or self.db.deleted)

    def test_fields_of_notes_pregnancy_visits_and_school_followup(self):
        cases = (
            ('notas A', 'notes', 'A', 1),
            ('notas A realizadas', 'notes', 'A', 1),
            ('notas A se han realizado', 'notes', 'A', 1),
            ('notas B en matematicas', 'notes', 'math_b', 1),
            ('casos de embarazo', 'pregnancy', 'pregnancy_cases', 1),
            ('porcentaje de prevencion de embarazo', 'pregnancy', 'prevention_pct', 0),
            ('referidos internos', 'visits', 'referrals_internal', 1),
            ('referidos internos en visitas', 'visits', 'referrals_internal', 1),
            ('referidos externos', 'visits', 'referrals_external', 1),
            ('visitas a agencias', 'visits', 'referrals_agency', 1),
            ('desercion 10 semanas', 'dropout', 'report_10', 0),
            ('no duplicados mujeres', 'no_duplicado', 'f', 2),
        )
        for question, report, field, expected in cases:
            with self.subTest(question=question):
                result = self.result(f'{question} global julio 2026')
                self.assertEqual((result['context']['metric'], result['context']['field']), (report, field))
                self.assertEqual(result['value'], expected)
                self.assertEqual(len(result['cards']), 1)

    def test_administrative_summary_and_duplicated_field_use_same_source(self):
        result = self.result('Informe administrativo global julio 2026')
        source = reports._build_adm_context(self.db, self.user, [1, 2, 3], 7, 2026, 0)
        self.assertEqual(result['value'], sum(row['services_count'] for row in source['rows']))
        self.assertEqual(len(result['tables']), 3)
        field = self.result('duplicados del informe administrativo global julio 2026')
        self.assertEqual(field['context']['field'], 'duplicates')
        self.assertEqual(field['value'], sum(row['duplicados'] for row in source['rows']))

    def test_source_links_keep_all_filters_and_selected_field_round_trips(self):
        result = self.result('notas A R1 julio 2026 propuesta 1')
        params = parse_qs(urlsplit(result['source_url']).query)
        self.assertEqual(params['proposal_id'], ['1'])
        self.assertEqual(params['employee_id'], ['-1'])
        self.assertEqual(params['month'], ['7'])
        self.assertEqual(params['year'], ['2026'])
        summary = farogpt.summary(self.db, self.user, result['context'])
        self.assertEqual(summary, result)
        global_result = self.result('notas global julio 2026')
        self.assertEqual(parse_qs(urlsplit(global_result['source_url']).query)['proposal_id'], ['1', '2', '3'])

    def test_field_comparison_and_switch_to_new_report(self):
        first = self.result('notas A global julio 2026')
        second = self.result('Comparar con agosto 2026', context=first['context'])
        self.assertEqual(second['comparison']['value'], 1)
        self.assertEqual(second['comparison']['difference'], 0)
        pregnancy = self.result('Y embarazo', context=first['context'])
        self.assertEqual(pregnancy['context']['metric'], 'pregnancy')
        self.assertNotEqual(pregnancy['context']['field'], 'A')
        self.assertEqual(pregnancy['value'], 1)

    def test_scoped_supervisor_global_remains_scoped_and_complete_is_never_built(self):
        user = SimpleNamespace(role='supervisor', _active_residential_id=2, username='scoped')
        result = self.result('no duplicados global julio 2026', user=user)
        self.assertEqual((result['value'], result['context']['residential_id']), (1, 2))
        with patch('app.services.full_monthly_report_data.build_full_monthly_report_data') as full:
            result = self.ask('Informe completo global julio 2026', user=user)
            self.assertEqual(result['type'], 'clarification')
            full.assert_not_called()
        with self.assertRaises(HTTPException):
            farogpt.summary(self.db, user, {'metric': 'notes', 'month': 7, 'year': 2026, 'residential_id': 1})

    def test_unsupported_or_conflicting_filters_never_return_unfiltered_total(self):
        for question in ('no duplicados R1 global julio 2026', 'notas julio 2026 menores de 10 años',
                         'no duplicados niños julio 2026', 'notas promedio numerico de matematicas julio 2026',
                         'desertores julio 2026', 'notas y embarazo julio 2026',
                         'embarazos mujeres julio 2026', 'ADM del 5 al 10 de julio 2026'):
            with self.subTest(question=question):
                result = self.ask(question)
                self.assertEqual(result['type'], 'clarification', result)
                self.assertNotIn('value', result)

    def test_expanded_report_template_handles_tables_units_and_escaping(self):
        result = self.result('Resumen de notas global julio 2026')
        result['tables'][0]['rows'][0][0] = '<script>unexpected()</script>'
        template = Environment(loader=FileSystemLoader('app/templates'),
                               autoescape=select_autoescape(['html'])).get_template('ui/farogpt_report.html')
        html = template.render(result=result, consulted_on=date(2026, 11, 14))
        self.assertIn('Promedio general A', html)
        self.assertIn('Calificaciones por materia', html)
        self.assertIn('Abrir reporte original', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>unexpected', html)

    def test_report_summary_suggestions_are_valid_questions(self):
        response = self.ask('Embarazo menores de 18 años julio 2026')
        self.assertEqual(response['type'], 'clarification')
        result = self.result(response['suggestions'][0])
        self.assertEqual(result['context']['metric'], 'pregnancy')
        self.assertEqual(result['value'], 1)

    def test_missing_period_retains_requested_report_field(self):
        pending = self.ask('cuántas notas A global')
        self.assertEqual(pending['type'], 'clarification')
        pending_year = self.ask('julio y agosto', context=pending['context'])
        self.assertEqual(pending_year['type'], 'clarification')
        result = self.ask('2026', context=pending_year['context'])
        self.assertEqual(result['type'], 'series', result)
        self.assertEqual(result['context']['field'], 'A')
        self.assertEqual(result['tables'][0]['rows'], [['Julio 2026', 1], ['Agosto 2026', 1]])
        self.assertIsNone(result['value'])
        self.assertEqual(farogpt.summary(self.db, self.user, result['context']), result)

    def test_monthly_reports_preserve_original_values_links_and_scope(self):
        for label in ('no duplicados', 'notas', 'embarazo', 'ADM'):
            with self.subTest(report=label):
                result = self.ask(f'{label} global julio y agosto 2026')
                self.assertEqual(result['type'], 'series', result)
                singles = [self.result(f'{label} global {month} 2026') for month in ('julio', 'agosto')]
                expected = [[single['period'], *[card['value'] for card in single['cards']]] for single in singles]
                self.assertEqual(result['tables'][0]['rows'], expected)
                self.assertEqual(result['metrics'], {})
                self.assertIsNone(result['value'])
                for month, single in zip(result['monthly_results'], singles):
                    self.assertEqual(month['source_url'], single['source_url'])
                self.assertNotIn('TEST-1', json.dumps(result))
        user = SimpleNamespace(role='supervisor', _active_residential_id=2, username='scoped')
        scoped = self.ask('no duplicados global julio y agosto 2026', user=user)
        self.assertEqual(scoped['context']['residential_id'], 2)
        self.assertEqual(scoped['tables'][0]['rows'][0][1], 1)
        with patch('app.services.full_monthly_report_data.build_full_monthly_report_data') as full:
            self.assertEqual(self.ask('Informe completo julio y agosto 2026')['type'], 'clarification')
            full.assert_not_called()

    def test_several_current_proposals_keep_field_until_selection(self):
        pending = farogpt.answer(self.db, self.user, 'notas A julio 2026', {})
        self.assertEqual(pending['type'], 'clarification')
        self.assertIn('varias propuestas', pending['message'])
        result = self.result('todas las propuestas', context=pending['context'])
        self.assertEqual((result['context']['field'], result['value']), ('A', 1))


if __name__ == '__main__':
    unittest.main()
