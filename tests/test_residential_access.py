from __future__ import annotations

import os
import re
import unittest
from unittest.mock import patch

from fastapi import HTTPException


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from app.core.config import settings as app_settings  # noqa: E402

app_settings.SESSION_SECRET = "test-session-secret-at-least-32-characters"

from app import main as app_main  # noqa: E402
from app.api.routes import auth, automation_reports, platform_settings, portal, residential_context  # noqa: E402
from app.core.platform_permissions import (  # noqa: E402
    ACCESS_AUTOMATION,
    ACCESS_FARO,
    ACCESS_INSTITUTIONAL_REPORTS,
    ACCESS_PORTAL_HOME,
)
from app.core.residential_scope import (  # noqa: E402
    ACTIVE_RESIDENTIAL_NAME_SESSION_KEY,
    ACTIVE_RESIDENTIAL_SESSION_KEY,
    AVAILABLE_RESIDENTIAL_COUNT_SESSION_KEY,
    require_faro_access,
    resolve_active_residential,
    user_can_read_record,
)
from app.models.platform_user_audit import PlatformUserAudit  # noqa: E402
from app.models.residential import Residential  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.user_residential import UserResidential  # noqa: E402


class _URL:
    path = "/ui/new-list"
    query = ""


class _Request:
    def __init__(self, session: dict | None = None):
        self.session = session if session is not None else {}
        self.url = _URL()

    def url_for(self, name: str, **path_params) -> str:
        if name != "static":
            raise AssertionError(f"Unexpected route name: {name}")
        return f"/static/{path_params['path']}"


class _Result:
    def __init__(self, values: list | None = None, scalar=None):
        self.values = values or []
        self.scalar_value = scalar

    def scalars(self):
        return self

    def all(self):
        return self.values

    def scalar_one_or_none(self):
        return self.scalar_value


class _Database:
    def __init__(self, *, objects: dict | None = None, results: list[_Result] | None = None):
        self.objects = objects or {}
        self.results = list(results or [])
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.get_calls = []

    def get(self, model, object_id):
        self.get_calls.append((model, object_id))
        return self.objects.get((model, object_id))

    def execute(self, statement):
        if not self.results:
            raise AssertionError("Unexpected database query")
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _user(user_id: int, *, role: str = "user") -> User:
    user = User(
        username=f"user{user_id}@csifpr.org",
        email=f"user{user_id}@csifpr.org",
        password_hash="not-rendered",
        role=role,
        is_active=True,
        local_login_enabled=False,
        session_version=1,
    )
    user.user_id = user_id
    return user


def _residential(residential_id: int, code: str) -> Residential:
    residential = Residential(
        code=code,
        name=f"Residencial {code}",
        municipality="Municipio",
        rq_code=f"RQ-{code}",
        is_active=True,
    )
    residential.residential_id = residential_id
    return residential


