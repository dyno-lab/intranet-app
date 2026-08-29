from __future__ import annotations

import os
import unittest
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from app.api.routes import admin as admin_routes  # noqa: E402
from app.api.routes import consolidado_mensual_global as consolidado_routes  # noqa: E402
from app.api.routes import hoja_cotejo_admin as hoja_routes  # noqa: E402
from app.api.routes import plantilla_duplicado as plantilla_routes  # noqa: E402
from app.core.residential_scope import ACTIVE_RESIDENTIAL_SESSION_KEY  # noqa: E402
from app.models.proposal import Proposal  # noqa: E402
from app.models.report_template import ReportTemplate  # noqa: E402
from app.models.residential import Residential  # noqa: E402
from app.services import consolidado_mensual_service as consolidado_service  # noqa: E402
from app.services import hoja_cotejo_admin_service as hoja_service  # noqa: E402


ACTIVE_RESIDENTIAL_ID = 7
OTHER_RESIDENTIAL_ID = 9


class _Request:
    def __init__(self, residential_id: int | None = None):
        self.session = {}
        if residential_id is not None:
            self.session[ACTIVE_RESIDENTIAL_SESSION_KEY] = residential_id


class _Result:
    def __init__(self, *, values=None, scalar=None):
        self.values = list(values or [])
        self.scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self.values

    def scalar_one_or_none(self):
        return self.scalar


class _Database:
    def __init__(self, *, objects=None, results=None):
        self.objects = objects or {}
        self.results = list(results or [])
        self.statements = []

    def get(self, model, object_id):
        return self.objects.get((model, object_id))

    def execute(self, statement):
        self.statements.append(statement)
        if not self.results:
            raise AssertionError("Unexpected database query")
        return self.results.pop(0)


def _user(role: str, residential_id: int | None = None):
    user = SimpleNamespace(role=role, username=f"{role}@example.test")
    if residential_id is not None:
        user._active_residential_id = residential_id
    return user


def _residential(residential_id: int, name: str) -> Residential:
    residential = Residential(
        code=f"R{residential_id}",
        name=name,
        municipality="Ponce",
        rq_code=f"RQ-{residential_id}",
        is_active=True,
    )
    residential.residential_id = residential_id
    return residential


def _route_context() -> dict[str, Any]:
    return {
        "month": 8,
        "year": 2026,
        "selected_period_type": "monthly",
        "period_label": "agosto 2026",
        "proposal": None,
        "pdf_template_name": "unused.html",
        "rows": [],
        "totals": {
            "gender": {"F": 0, "M": 0},
            "unique_participants": 0,
            "attendances": 0,
        },
        "legacy_reference_note": "",
    }


def _statement_has_value(statement: Any, value: int) -> bool:
    return value in statement.compile().params.values()


