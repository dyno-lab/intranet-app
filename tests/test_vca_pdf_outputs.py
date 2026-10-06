from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from tests import test_consolidated_reports as fixtures  # test environment defaults
from app.api.routes import automation_reports, reports
from app.services import vca_report_pdf
from app.services.report_pdf import PDFBackendUnavailableError, PDFRenderError


class VCAPdfOutputsTests(unittest.TestCase):
    def test_alternate_renderer_preserves_detail_then_appends_legal_summary(self):
        def pdf(width, height):
            writer = PdfWriter()
            writer.add_blank_page(width=width, height=height)
            output = BytesIO()
            writer.write(output)
            return output.getvalue()

        context = {"vca_summary": {"rows": []}, "rows": [{"nombre": "Prueba"}]}
        with patch.object(vca_report_pdf, "render_template_to_pdf_bytes",
                          side_effect=[pdf(595, 842), pdf(1008, 612)]) as render:
            payload = vca_report_pdf.render_vca_legacy_pdf(templates=object(), context=context)
        pages = PdfReader(BytesIO(payload)).pages
        self.assertEqual([(p.mediabox.width, p.mediabox.height) for p in pages], [(595, 842), (1008, 612)])
        detail, summary = [call.kwargs for call in render.call_args_list]
        self.assertEqual(detail["template_name"], "ui/reports/vca_pdf.html")
        self.assertEqual(detail["context"], {**context, "vca_summary": None})
        self.assertNotIn("wkhtmltopdf_args", detail)
        self.assertEqual(summary["context"], context)
        args = summary["wkhtmltopdf_args"]
        self.assertEqual(args[args.index("--page-size") + 1], "Legal")
        self.assertEqual(args[args.index("--orientation") + 1], "Landscape")
        self.assertEqual(args[args.index("--page-offset") + 1], "1")
        self.assertIsNotNone(context["vca_summary"])

    def test_download_uses_summary_fallback_when_browser_is_unavailable_or_fails(self):
        user = SimpleNamespace(role="admin", user_id=1)
        app = FastAPI()
        app.include_router(reports.router)
        app.dependency_overrides[reports.get_db] = lambda: None
        app.dependency_overrides[reports.get_current_user] = lambda: user
        context = {"selected_month": 8, "selected_year": 2026, "vca_summary": {"rows": []}}
        for error in (PDFBackendUnavailableError("Unavailable"), PDFRenderError("Failed")):
            with self.subTest(error=type(error).__name__), TestClient(app) as client, \
                 patch.object(reports, "_build_vca_context", return_value=context), \
                 patch.object(reports, "render_template_to_chromium_pdf_bytes", side_effect=error), \
                 patch.object(reports, "render_vca_legacy_pdf", return_value=b"%PDF-complete") as render, \
                 patch.object(reports.logger, "exception"):
                response = client.get("/vca/pdf/download?proposal_id=1&month=8&year=2026&employee_id=0")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"%PDF-complete")
            self.assertEqual(render.call_args.kwargs["context"]["vca_summary"], context["vca_summary"])

    def test_both_zip_downloads_include_summary_and_keep_other_reports(self):
        keys = ["bonafide", "no_duplicado", "duplicado", "visitas", "por_programa",
                "hoja_cotejo", "desercion", "embarazo", "notas", "vca", "adm"]
        bundle = {key: {"selected_month": 8, "selected_year": 2026} for key in keys}
        bundle["vca"]["vca_summary"] = {"rows": []}
        user = SimpleNamespace(role="admin", user_id=1)
        for module, path in ((reports, "/todos/pdf"), (automation_reports, "/reports/todos/pdf")):
            app = FastAPI()
            app.include_router(module.router)
            app.dependency_overrides[module.get_db] = lambda: None
            dependency = reports.get_current_user if module is reports else automation_reports.require_automation_access
            app.dependency_overrides[dependency] = lambda: user
            with self.subTest(route=path), TestClient(app) as client, \
                 patch.object(automation_reports, "_automation_user", return_value=user), \
                 patch.object(module, "_build_all_reports_bundle_context", return_value=bundle), \
                 patch.object(module, "build_notes_pdf_chart_images", return_value={}), \
                 patch.object(module, "render_template_to_chromium_pdf_bytes", return_value=b"%PDF-bonafide"), \
                 patch.object(module, "render_template_to_pdf_bytes", return_value=b"%PDF-other") as legacy, \
                 patch.object(module, "render_vca_legacy_pdf", return_value=b"%PDF-complete-vca") as vca:
                response = client.get(path + "?proposal_id=1&month=8&year=2026&employee_id=0")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(legacy.call_count, 9)
            vca.assert_called_once()
            with ZipFile(BytesIO(response.content)) as archive:
                self.assertEqual(len(archive.namelist()), 11)
                self.assertEqual(archive.read("vca_vca_2026_8.pdf"), b"%PDF-complete-vca")


if __name__ == "__main__":
    unittest.main()
