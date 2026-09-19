from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
import unittest

from pypdf import PdfReader

from app.services import full_monthly_report_tables as tables


def program(code, f, m, total):
    return {"program": SimpleNamespace(code=code), "total_f": f, "total_m": m, "total_all": total}


def fixture():
    residentials = []
    for identifier in (1, 2):
        residentials.append({
            "residential_id": identifier, "residential_name": f"Residencial {identifier}",
            "residential": SimpleNamespace(municipality="Ponce", rq_code=f"RQ{identifier}"),
            "no_duplicado": {"total_all": 5}, "duplicado": {"total_all": 15},
            "por_programa": {"program_sections": [program("1-A", 2, 2, 4), program("2-B", 3, 0, 3)]},
            "hoja_cotejo": {"program_blocks": [{"program": SimpleNamespace(code="1-A"), "program_contact_hours": 9}], "total_contact_hours": 8.5},
        })
    return {"period_label": "Septiembre 2026", "residentials": residentials,
            "no_duplicado": {"total_all": 7}, "duplicado": {"total_all": 23},
            "por_programa": {"program_sections": [program("1-A", 4, 4, 8), program("2-B", 3, 2, 5)]},
            "hoja_cotejo": {"program_blocks": [{"program": SimpleNamespace(code="1-A"), "program_contact_hours": 13}], "total_contact_hours": 12.75},
            "visitas": {"referral_rows": []}}


def reader(payload):
    return PdfReader(BytesIO(payload))


def text(payload):
    return "\n".join(line.strip() for page in reader(payload).pages for line in page.extract_text().splitlines())


class FullMonthlyReportTablesTests(unittest.TestCase):
    def test_empty_program_configuration_does_not_invent_a_program(self):
        data = fixture()
        data["por_programa"]["program_sections"] = []
        for row in data["residentials"]:
            row["por_programa"]["program_sections"] = []
        result = text(tables.duplicated_pdf(data))
        self.assertIn("Residencial 1", result)
        self.assertIn("Total\n0\n7\n23", result)
        self.assertNotIn("Programa 1-A", result)

    def test_duplicate_totals_preserve_distinct_meanings(self):
        result = text(tables.duplicated_pdf(fixture()))
        self.assertIn("Total\n8\n5\n13\n7\n23", result)
        self.assertIn("una persona puede participar en más de uno", result)

    def test_hours_use_existing_grand_total_not_sum_of_rows_or_programs(self):
        result = text(tables.contact_hours_table_pdf(fixture()))
        self.assertIn("12.75", result)
        self.assertIn("13.00", result)
        self.assertNotIn("17.00", result)

    def test_external_referrals_count_rows_and_preserve_locations_outside_active_list(self):
        data = fixture()
        data["visitas"]["referral_rows"] = [
            {"referral_type": "Externo", "residential_name": "Residencial 1", "agency": "Agencia A"},
            {"referral_type": "Externo", "residential_name": "Residencial 1", "agency": "Agencia A"},
            {"referral_type": "Externo", "residential_name": "Inactivo", "agency": "Agencia B"},
            {"referral_type": "Interno", "residential_name": "Residencial 2", "agency": "Excluir"},
        ]
        result = text(tables.external_referrals_pdf(data))
        self.assertIn("Residencial 1\n2\nAgencia A", result)
        self.assertIn("Residencial 2\n0", result)
        self.assertIn("Inactivo\n1\nAgencia B", result)
        self.assertIn("Total Acumulados\n3", result)
        self.assertNotIn("Excluir", result)

    def test_real_visit_context_uses_code_name_alias_without_duplicate_location(self):
        from tests.test_full_monthly_report_data import FullMonthlyReportDataTests
        source = FullMonthlyReportDataTests()
        source.setUp()
        self.addCleanup(source.doCleanups)
        data = source.build()
        result = text(tables.external_referrals_pdf(data))
        self.assertIn("Residencial 1\n1\nAgencia", result)
        self.assertNotIn("R1 - Residencial 1", result)
        self.assertEqual(result.count("Residencial 1\n"), 1)

    def test_targets_distinguish_missing_zero_and_program_participation(self):
        data = fixture()
        data["target_cumulative"] = {"period_label": "Julio a septiembre 2026", "by_residential": {1: 20, 2: 30}, "total_all": 40}
        payload = reader(tables.participant_targets_pdf(data, {"targets": {1: 0}}))
        self.assertEqual(len(payload.pages), 3)
        first, second, third = ["\n".join(line.strip() for line in page.extract_text().splitlines()) for page in payload.pages]
        self.assertIn("Pendiente", first)
        self.assertRegex(first, r"No\s+aplica")
        self.assertIn("40", first)
        self.assertIn("TOTAL\n8\n5\n13", second)
        self.assertIn("no representa personas únicas", second)
        self.assertIn("Pendiente: desglose de población", third)

    def test_explicit_population_bins_render_without_splitting_other_age_ranges(self):
        data = fixture()
        grouped = {key: {"f": 2, "m": 1, "total": 3} for key in ("children", "youth", "adults", "older")}
        data["target_population_rows"] = {1: deepcopy(grouped), 2: deepcopy(grouped), "global": deepcopy(grouped)}
        payload = reader(tables.participant_targets_pdf(data, {"targets": {1: 10, 2: 10}}))
        last = "\n".join(line.strip() for line in payload.pages[-1].extract_text().splitlines())
        self.assertNotIn("Pendiente: desglose de población", last)
        self.assertIn("7\n20\n35%", last)

    def test_continuation_pages_preserve_every_residential_and_repeat_headers(self):
        data = fixture()
        source = data["residentials"][0]
        data["residentials"] = []
        for identifier in range(19):
            row = deepcopy(source)
            row.update(residential_id=identifier, residential_name=f"Residencial {identifier:02}")
            data["residentials"].append(row)
        for builder in (tables.duplicated_pdf, tables.contact_hours_table_pdf, tables.external_referrals_pdf):
            with self.subTest(builder=builder.__name__):
                result = reader(builder(data))
                self.assertEqual(len(result.pages), 2)
                body = "\n".join(page.extract_text() for page in result.pages)
                for row in data["residentials"]:
                    self.assertEqual(body.count(row["residential_name"] + "\n"), 1)


if __name__ == "__main__":
    unittest.main()
