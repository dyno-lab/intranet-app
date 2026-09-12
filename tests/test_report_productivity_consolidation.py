from __future__ import annotations

import unittest
from copy import deepcopy
from types import SimpleNamespace

from fastapi import HTTPException

from app.services.report_productivity_consolidation import consolidate_productivity_inputs


def goal_row(proposal_id, activity_id=10, **overrides):
    values = dict(proposal_id=proposal_id, activity_code_id=activity_id,
                  goal_type="global_fixed", goal_value=4, period_goal_value=12)
    values.update(overrides)
    return (SimpleNamespace(**values), f"P{proposal_id}", f"Propuesta {proposal_id}", "1.a.2", "Actividad")


def count_row(proposal_id, count, activity_id=10, residential_id=7):
    return SimpleNamespace(proposal_id=proposal_id, activity_code_id=activity_id,
                           residential_id=residential_id, residential_name="Residencial",
                           executed_count=count)


class ReportProductivityConsolidationTests(unittest.TestCase):
    def test_shared_goal_kept_once_and_execution_summed_with_matching_keys(self):
        goals = [goal_row(2), goal_row(1)]
        counts = [count_row(2, 3), count_row(1, 2), count_row(2, 1, residential_id=8)]
        periods = [count_row(2, 9), count_row(1, 6)]
        before = deepcopy((goals, counts, periods))

        merged_goals, merged_counts, merged_periods = consolidate_productivity_inputs(goals, counts, periods)

        self.assertEqual(len(merged_goals), 1)
        goal, code, name, activity, description = merged_goals[0]
        self.assertEqual((goal.proposal_id, goal.activity_code_id, goal.goal_value, goal.period_goal_value), (1, 10, 4, 12))
        self.assertEqual((code, name, activity, description), ("P1 / P2", "Propuesta 1 / Propuesta 2", "1.a.2", "Actividad"))
        self.assertEqual([(row.proposal_id, row.residential_id, row.executed_count) for row in merged_counts], [(1, 7, 5), (1, 8, 1)])
        self.assertEqual([(row.proposal_id, row.activity_code_id, row.executed_count) for row in merged_periods], [(1, 10, 15)])
        self.assertEqual((goals, counts, periods), before)
        self.assertIsNot(goal, goals[1][0])

    def test_differing_goal_fields_are_rejected(self):
        for values in ({"goal_type": "per_residential_fixed"}, {"goal_value": 5}, {"period_goal_value": 13}):
            with self.subTest(values=values), self.assertRaises(HTTPException) as error:
                consolidate_productivity_inputs([goal_row(1), goal_row(2, **values)], [], [])
            self.assertEqual(error.exception.status_code, 422)
            self.assertIn("1.a.2", error.exception.detail)

    def test_activity_ids_remain_distinct_despite_same_visible_code(self):
        goals, counts, periods = consolidate_productivity_inputs(
            [goal_row(1), goal_row(2, activity_id=20)],
            [count_row(1, 2), count_row(2, 3, activity_id=20)], [],
        )
        self.assertEqual([row[0].activity_code_id for row in goals], [10, 20])
        self.assertEqual([row.executed_count for row in counts], [2, 3])
        self.assertEqual(periods, [])

    def test_no_goal_counts_have_consistent_canonical_keys(self):
        goals, counts, periods = consolidate_productivity_inputs([], [count_row(2, None)], [count_row(1, 3)])
        self.assertEqual(goals, [])
        self.assertEqual((counts[0].proposal_id, counts[0].executed_count), (1, 0))
        self.assertEqual((periods[0].proposal_id, periods[0].executed_count), (1, 3))

    def test_empty_inputs(self):
        self.assertEqual(consolidate_productivity_inputs([], [], []), ([], [], []))


if __name__ == "__main__":
    unittest.main()