class AdminReportResidentialScopeTests(unittest.TestCase):
    def test_route_scope_helpers_preserve_global_mode_and_enforce_active_mode(self):
        modules = (consolidado_routes, plantilla_routes, hoja_routes)

        for module in modules:
            for role in ("admin", "supervisor"):
                with self.subTest(module=module.__name__, role=role, mode="global"):
                    global_user = _user(role)
                    self.assertIsNone(
                        module._resolve_report_residential_id(_Request(), global_user, None)
                    )
                    self.assertEqual(
                        module._resolve_report_residential_id(
                            _Request(), global_user, OTHER_RESIDENTIAL_ID
                        ),
                        OTHER_RESIDENTIAL_ID,
                    )

                with self.subTest(module=module.__name__, role=role, mode="residential"):
                    residential_user = _user(role, ACTIVE_RESIDENTIAL_ID)
                    request = _Request(ACTIVE_RESIDENTIAL_ID)
                    self.assertEqual(
                        module._resolve_report_residential_id(
                            request, residential_user, None
                        ),
                        ACTIVE_RESIDENTIAL_ID,
                    )
                    self.assertEqual(
                        module._resolve_report_residential_id(
                            request, residential_user, ACTIVE_RESIDENTIAL_ID
                        ),
                        ACTIVE_RESIDENTIAL_ID,
                    )
                    with self.assertRaises(Exception) as conflict:
                        module._resolve_report_residential_id(
                            request, residential_user, OTHER_RESIDENTIAL_ID
                        )
                    self.assertEqual(
                        getattr(conflict.exception, "status_code", None),
                        403,
                    )

    def _assert_endpoint_forces_active_residential(
        self,
        module: Any,
        endpoint: Any,
        kwargs: dict[str, Any],
        response_kind: str,
    ) -> None:
        with patch.object(module, "_build_context", return_value=_route_context()) as builder:
            if response_kind == "template":
                response_patch = patch.object(
                    module.templates,
                    "TemplateResponse",
                    return_value=SimpleNamespace(status_code=200),
                )
            elif response_kind == "pdf":
                response_patch = patch.object(
                    module,
                    "render_template_to_pdf_bytes",
                    return_value=b"pdf",
                )
            else:
                response_patch = patch.object(
                    module,
                    "_build_excel_bytes",
                    return_value=b"xlsx",
                )

            with response_patch:
                endpoint(**kwargs)

        self.assertEqual(builder.call_args.args[5], ACTIVE_RESIDENTIAL_ID)

    def test_views_pdf_excel_and_validation_force_the_active_residential(self):
        request = _Request(ACTIVE_RESIDENTIAL_ID)
        user = _user("admin", ACTIVE_RESIDENTIAL_ID)
        db = object()
        common = {
            "request": request,
            "month": 8,
            "year": 2026,
            "period_type": "monthly",
            "start_date": None,
            "end_date": None,
            "proposal_id": "3",
            "residential_id": None,
            "db": db,
            "current_user": user,
        }
        cases = [
            (
                consolidado_routes,
                consolidado_routes.consolidado_mensual_global_index,
                {**common, "authorized_name": None},
                "template",
            ),
            (
                consolidado_routes,
                consolidado_routes.consolidado_mensual_global_pdf,
                {**common, "authorized_name": None},
                "pdf",
            ),
            (
                consolidado_routes,
                consolidado_routes.consolidado_mensual_global_excel,
                {**common, "authorized_name": None},
                "excel",
            ),
            (
                consolidado_routes,
                consolidado_routes.consolidado_mensual_global_validacion,
                common,
                "template",
            ),
            (
                plantilla_routes,
                plantilla_routes.plantilla_duplicado_index,
                common,
                "template",
            ),
            (
                plantilla_routes,
                plantilla_routes.plantilla_duplicado_pdf,
                common,
                "pdf",
            ),
            (
                plantilla_routes,
                plantilla_routes.plantilla_duplicado_excel,
                common,
                "excel",
            ),
            (
                hoja_routes,
                hoja_routes.hoja_cotejo_index,
                {**common, "authorized_name": None},
                "template",
            ),
            (
                hoja_routes,
                hoja_routes.hoja_cotejo_pdf,
                {**common, "authorized_name": None},
                "pdf",
            ),
            (
                hoja_routes,
                hoja_routes.hoja_cotejo_excel,
                {**common, "authorized_name": None},
                "excel",
            ),
        ]

        for module, endpoint, kwargs, response_kind in cases:
            with self.subTest(endpoint=endpoint.__name__):
                self._assert_endpoint_forces_active_residential(
                    module,
                    endpoint,
                    kwargs,
                    response_kind,
                )

    def test_generate_redirects_include_the_forced_active_residential(self):
        request = _Request(ACTIVE_RESIDENTIAL_ID)
        user = _user("admin", ACTIVE_RESIDENTIAL_ID)
        common: dict[str, Any] = {
            "request": request,
            "month": 8,
            "year": 2026,
            "period_type": "monthly",
            "start_date": None,
            "end_date": None,
            "proposal_id": "3",
            "residential_id": None,
            "output": "pdf",
            "current_user": user,
        }

        responses = (
            consolidado_routes.consolidado_mensual_global_generar(
                **common,
                authorized_name=None,
            ),
            plantilla_routes.plantilla_duplicado_generar(**common),
            hoja_routes.hoja_cotejo_generar(
                **common,
                authorized_name=None,
            ),
        )

        for response in responses:
            with self.subTest(location=response.headers["location"]):
                self.assertEqual(response.status_code, 303)
                self.assertIn(
                    f"residential_id={ACTIVE_RESIDENTIAL_ID}",
                    response.headers["location"],
                )

    def test_visual_preview_forces_active_residential(self):
        template = SimpleNamespace(
            report_key="hoja_cotejo_admin",
            name="Hoja de Cotejo",
        )
        user = _user("admin", ACTIVE_RESIDENTIAL_ID)
        db = _Database(objects={(ReportTemplate, 5): template})

        with (
            patch.object(
                admin_routes,
                "build_hoja_cotejo_admin_context",
                return_value={"program_blocks": []},
            ) as builder,
            patch.object(
                admin_routes.templates,
                "TemplateResponse",
                return_value=SimpleNamespace(status_code=200),
            ),
        ):
            admin_routes.admin_report_template_versions_preview_visual(
                request=_Request(ACTIVE_RESIDENTIAL_ID),
                report_template_id=5,
                version_label="",
                header_image=None,
                header_title=None,
                header_subtitle=None,
                header_notes=None,
                footer_image=None,
                footer_text=None,
                signature_1_label=None,
                signature_1_title=None,
                signature_2_label=None,
                signature_2_title=None,
                date_label=None,
                margin_top=None,
                margin_right=None,
                margin_bottom=None,
                margin_left=None,
                table_spacing=None,
                rows_per_table=None,
                columns_text=None,
                preview_proposal_id=3,
                preview_month=8,
                preview_year=2026,
                preview_period_type="monthly",
                preview_start_date=None,
                preview_end_date=None,
                preview_authorized_name=None,
                db=db,
                current_user=user,
            )

        self.assertEqual(
            builder.call_args.kwargs["residential_id"],
            ACTIVE_RESIDENTIAL_ID,
        )

    def test_hoja_cotejo_form_preserves_residential_scope(self):
        source, _, _ = hoja_routes.templates.env.loader.get_source(
            hoja_routes.templates.env,
            "ui/admin/hoja_cotejo.html",
        )

        self.assertEqual(source.count('name="residential_id"'), 2)
        self.assertNotIn("Alcance:</strong> Global, no por residencial", source)

    def test_residential_mode_limits_route_filter_options(self):
        residential = _residential(ACTIVE_RESIDENTIAL_ID, "Residencial Activo")
        user = _user("admin", ACTIVE_RESIDENTIAL_ID)

        for module, service_name in (
            (consolidado_routes, "build_consolidado_mensual_global"),
            (plantilla_routes, "build_plantilla_duplicado_context"),
        ):
            db = _Database(
                results=[
                    _Result(values=[]),
                    _Result(values=[residential]),
                ]
            )
            with patch.object(module, service_name, return_value={}):
                context = module._build_context(
                    db,
                    user,
                    8,
                    2026,
                    None,
                    ACTIVE_RESIDENTIAL_ID,
                )

            with self.subTest(module=module.__name__):
                self.assertEqual(context["residentials"], [residential])
                self.assertIn(
                    "residentials.residential_id",
                    str(db.statements[1]).lower(),
                )
                self.assertTrue(
                    _statement_has_value(db.statements[1], ACTIVE_RESIDENTIAL_ID)
                )

    def test_consolidado_service_filters_residential_rows_and_sessions(self):
        residential = _residential(ACTIVE_RESIDENTIAL_ID, "Residencial Activo")
        db = _Database(
            results=[
                _Result(values=[residential]),
                _Result(values=[]),
            ]
        )

        context = consolidado_service.build_consolidado_mensual_global(
            db,
            month=8,
            year=2026,
            residential_id=ACTIVE_RESIDENTIAL_ID,
        )

        self.assertEqual(context["selected_residential_id"], ACTIVE_RESIDENTIAL_ID)
        self.assertEqual(
            [row["residential_id"] for row in context["rows"]],
            [ACTIVE_RESIDENTIAL_ID],
        )
        self.assertEqual(len(db.statements), 2)
        self.assertIn("residentials.residential_id", str(db.statements[0]).lower())
        self.assertIn("activity_sessions.residential_id", str(db.statements[1]).lower())
        for statement in db.statements:
            self.assertTrue(_statement_has_value(statement, ACTIVE_RESIDENTIAL_ID))

    def test_hoja_service_filters_residential_list_and_related_session_queries(self):
        residential = _residential(ACTIVE_RESIDENTIAL_ID, "Residencial Activo")
        proposal = SimpleNamespace(proposal_id=3, code="P3", name="Propuesta 3")
        program = SimpleNamespace(code="PRG", name="Programa")
        structure = [
            {
                "program": program,
                "population_blocks": [
                    {
                        "rows": [
                            {
                                "activity_code_id": 11,
                                "activity_code": "A-11",
                                "activity_description": "Actividad",
                            }
                        ]
                    }
                ],
            }
        ]
        db = _Database(
            objects={(Proposal, 3): proposal},
            results=[
                _Result(values=[residential]),
                _Result(scalar=date(2026, 1, 15)),
                _Result(values=[(11, 1)]),
                _Result(values=[(11, 2, 1)]),
                _Result(values=[(11, 3)]),
                _Result(values=[]),
                _Result(values=[proposal]),
            ],
        )

        with patch.object(
            hoja_service,
            "resolve_effective_program_population_blocks",
            return_value=structure,
        ):
            context = hoja_service.build_hoja_cotejo_admin_context(
                db,
                month=8,
                year=2026,
                proposal_id=3,
                residential_id=ACTIVE_RESIDENTIAL_ID,
            )

        self.assertEqual(context["selected_residential_id"], ACTIVE_RESIDENTIAL_ID)
        self.assertFalse(context["is_all_residentials"])
        self.assertEqual(context["active_residential_count"], 1)
        self.assertEqual(context["residential_names"], "Residencial Activo")
        self.assertEqual(len(db.statements), 7)

        residential_statement = db.statements[0]
        self.assertIn(
            "residentials.residential_id",
            str(residential_statement).lower(),
        )
        self.assertTrue(
            _statement_has_value(residential_statement, ACTIVE_RESIDENTIAL_ID)
        )

        for statement in db.statements[1:5]:
            with self.subTest(statement=str(statement)):
                self.assertIn(
                    "activity_sessions.residential_id",
                    str(statement).lower(),
                )
                self.assertTrue(
                    _statement_has_value(statement, ACTIVE_RESIDENTIAL_ID)
                )

    def test_hoja_service_preserves_the_global_residential_list(self):
        residentials = [
            _residential(ACTIVE_RESIDENTIAL_ID, "Residencial Activo"),
            _residential(OTHER_RESIDENTIAL_ID, "Otro Residencial"),
        ]
        db = _Database(
            results=[
                _Result(values=residentials),
                _Result(values=[]),
            ]
        )

        context = hoja_service.build_hoja_cotejo_admin_context(
            db,
            month=8,
            year=2026,
        )

        self.assertTrue(context["is_all_residentials"])
        self.assertEqual(context["active_residential_count"], 2)
        self.assertEqual(
            context["residential_names"],
            "Residencial Activo, Otro Residencial",
        )
        self.assertNotIn(
            "residentials.residential_id =",
            str(db.statements[0]).lower(),
        )


if __name__ == "__main__":
    unittest.main()