class ResidentialAccessTests(unittest.TestCase):
    def test_assembled_app_applies_module_guards(self):
        included_routers = [
            route
            for route in app_main.app.routes
            if hasattr(route, "original_router") and hasattr(route, "include_context")
        ]

        def dependency_calls(included_router):
            return [
                dependency.dependency
                for dependency in included_router.include_context.dependencies
            ]

        def included_for(router):
            return next(
                included_router
                for included_router in included_routers
                if included_router.original_router is router
            )

        faro_routers = (
            app_main.ui_router,
            app_main.admin_router,
            app_main.catalogs_router,
            app_main.consolidado_mensual_global_router,
            app_main.plantilla_duplicado_router,
            app_main.hoja_cotejo_admin_router,
            app_main.school_grades_router,
            app_main.school_dropout_router,
            app_main.pregnancy_router,
            app_main.reports_router,
            app_main.sessions_router,
            app_main.participants_router,
            app_main.attendance_router,
            app_main.employees_router,
            app_main.activity_codes_router,
        )
        for router in faro_routers:
            calls = dependency_calls(included_for(router))
            with self.subTest(router=router):
                self.assertIn(
                    "require_faro_access",
                    {getattr(call, "__name__", "") for call in calls},
                )

        institutional_calls = dependency_calls(
            included_for(app_main.institutional_reports_router)
        )
        permission_dependencies = [
            call
            for call in institutional_calls
            if getattr(call, "__module__", "") == "app.core.platform_permissions"
        ]
        self.assertTrue(permission_dependencies)
        self.assertTrue(
            any(
                ACCESS_INSTITUTIONAL_REPORTS
                in [cell.cell_contents for cell in (call.__closure__ or ())]
                for call in permission_dependencies
            )
        )

        platform_calls = dependency_calls(included_for(app_main.platform_settings_router))
        self.assertNotIn(
            "require_faro_access",
            {getattr(call, "__name__", "") for call in platform_calls},
        )

    def test_selector_next_path_rejects_external_and_self_redirects(self):
        self.assertEqual(
            residential_context._safe_next_path("https://attacker.example"),
            "/ui",
        )
        self.assertEqual(
            residential_context._safe_next_path("/ui/context/residential"),
            "/ui",
        )
        self.assertEqual(
            residential_context._safe_next_path("/ui/context/residential/?next=/ui"),
            "/ui",
        )
        self.assertEqual(
            residential_context._safe_next_path("/ui/new-list"),
            "/ui/new-list",
        )

    def test_residential_templates_compile_without_corrupted_html(self):
        template_names = (
            "auth/login.html",
            "portal/access_denied.html",
            "platform_settings/index.html",
        )
        forbidden_fragments = (
            "</head>=",
            "<title</head>",
            "</title>itado",
            "class</div>=",
            "<span</div>",
            "<</div>strong",
            "<s</div>trong>",
            "</d</span>iv>",
            "<o</select>ption",
            "<strong>Residencia</strong>l",
        )
        for template_name in template_names:
            with self.subTest(template=template_name):
                template = auth.templates.get_template(template_name)
                source, _, _ = auth.templates.env.loader.get_source(
                    auth.templates.env,
                    template_name,
                )
                self.assertEqual(template.name, template_name)
                for fragment in forbidden_fragments:
                    self.assertNotIn(fragment, source)

    def test_single_assignment_is_selected_and_stale_context_is_replaced(self):
        user = _user(7)
        residential = _residential(2, "B")
        request = _Request({
            ACTIVE_RESIDENTIAL_SESSION_KEY: 999,
            ACTIVE_RESIDENTIAL_NAME_SESSION_KEY: "Residencial anterior",
        })
        db = _Database(results=[_Result(values=[residential])])

        active, available = resolve_active_residential(request, db, user)

        self.assertIs(active, residential)
        self.assertEqual(available, [residential])
        self.assertEqual(request.session[ACTIVE_RESIDENTIAL_SESSION_KEY], 2)
        self.assertEqual(
            request.session[ACTIVE_RESIDENTIAL_NAME_SESSION_KEY],
            residential.name,
        )
        self.assertEqual(request.session[AVAILABLE_RESIDENTIAL_COUNT_SESSION_KEY], 1)

    def test_selector_route_auto_selects_single_residential(self):
        user = _user(7)
        residential = _residential(2, "B")
        request = _Request()
        db = _Database(results=[_Result(values=[residential])])

        response = residential_context.residential_context_page(
            request=request,
            next_path="/ui",
            db=db,
            current_user=user,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/ui")
        self.assertEqual(request.session[ACTIVE_RESIDENTIAL_SESSION_KEY], 2)

    def test_multiple_assignments_require_an_explicit_selection(self):
        user = _user(7)
        residentials = [_residential(1, "A"), _residential(2, "B")]
        request = _Request()

        active, available = resolve_active_residential(
            request,
            _Database(results=[_Result(values=residentials)]),
            user,
        )

        self.assertIsNone(active)
        self.assertEqual(available, residentials)
        self.assertNotIn(ACTIVE_RESIDENTIAL_SESSION_KEY, request.session)
        self.assertEqual(request.session[AVAILABLE_RESIDENTIAL_COUNT_SESSION_KEY], 2)

    def test_faro_redirects_multi_residential_user_to_selector(self):
        user = _user(7)
        residentials = [_residential(1, "A"), _residential(2, "B")]
        request = _Request({"user_id": user.user_id, "session_version": 1})
        db = _Database(
            objects={(User, user.user_id): user},
            results=[
                _Result(values=[ACCESS_FARO]),
                _Result(values=residentials),
            ],
        )

        with self.assertRaises(HTTPException) as context:
            require_faro_access(request=request, db=db)

        self.assertEqual(context.exception.status_code, 303)
        self.assertIn("/login?next=", context.exception.headers["Location"])

    def test_admin_and_supervisor_bypass_residential_selection(self):
        for role in ("admin", "supervisor"):
            with self.subTest(role=role):
                user = _user(7, role=role)
                request = _Request({
                    "user_id": user.user_id,
                    "session_version": 1,
                    ACTIVE_RESIDENTIAL_SESSION_KEY: 99,
                    ACTIVE_RESIDENTIAL_NAME_SESSION_KEY: "Anterior",
                })
                db = _Database(
                    objects={(User, user.user_id): user},
                    results=[_Result(values=[ACCESS_FARO])],
                )

                resolved_user = require_faro_access(request=request, db=db)

                self.assertIs(resolved_user, user)
                self.assertNotIn(ACTIVE_RESIDENTIAL_SESSION_KEY, request.session)
                self.assertNotIn(ACTIVE_RESIDENTIAL_NAME_SESSION_KEY, request.session)
                self.assertEqual(db.results, [])

    def test_selector_route_redirects_admin_and_supervisor_without_querying_assignments(self):
        for role in ("admin", "supervisor"):
            with self.subTest(role=role):
                user = _user(7, role=role)
                request = _Request({ACTIVE_RESIDENTIAL_SESSION_KEY: 99})
                db = _Database()

                response = residential_context.residential_context_page(
                    request=request,
                    next_path="/ui",
                    db=db,
                    current_user=user,
                )

                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], "/ui")
                self.assertNotIn(ACTIVE_RESIDENTIAL_SESSION_KEY, request.session)
                self.assertEqual(db.results, [])

    def test_legacy_selector_redirects_multi_residential_user_to_login(self):
        user = _user(7)
        residentials = [_residential(1, "A"), _residential(2, "B")]
        request = _Request()
        db = _Database(results=[_Result(values=residentials)])

        response = residential_context.residential_context_page(
            request=request,
            next_path="/ui",
            db=db,
            current_user=user,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login?next=%2Fui")

    def test_login_embeds_residential_selector_for_authenticated_user(self):
        user = _user(7)
        residentials = [_residential(1, "A"), _residential(2, "B")]
        request = _Request({"user_id": user.user_id, "session_version": 1})
        db = _Database(
            objects={(User, user.user_id): user},
            results=[
                _Result(values=[ACCESS_FARO]),
                _Result(values=residentials),
            ],
        )

        response = auth.login_page(
            request=request,
            next_path="/ui/new-list",
            db=db,
        )
        body = response.body.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Acceso institucional aprobado", body)
        self.assertIn("Residencial de trabajo", body)
        self.assertIn("Residencial A", body)
        self.assertIn("Residencial B", body)
        self.assertIn('action="/login/faro"', body)
        self.assertIn('<select id="residential-id"', body)
        self.assertEqual(body.count('<option value="'), 3)
        self.assertRegex(
            body,
            re.compile(r'<option value="1"[^>]*>\s*A · Residencial A · Municipio\s*</option>'),
        )
        self.assertRegex(
            body,
            re.compile(r'<option value="2"[^>]*>\s*B · Residencial B · Municipio\s*</option>'),
        )
        self.assertNotIn('name="password"', body)

    def test_login_shows_entry_actions_without_selector_for_admin_and_supervisor(self):
        for role in ("admin", "supervisor"):
            with self.subTest(role=role):
                user = _user(7, role=role)
                request = _Request({"user_id": user.user_id, "session_version": 1})
                db = _Database(
                    objects={(User, user.user_id): user},
                    results=[_Result(values=[ACCESS_FARO])],
                )

                response = auth.login_page(
                    request=request,
                    next_path="/ui/new-list",
                    db=db,
                )
                body = response.body.decode("utf-8")

                self.assertEqual(response.status_code, 200)
                self.assertIn("Entrar a Faro", body)
                self.assertIn(">Entrar</button>", body)
                self.assertIn("Volver a Home", body)
                self.assertNotIn("Residencial de trabajo", body)
                self.assertEqual(db.results, [])

    def test_login_entry_sets_only_an_assigned_residential(self):
        user = _user(7)
        residentials = [_residential(1, "A"), _residential(2, "B")]
        request = _Request({
            "user_id": user.user_id,
            "session_version": 1,
            auth._FARO_LOGIN_CSRF_SESSION_KEY: "valid-token",
        })
        db = _Database(
            objects={(User, user.user_id): user},
            results=[
                _Result(values=[ACCESS_FARO]),
                _Result(values=residentials),
            ],
        )

        response = auth.enter_faro(
            request=request,
            residential_id=2,
            next_path="/ui/new-list",
            csrf_token="valid-token",
            db=db,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/ui/new-list")
        self.assertEqual(request.session[ACTIVE_RESIDENTIAL_SESSION_KEY], 2)
        self.assertEqual(request.session[AVAILABLE_RESIDENTIAL_COUNT_SESSION_KEY], 2)

    def test_login_entry_rejects_unassigned_residential(self):
        user = _user(7)
        request = _Request({
            "user_id": user.user_id,
            "session_version": 1,
            auth._FARO_LOGIN_CSRF_SESSION_KEY: "valid-token",
        })
        db = _Database(
            objects={(User, user.user_id): user},
            results=[
                _Result(values=[ACCESS_FARO]),
                _Result(values=[_residential(1, "A"), _residential(2, "B")]),
            ],
        )

        with self.assertRaises(HTTPException) as context:
            auth.enter_faro(
                request=request,
                residential_id=99,
                next_path="/ui/new-list",
                csrf_token="valid-token",
                db=db,
            )

        self.assertEqual(context.exception.status_code, 403)
        self.assertNotIn(ACTIVE_RESIDENTIAL_SESSION_KEY, request.session)

    def test_admin_and_supervisor_enter_faro_without_residential_query(self):
        for role in ("admin", "supervisor"):
            with self.subTest(role=role):
                user = _user(7, role=role)
                request = _Request({
                    "user_id": user.user_id,
                    "session_version": 1,
                    auth._FARO_LOGIN_CSRF_SESSION_KEY: "valid-token",
                    ACTIVE_RESIDENTIAL_SESSION_KEY: 99,
                })
                db = _Database(
                    objects={(User, user.user_id): user},
                    results=[_Result(values=[ACCESS_FARO])],
                )

                response = auth.enter_faro(
                    request=request,
                    residential_id=None,
                    next_path="/ui/new-list",
                    csrf_token="valid-token",
                    db=db,
                )

                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], "/ui/new-list")
                self.assertNotIn(ACTIVE_RESIDENTIAL_SESSION_KEY, request.session)
                self.assertEqual(db.results, [])

    def test_faro_login_rejects_invalid_csrf_and_external_redirects(self):
        self.assertEqual(
            auth._safe_faro_next_path("https://attacker.example"),
            "/ui/new-list",
        )
        request = _Request({auth._FARO_LOGIN_CSRF_SESSION_KEY: "expected-token"})

        with self.assertRaises(HTTPException) as context:
            auth.enter_faro(
                request=request,
                residential_id=1,
                next_path="//attacker.example",
                csrf_token="wrong-token",
                db=_Database(),
            )

        self.assertEqual(context.exception.status_code, 403)

    def test_selector_rejects_unassigned_residential(self):
        user = _user(7)
        request = _Request({residential_context._CSRF_SESSION_KEY: "valid-token"})
        db = _Database(results=[_Result(values=[_residential(1, "A")])])

        with self.assertRaises(HTTPException) as context:
            residential_context.select_residential_context(
                request=request,
                residential_id=2,
                next_path="/ui",
                csrf_token="valid-token",
                db=db,
                current_user=user,
            )

        self.assertEqual(context.exception.status_code, 403)
        self.assertNotIn(ACTIVE_RESIDENTIAL_SESSION_KEY, request.session)

    def test_role_record_policy(self):
        admin = _user(1, role="admin")
        supervisor = _user(2, role="supervisor")
        user = _user(3, role="user")

        self.assertTrue(
            user_can_read_record(
                admin,
                active_residential_id=1,
                record_residential_id=99,
                created_by_user_id=88,
            )
        )
        self.assertTrue(
            user_can_read_record(
                supervisor,
                active_residential_id=1,
                record_residential_id=1,
                created_by_user_id=88,
            )
        )
        self.assertFalse(
            user_can_read_record(
                supervisor,
                active_residential_id=1,
                record_residential_id=2,
                created_by_user_id=88,
            )
        )
        self.assertTrue(
            user_can_read_record(
                user,
                active_residential_id=1,
                record_residential_id=1,
                created_by_user_id=user.user_id,
            )
        )
        self.assertTrue(
            user_can_read_record(
                user,
                active_residential_id=1,
                record_residential_id=1,
                created_by_user_id=88,
            )
        )
        self.assertFalse(
            user_can_read_record(
                user,
                active_residential_id=1,
                record_residential_id=2,
                created_by_user_id=user.user_id,
            )
        )

    def test_non_admin_settings_manager_cannot_update_residential_assignments(self):
        manager = _user(1, role="supervisor")
        request = _Request({platform_settings._CSRF_SESSION_KEY: "valid-token"})
        db = _Database()

        with self.assertRaises(HTTPException) as context:
            platform_settings.update_user_residentials(
                request=request,
                user_id=2,
                residential_ids=[1],
                primary_residential_id=1,
                csrf_token="valid-token",
                db=db,
                current_user=manager,
            )

        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(db.get_calls, [])
        self.assertEqual(db.added, [])

    def test_platform_settings_updates_multiple_assignments_and_primary(self):
        manager = _user(1, role="admin")
        target = _user(2)
        target.residential_id = 1
        existing = UserResidential(
            user_id=target.user_id,
            residential_id=1,
            assigned_by_user_id=manager.user_id,
            is_active=True,
        )
        request = _Request({platform_settings._CSRF_SESSION_KEY: "valid-token"})
        db = _Database(
            objects={(User, target.user_id): target},
            results=[
                _Result(values=[1, 2]),
                _Result(values=[existing]),
            ],
        )

        response = platform_settings.update_user_residentials(
            request=request,
            user_id=target.user_id,
            residential_ids=[1, 2],
            primary_residential_id=2,
            csrf_token="valid-token",
            db=db,
            current_user=manager,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(target.residential_id, 2)
        self.assertEqual(db.commits, 1)
        added_assignment = next(
            value for value in db.added if isinstance(value, UserResidential)
        )
        self.assertEqual(added_assignment.residential_id, 2)
        audit = next(value for value in db.added if isinstance(value, PlatformUserAudit))
        self.assertEqual(audit.action, "residential_assignments_updated")

    def test_home_only_renders_assigned_application_cards(self):
        user = _user(1)
        request = _Request({"user_id": user.user_id, "session_version": 1})
        db = _Database(
            objects={(User, user.user_id): user},
            results=[_Result(values=[ACCESS_PORTAL_HOME, ACCESS_FARO])],
        )

        response = portal.portal_home(request=request, db=db)
        body = response.body.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Faro de Esperanza", body)
        self.assertIn("/login?next=/ui/new-list", body)
        self.assertNotIn("Reportes Institucionales", body)
        self.assertNotIn("Automatizaciones", body)

    def test_automation_session_requires_explicit_permission(self):
        user = _user(1, role="admin")
        request = _Request({"user_id": user.user_id, "session_version": 1})
        denied_db = _Database(
            objects={(User, user.user_id): user},
            results=[_Result(values=[])],
        )

        with patch.object(automation_reports.settings, "AUTOMATION_API_KEY", None):
            with self.assertRaises(HTTPException) as context:
                automation_reports.require_automation_access(
                    request=request,
                    db=denied_db,
                    x_automation_token=None,
                )
        self.assertEqual(context.exception.status_code, 403)

        allowed_db = _Database(
            objects={(User, user.user_id): user},
            results=[_Result(values=[ACCESS_AUTOMATION])],
        )
        with patch.object(automation_reports.settings, "AUTOMATION_API_KEY", None):
            principal = automation_reports.require_automation_access(
                request=request,
                db=allowed_db,
                x_automation_token=None,
            )
        self.assertIs(principal, user)

    def test_session_automation_cannot_impersonate_another_user(self):
        authenticated_user = _user(1)
        db = _Database()

        self.assertIs(
            automation_reports._automation_user(
                db,
                run_as_user_id=None,
                authenticated_user=authenticated_user,
            ),
            authenticated_user,
        )
        with self.assertRaises(HTTPException) as context:
            automation_reports._automation_user(
                db,
                run_as_user_id=2,
                authenticated_user=authenticated_user,
            )
        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(db.get_calls, [])

    def test_valid_automation_token_remains_a_machine_credential(self):
        request = _Request()
        db = _Database()
        with patch.object(automation_reports.settings, "AUTOMATION_API_KEY", "machine-secret"):
            automation_reports.require_automation_access(
                request=request,
                db=db,
                x_automation_token="machine-secret",
            )
        self.assertEqual(db.get_calls, [])


if __name__ == "__main__":
    unittest.main()
