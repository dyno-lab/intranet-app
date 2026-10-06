from copy import deepcopy
from types import SimpleNamespace
import unittest

from tests import test_full_monthly_report_data as fixtures
from app.services.full_monthly_report_checklist import checklist_rows
from app.services.full_monthly_report_checklist_goals import apply_frequency, reference_plan_multiplier


class ChecklistFrequencyTests(unittest.TestCase):
    def row(self, code, monthly=6, cumulative=18):
        return {"activity_code": code, "activities_count": monthly,
                "cumulative_activities": cumulative, "duplicados": 37,
                "achievement_text": "Resultados reales", "goal_summary": "Meta anterior",
                "goal_target": 999, "cumulative_target": 999}

    def test_monthly_and_full_period_targets_are_independent(self):
        source = self.row("1.A.5")
        before = deepcopy(source)
        row = apply_frequency(source, 1)
        self.assertEqual((row["goal_summary"], row["goal_target"], row["cumulative_target"]),
                         ("12 Mensual", 12, 36))
        self.assertEqual((row["monthly_percent"], row["cumulative_ratio"], row["percent"]),
                         (50, "18/36", 50))
        self.assertEqual(source, before)
        self.assertEqual((row["activities_count"], row["duplicados"]), (6, 37))

    def test_two_selected_proposals_add_targets_without_multiplying_results(self):
        row = apply_frequency(self.row("1.a.5"), 2)
        self.assertEqual((row["goal_summary"], row["goal_target"], row["cumulative_target"]),
                         ("24 Mensual", 24, 72))
        self.assertEqual((row["monthly_percent"], row["cumulative_ratio"], row["percent"]),
                         (25, "18/72", 25))
        self.assertEqual(row["activities_count"], 6)

    def test_as_needed_and_one_activity_per_proposal(self):
        for factor in (1, 2):
            for monthly, cumulative, monthly_percent, period_percent in ((0, 0, 0, 0), (0, 5, 0, 100), (2, 5, 100, 100)):
                row = apply_frequency(self.row("2.b.5", monthly, cumulative), factor)
                self.assertEqual((row["goal_summary"], row["cumulative_ratio"]), ("Según Necesidad", str(cumulative)))
                self.assertEqual((row["monthly_percent"], row["percent"]), (monthly_percent, period_percent))
            row = apply_frequency(self.row("4.d.12", 0, 1), factor)
            self.assertEqual(row["cumulative_ratio"], f"1/{factor}")
            self.assertEqual(row["goal_summary"], "1 Actividad" if factor == 1 else "2 Actividades")

    def test_scope_is_only_the_approved_proposals_and_unknown_codes_keep_current_goals(self):
        for code, name in (("005", "2025-000094-B"), ("006", "2025-000094-C")):
            context = {"proposal": SimpleNamespace(code=code, name=name), "selected_proposal_id": 9}
            self.assertEqual(reference_plan_multiplier(context), 1)
            self.assertEqual(reference_plan_multiplier({**context, "selected_proposal_ids": [9, 10]}), 2)
        self.assertEqual(reference_plan_multiplier({"proposal": SimpleNamespace(code="007", name="Otra")}), 0)
        row = self.row("9.a.99")
        self.assertIs(apply_frequency(row, 2), row)

    def test_recruitment_uses_distinct_residential_counts_with_reference_targets(self):
        context = {"proposal": SimpleNamespace(code="005", name="2025-000094-B"),
                   "selected_proposal_id": 5, "selected_proposal_ids": [5, 6],
                   "program_blocks": [{"program_code": "1A", "program_display_name": "Niños", "rows": []}]}
        populations = [{"program": SimpleNamespace(code="1A"), "population_blocks": [
            {"population_label": "Niños", "rows": []}]}]
        recruitment = {("1A", "Niños"): {"monthly_count": 11, "cumulative_count": 12}}
        row = checklist_rows(context, populations, recruitment)[0][1][1][1]
        self.assertEqual((row["goal_summary"], row["cumulative_ratio"]), ("36 Mensual", "12/36"))
        self.assertEqual((row["monthly_percent"], row["percent"]), (31, 33))
        self.assertIn("12 residenciales distintos acumulados", row["achievement_text"])


if __name__ == "__main__":
    unittest.main()
