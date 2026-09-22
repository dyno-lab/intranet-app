from io import BytesIO
from types import SimpleNamespace
import unittest

from pypdf import PdfReader

from app.services.full_monthly_report_targets import configured_targets
from app.services.full_monthly_report_tables import participant_targets_pdf
from tests.test_full_monthly_report_tables import fixture


class FullMonthlyReportTargetsTests(unittest.TestCase):
    def test_approved_proposal_goals_match_rq_and_not_local_ids_or_names(self):
        approved = {
            "RQ1014": 192, "RQ1009": 110, "RQ1001": 100, "RQ1017": 155,
            "RQ1016": 155, "RQ5022": 105, "RQ5148": 90, "RQ3089": 90,
            "RQ5045": 75, "RQ3090": 80, "RQ5266": 58, "RQ5184": 65,
            "RQ5314": 80, "RQ5048": 100, "RQ4010": 72, "RQ4009": 72,
            "RQ4011": 75, "RQ4001": 108,
        }
        proposal = SimpleNamespace(proposal_id=87, code="006", name="2025-000094-C")
        residentials = [SimpleNamespace(residential_id=identifier, rq_code=rq.lower(), name="Nombre distinto")
                        for identifier, rq in enumerate(approved, 101)]
        resolved = configured_targets([proposal, proposal], residentials)
        self.assertEqual(resolved["targets"], {row.residential_id: approved[row.rq_code.upper()] for row in residentials})
        self.assertEqual(sum(resolved["targets"].values()), 1782)
        approved_amps = {
            "RQ1014": "RQ005009017P", "RQ1009": "RQ005009015P", "RQ1001": "RQ005009010P",
            "RQ1017": "RQ005009020P", "RQ1016": "RQ005009019P", "RQ5022": "RQ005009022P",
            "RQ5148": "RQ005006022P", "RQ3089": "RQ005006021P", "RQ5045": "RQ005006029P",
            "RQ3090": "RQ005006028P", "RQ5266": "RQ005006020P", "RQ5184": "RQ005006019P",
            "RQ5314": "RQ005006016P", "RQ5048": "RQ005006018P", "RQ4010": "RQ005008015P",
            "RQ4009": "RQ005008014P", "RQ4011": "RQ005008016P", "RQ4001": "RQ005008007P",
        }
        self.assertEqual(resolved["amps"], {row.residential_id: approved_amps[row.rq_code.upper()] for row in residentials})
        proposal_005 = SimpleNamespace(proposal_id=42, code="005", name="2025-000094-B")
        for selection in ([proposal_005], [proposal_005, proposal], [proposal, proposal_005, proposal]):
            with self.subTest(proposals=[item.code for item in selection]):
                self.assertEqual(configured_targets(selection, residentials), resolved)

    def test_unknown_proposal_or_rq_does_not_borrow_an_approved_goal(self):
        known = SimpleNamespace(proposal_id=6, code="006", name="2025-000094-C")
        other = SimpleNamespace(proposal_id=4, code="004", name="Otra propuesta")
        residentials = [SimpleNamespace(residential_id=1, rq_code="RQ1014"),
                        SimpleNamespace(residential_id=2, rq_code="RQ9999")]
        self.assertEqual(configured_targets([known], residentials)["targets"], {1: 192})
        self.assertEqual(configured_targets([known], residentials)["amps"], {1: "RQ005009017P"})
        for proposals in ([], [other], [known, other], [SimpleNamespace(proposal_id=6, code="006", name="Otra propuesta")]):
            self.assertEqual(configured_targets(proposals, residentials), {"targets": {}, "amps": {}})

    def test_fixed_targets_apply_to_all_three_sheets_without_changing_attended_totals(self):
        data = fixture()
        data["proposals"] = [SimpleNamespace(proposal_id=6, code="006", name="2025-000094-C")]
        for row, rq in zip(data["residentials"], ("RQ1014", "RQ1009")):
            row["residential"].residential_id = row["residential_id"]
            row["residential"].rq_code = rq
        data["target_cumulative"] = {"period_label": "Julio a septiembre 2026", "by_residential": {1: 20, 2: 30}, "total_all": 40}
        population = {key: {"f": 0, "m": 0, "total": 0} for key in ("children", "youth", "adults", "older")}
        data["target_population_rows"] = {1: population, 2: population, "global": population}
        reader = PdfReader(BytesIO(participant_targets_pdf(data, {"targets": {1: 999, 2: 999}})))
        pages = [" ".join(page.extract_text().split()) for page in reader.pages]
        self.assertEqual(len(pages), 3)
        # Fixed goals sum to 302. Existing monthly/global and cumulative/global
        # unique counts remain 7 and 40, while program participation stays 13.
        self.assertIn("Residencial 1 Ponce RQ1014 RQ005009017P 192 5 20 3% 10%", pages[0])
        self.assertIn("Residencial 2 Ponce RQ1009 RQ005009015P 110 5 30 5% 27%", pages[0])
        self.assertIn("TOTAL 2 / / 302 7 40 2% 13%", pages[0])
        self.assertIn("TOTAL 8 5 13 302 4%", pages[1])
        self.assertIn("7 302 2%", pages[2])
        self.assertNotIn("Pendiente", pages[0])
        self.assertTrue(all("999" not in page for page in pages))
        proposal_006 = data["proposals"][0]
        proposal_005 = SimpleNamespace(proposal_id=5, code="005", name="2025-000094-B")
        for selection in ([proposal_005], [proposal_005, proposal_006]):
            data["proposals"] = selection
            result = PdfReader(BytesIO(participant_targets_pdf(data, {})))
            self.assertEqual([" ".join(page.extract_text().split()) for page in result.pages], pages)


if __name__ == "__main__":
    unittest.main()
