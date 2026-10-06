from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_consolidated_reports as fixtures
from app.api.routes import reports
from app.services.vca_report_summary import build_vca_summary


class VCARegistrationSummaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ConsolidatedReportTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db = self.fixture.db
        self.tables = self.fixture.tables
        self.fixture.insert("residentials", [
            {"residential_id": 7, "name": "Arístides Chavier", "is_active": True},
            {"residential_id": 8, "name": "Bella Vista", "is_active": True},
        ])
        self.db.execute(self.tables["participants"].update().values(residential_id=7))
        self.db.execute(self.tables["proposal_participants"].update().values(residential_id=7, is_active=True))
        self.db.commit()

    def add_person(self, identifier, residential=7, active=True, vca="SI", proposals=(1,)):
        self.fixture.insert("participants", [{"participant_id": identifier, "residential_id": residential,
            "nombre": "Persona", "apellido_paterno": str(identifier), "vca": vca,
            "is_active": active, "genero": "F", "fecha_nacimiento": date(1990, 1, 1)}])
        self.fixture.insert("persons", [{"person_id": identifier, "legacy_participant_id": identifier}])
        for proposal in proposals:
            self.fixture.insert("proposal_participants", [{"proposal_participant_id": identifier * 100 + proposal,
                "proposal_id": proposal, "person_id": identifier, "residential_id": residential,
                "nombre": "Persona", "apellido_paterno": str(identifier), "vca": vca,
                "is_active": active, "genero": "F", "fecha_nacimiento": date(1990, 1, 1)}])

    def build(self, proposals=1):
        return self.fixture.context(reports._build_vca_context, proposals)

    def test_twenty_registered_fifteen_served_and_repeated_participations(self):
        for identifier in range(2, 21):
            self.add_person(identifier)
        self.fixture.insert("attendance", [{"attendance_id": i + 20, "session_id": 1,
            "participant_id": i, "attended": True} for i in range(2, 16)])
        self.fixture.insert("activity_sessions", [{"session_id": i, "proposal_id": 1,
            "activity_code_id": 100, "residential_id": 7, "session_date": date(2026, 7, 10)}
            for i in range(10, 18)])
        self.fixture.insert("attendance", [{"attendance_id": i + 100, "session_id": i,
            "participant_id": 1, "attended": True} for i in range(10, 18)])
        self.fixture.insert("attendance", [{"attendance_id": 300, "session_id": 1,
            "participant_id": 16, "attended": False}])
        context = self.build()
        summary = context["vca_summary"]
        self.assertEqual(context["total_people"], 15)
        self.assertEqual(summary["total"]["registered"], 20)
        self.assertEqual(summary["total"]["served"], 15)
        self.assertEqual(summary["total"]["f"], 15)
        self.assertEqual(summary["total"]["m"], 0)
        self.assertEqual(summary["total"]["services"], {10: 24})
        self.assertEqual(next(row for row in context["rows"] if row["participant_id"] == 1)["column_values"], {10: 10})
        self.assertEqual(summary["rows"][0]["registered"], 20)
        # The registry is not restricted to people attending in the selected month.
        august = reports._build_vca_context(self.db, SimpleNamespace(), 1, 8, 2026, 0)
        self.assertEqual(august["vca_summary"]["total"]["registered"], 20)
        self.assertEqual(august["vca_summary"]["total"]["served"], 0)

    def test_registry_requires_active_vca_registration_and_deduplicates_proposals(self):
        self.add_person(2, proposals=(1, 2))
        self.add_person(3, active=False)
        self.add_person(4, vca="NO")
        self.add_person(5, proposals=(3,))
        self.add_person(6, proposals=())
        self.add_person(7, residential=8, vca=" si ")
        combined = self.build([1, 2])
        self.assertEqual(combined["vca_summary"]["total"]["registered"], 3)
        self.assertEqual(combined["total_people"], 1)
        self.assertEqual(combined["vca_summary"]["total"]["services"], {10: 5})
        self.assertEqual([(r["residential_name"], r["registered"], r["served"])
                          for r in combined["vca_summary"]["rows"]], [
            ("Arístides Chavier", 2, 1), ("Bella Vista", 1, 0)])
        selected = SimpleNamespace(residential_id=8)
        with patch.object(reports, "_resolve_reporting_scope", return_value={
            "selected_user": selected, "is_global": False, "employee_id": -8,
        }), patch.object(reports, "_residential_from_user", return_value="Bella Vista"):
            scoped = self.build([1, 2])
        self.assertEqual(scoped["vca_summary"]["total"]["registered"], 1)
        self.assertEqual(scoped["vca_summary"]["total"]["served"], 0)
        self.assertEqual([r["residential_name"] for r in scoped["vca_summary"]["rows"]], ["Bella Vista"])

    def test_summary_is_not_built_without_authorized_scope_or_valid_proposal(self):
        with patch.object(reports, "_resolve_reporting_scope", return_value={
            "selected_user": None, "is_global": False, "employee_id": None,
        }):
            context = self.build()
        self.assertIsNone(context["vca_summary"])
        self.assertIsNone(self.build(999)["vca_summary"])

    def test_template_age_boundaries_and_unknown_demographics_preserve_totals(self):
        ages = [0, 4, 5, 8, 9, 13, 14, 17, 18, 61, 62, 100, None, -1, 20]
        columns = [SimpleNamespace(vca_column_id=i) for i in (10, 20, 30)]
        rows = [{"participant_id": i, "genero": "F" if i % 2 == 0 else "M",
                 "column_values": {10: 10 if i == 0 else "", 20: 1, 30: ""}}
                for i in range(len(ages))]
        rows[-1]["genero"] = ""
        summary = build_vca_summary(registered_people={i: 7 for i in range(20)},
            rows=rows, columns=columns, residential_names={7: "Arístides Chavier"},
            participant_details={i: {"residential_id": 7, "age": age} for i, age in enumerate(ages)})
        total = summary["total"]
        self.assertEqual(total["ages"], [{"f": 1, "m": 1}] * 6)
        self.assertEqual((total["registered"], total["served"], total["f"], total["m"]), (20, 15, 7, 7))
        self.assertEqual((total["unknown_age"], total["unknown_gender"]), (2, 1))
        self.assertEqual(total["services"], {10: 10, 20: 15, 30: 0})

    def test_summary_templates_include_registry_without_attendance_and_keep_detail_first(self):
        context = reports._build_vca_context(self.db, SimpleNamespace(), 1, 8, 2026, 0)
        html = reports.templates.get_template("ui/reports/vca_pdf.html").render(context)
        self.assertLess(html.index("No hay participantes VCA"), html.index('<section class="vca-compliance">'))
        self.assertIn("Arístides Chavier", html)
        self.assertIn("INFORME DE CUMPLIMIENTO VCA CONSOLIDADO", html)
        self.assertIn("Total de personas con impedimentos", html)
        self.assertIn("Servicio", html)
        self.assertEqual(html.count('class="vca-compliance"'), 1)
        # Existing exports can still render older/minimal contexts without a summary.
        old_html = reports.templates.get_template("ui/reports/vca_pdf.html").render({
            **context, "vca_summary": None})
        self.assertNotIn('class="vca-compliance"', old_html)


if __name__ == "__main__":
    unittest.main()
