from __future__ import annotations

import unittest

from sqlalchemy import Column, MetaData, Table, create_engine
from sqlalchemy.orm import Session

from app.models.activity_code import ActivityCode
from app.models.proposal import Proposal  # noqa: F401 — resolves proposal foreign-key column types
from app.models.proposal_activity_code import ProposalActivityCode
from app.models.proposal_population_group import ProposalPopulationGroup
from app.models.proposal_report_program import ProposalReportProgram
from app.models.proposal_report_program_activity import ProposalReportProgramActivity
from app.models.proposal_report_program_activity_code import ProposalReportProgramActivityCode
from app.models.proposal_report_program_population import ProposalReportProgramPopulation
from app.models.proposal_report_program_population_activity_code import ProposalReportProgramPopulationActivityCode
from app.services.report_programs import (
    resolve_effective_program_population_blocks,
    resolve_effective_program_activity_code_ids,
    effective_program_activity_code_select,
)


class ReportProgramMultiProposalTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        metadata = MetaData()
        self.tables = {}
        for model in (
            ActivityCode, ProposalActivityCode, ProposalPopulationGroup,
            ProposalReportProgram, ProposalReportProgramActivity,
            ProposalReportProgramActivityCode, ProposalReportProgramPopulation,
            ProposalReportProgramPopulationActivityCode,
        ):
            # Keep real ORM column names/types; SQL Server defaults and foreign
            # keys unrelated to this read-only fixture are intentionally omitted.
            self.tables[model] = Table(model.__tablename__, metadata, *[
                Column(column.name, column.type, primary_key=column.primary_key)
                for column in model.__table__.columns
            ])
        metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        for proposal_id in (1, 2, 3):
            self.insert(ProposalPopulationGroup, population_group_id=proposal_id,
                        proposal_id=proposal_id, code="adult", label="Adultos", sort_order=0)
            self.insert(ProposalReportProgram, program_id=proposal_id,
                        proposal_id=proposal_id, population_group_id=proposal_id,
                        code="P1", name="Programa", formal_name="Programa formal",
                        sort_order=0, is_active=True)
        for activity_id, code, proposal_id in ((10, "1.a.2", 1), (20, "1.a.3", 2), (30, "1.a.4", 3)):
            self.insert(ActivityCode, activity_code_id=activity_id, code=code,
                        description=code, proposal_id=proposal_id, is_active=True)
        self.insert(ProposalActivityCode, proposal_activity_code_id=1, proposal_id=2,
                    activity_code_id=10, is_active=True)

    def insert(self, model, **values):
        self.db.execute(self.tables[model].insert().values(**values))

    def add_population(self, proposal_id, activity_ids):
        self.insert(ProposalReportProgramPopulation, program_population_id=proposal_id,
                    program_id=proposal_id, population_group_id=proposal_id,
                    sort_order=0, is_active=True)
        for activity_id in activity_ids:
            self.insert(ProposalReportProgramPopulationActivityCode,
                        program_population_id=proposal_id, activity_code_id=activity_id)

    def test_shared_activity_merged_once_and_unselected_proposal_excluded(self):
        self.add_population(1, [10])
        self.add_population(2, [10, 20])
        self.add_population(3, [30])

        blocks = resolve_effective_program_population_blocks(self.db, [1, 2, 1])

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["program"].program_id, 1)
        self.assertEqual(blocks[0]["program_display_name"], "Programa formal")
        self.assertEqual(len(blocks[0]["population_blocks"]), 1)
        population = blocks[0]["population_blocks"][0]
        self.assertEqual(population["population_label"], "Adultos")
        self.assertEqual([row["activity_code_id"] for row in population["rows"]], [10, 20])

    def test_activity_subquery_preserves_population_precedence_and_legacy_fallback(self):
        self.insert(ProposalReportProgramActivity, program_activity_id=1,
                    program_id=1, code="legacy", label="Actividad", is_active=False)
        self.insert(ProposalReportProgramActivityCode, program_activity_id=1, activity_code_id=10)
        def check(expected):
            self.assertEqual(set(self.db.execute(effective_program_activity_code_select(1)).scalars()), expected)
            self.assertEqual(resolve_effective_program_activity_code_ids(self.db, 1), expected)
        check({10})
        self.add_population(1, [20])
        check({20})
        self.db.execute(self.tables[ProposalReportProgramPopulationActivityCode].delete())
        check(set())  # An empty active population must not fall back to legacy assignments.
        self.db.execute(self.tables[ProposalReportProgramPopulation].update().values(is_active=False))
        check({10})

    def test_single_proposal_list_preserves_existing_shape_and_rows(self):
        self.add_population(1, [10])
        scalar_blocks = resolve_effective_program_population_blocks(self.db, 1)
        self.assertEqual(resolve_effective_program_population_blocks(self.db, [1]), scalar_blocks)
        self.assertEqual(set(scalar_blocks[0]), {"program", "program_display_name", "population_blocks"})
        self.assertEqual(scalar_blocks[0]["population_blocks"], [{
            "program_population_id": 1, "population_group_id": 1,
            "population_label": "Adultos", "rows": [{
                "activity_code_id": 10, "activity_code": "1.a.2", "activity_description": "1.a.2",
            }],
        }])

    def test_legacy_and_population_structure_merge_without_duplicate_rows(self):
        self.insert(ProposalReportProgramActivity, program_activity_id=1,
                    program_id=1, code="legacy", label="Actividad", is_active=True)
        self.insert(ProposalReportProgramActivityCode, program_activity_id=1, activity_code_id=10)
        self.add_population(2, [10, 20])

        blocks = resolve_effective_program_population_blocks(self.db, [1, 2])

        self.assertEqual(len(blocks), 1)
        self.assertEqual(len(blocks[0]["population_blocks"]), 1)
        self.assertEqual([row["activity_code_id"] for row in blocks[0]["population_blocks"][0]["rows"]], [10, 20])

    def test_different_population_labels_remain_separate(self):
        self.add_population(1, [10])
        self.add_population(2, [20])
        self.db.execute(self.tables[ProposalPopulationGroup].update()
                        .where(self.tables[ProposalPopulationGroup].c.population_group_id == 2)
                        .values(label="Jóvenes"))

        blocks = resolve_effective_program_population_blocks(self.db, [1, 2])

        self.assertEqual([p["population_label"] for p in blocks[0]["population_blocks"]], ["Adultos", "Jóvenes"])

    def test_same_display_code_does_not_merge_different_activity_ids(self):
        self.add_population(1, [10])
        self.add_population(2, [20])
        self.db.execute(self.tables[ActivityCode].update()
                        .where(self.tables[ActivityCode].c.activity_code_id == 20)
                        .values(code="1.a.2"))

        rows = resolve_effective_program_population_blocks(self.db, [1, 2])[0]["population_blocks"][0]["rows"]

        self.assertEqual([row["activity_code_id"] for row in rows], [10, 20])


if __name__ == "__main__":
    unittest.main()
