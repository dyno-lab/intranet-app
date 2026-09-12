from __future__ import annotations

import os
import re
import unittest
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jinja2 import ChainableUndefined, Environment, FileSystemLoader

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes import reports


TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "app" / "templates"


class ProposalSelectParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.multiple = False
        self.selected = []
        self.form_actions = []
        self.post_actions = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select" and attrs.get("name") == "proposal_id":
            self.active = True
            self.multiple = "multiple" in attrs
        if tag == "option" and self.active and "selected" in attrs:
            self.selected.append(attrs["value"])
        if tag == "button" and "formaction" in attrs:
            self.form_actions.append(attrs["formaction"])
        if tag == "form" and attrs.get("method") == "post" and attrs.get("action", "").startswith("/ui/reports/"):
            self.post_actions.append(attrs["action"])

    def handle_endtag(self, tag):
        if tag == "select":
            self.active = False


def sample_context():
    return {
        "request": SimpleNamespace(session={}, url=SimpleNamespace(path="/ui/reports")),
        "current_user": SimpleNamespace(role="admin", user_id=7),
        "proposals": [SimpleNamespace(proposal_id=i, code=f"P{i}", name=f"Propuesta {i}") for i in (1, 2, 3)],
        "selected_proposal_id": 1,
        "selected_proposal_ids": [1, 2],
        "selected_user": SimpleNamespace(user_id=7, username="Pruebas"),
        "selected_employee_id": 7,
        "period_label": "Septiembre 2026",
        "selected_period_type": "monthly",
        "selected_month": 9,
        "selected_year": 2026,
        "is_global": False,
        "user_residential_map": {7: "Residencial de prueba"},
        "summary": {"hours": 0, "visits": 0, "attendances": 0},
        "rows": [],
        "mapped_activity_ids": [],
        "referral_rows": [],
        "referral_type_options": [],
        "visit_report": SimpleNamespace(visit_report_id=1),
        "report_options": [SimpleNamespace(value="visitas", label="Visitas"), SimpleNamespace(value="adm", label="Informe ADM")],
        "selected_report_key": "visitas",
        "month_options": [(9, "Septiembre")],
        "year_options": [2026],
    }


class ReportMultiProposalTemplateTests(unittest.TestCase):
    def setUp(self):
        self.env = Environment(loader=FileSystemLoader(TEMPLATE_ROOT), undefined=ChainableUndefined)

    def test_every_existing_proposal_selector_preserves_multiple_and_legacy_selection(self):
        templates_checked = 0
        for path in (TEMPLATE_ROOT / "ui" / "reports").glob("*.html"):
            source = path.read_text(encoding="utf-8")
            select = re.search(r'<select[^>]*name="proposal_id"[^>]*>.*?</select>', source, re.S)
            if not select:
                continue
            setup = re.search(r"{% set report_proposal_ids = .*?%}", source)
            self.assertIsNotNone(setup, path.name)
            for multiple in (True, False):
                with self.subTest(template=path.name, multiple=multiple):
                    context = sample_context()
                    if not multiple:
                        context.pop("selected_proposal_ids")
                    html = self.env.from_string(setup.group() + select.group()).render(**context)
                    parsed = ProposalSelectParser()
                    parsed.feed(html)
                    self.assertTrue(parsed.multiple)
                    self.assertEqual(parsed.selected, ["1", "2"] if multiple else ["1"])
            templates_checked += 1
        self.assertEqual(templates_checked, 13)

    def test_existing_visits_output_actions_and_single_proposal_referral_writes(self):
        expected_actions = ["/ui/reports/visitas", "/ui/reports/visitas/pdf/download", "/ui/reports/visitas/excel", "/ui/reports/visitas/pdf"]
        for multiple in (True, False):
            with self.subTest(multiple=multiple):
                context = sample_context()
                context["selected_proposal_ids"] = [1, 2] if multiple else [1]
                html = self.env.get_template("ui/reports/visitas.html").render(**context)
                parsed = ProposalSelectParser()
                parsed.feed(html)
                self.assertEqual(parsed.form_actions, expected_actions)
                self.assertEqual(parsed.post_actions, [] if multiple else ["/ui/reports/visitas/referrals/save", "/ui/reports/visitas/delete"])
                if multiple:
                    self.assertIn("P1 - Propuesta 1; P2 - Propuesta 2", html)

    def test_existing_index_output_types_remain_screen_excel_pdf(self):
        html = self.env.get_template("ui/reports/index.html").render(**sample_context())
        output = re.search(r'<select[^>]*name="output"[^>]*>.*?</select>', html, re.S).group()
        self.assertEqual(re.findall(r'<option value="([^"]+)"', output), ["screen", "excel", "pdf"])
        self.assertIn('action="/ui/reports/run"', html)

    def test_existing_printed_proposal_labels_include_all_selected_names(self):
        for name in ("visitas_pdf.html", "embarazo_pdf.html", "desercion_escolar_pdf.html"):
            with self.subTest(template=name):
                source = (TEMPLATE_ROOT / "ui" / "reports" / name).read_text(encoding="utf-8")
                setup = re.search(r"{% set report_proposal_ids = .*?%}", source).group()
                label = re.search(r"<div><strong>Propuesta:</strong>.*?</div>", source).group()
                html = self.env.from_string(setup + label).render(**sample_context())
                self.assertEqual(html, "<div><strong>Propuesta:</strong> P1 - Propuesta 1; P2 - Propuesta 2</div>")


class ReportMultiProposalDownloadRouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(reports.router, prefix="/ui/reports")
        app.dependency_overrides[reports.get_db] = lambda: None
        app.dependency_overrides[reports.get_current_user] = lambda: SimpleNamespace()
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.query = "?proposal_id=1&proposal_id=2&month=9&year=2026&employee_id=0"

    def test_pdf_download_keeps_pdf_mime_and_passes_all_proposals(self):
        with patch.object(reports, "_build_visits_context", return_value={}) as build, patch.object(reports, "_pdf_download_filename", return_value="visitas.pdf"), patch.object(reports, "render_template_to_chromium_pdf_bytes", return_value=b"%PDF-test") as render:
            response = self.client.get("/ui/reports/visitas/pdf/download" + self.query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(build.call_args.args[2], [1, 2])
        self.assertEqual(render.call_args.kwargs["template_name"], "ui/reports/visitas_pdf.html")
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertEqual(response.headers["content-disposition"], 'attachment; filename="visitas.pdf"')

    def test_excel_download_keeps_sheet_title_mime_and_all_proposals(self):
        context = {"period_label": "Septiembre 2026", "selected_user": None, "is_global": True, "residential_name": "Global"}
        with patch.object(reports, "_build_visits_context", return_value=context) as build, patch.object(reports, "build_visitas_sheet") as sheet, patch.object(reports, "workbook_to_bytes", return_value=BytesIO(b"xlsx-test")), patch.object(reports, "_period_filename_suffix", return_value="2026_9"):
            response = self.client.get("/ui/reports/visitas/excel" + self.query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(build.call_args.args[2], [1, 2])
        self.assertEqual(sheet.call_args.kwargs["title"], "Visitas")
        self.assertEqual(response.headers["content-type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("visitas_Global_2026_9.xlsx", response.headers["content-disposition"])


if __name__ == "__main__":
    unittest.main()
