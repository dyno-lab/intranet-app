from __future__ import annotations

import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from app.api.routes import reports  # noqa: E402
from app.core import residential_scope  # noqa: E402
from app.core.auth import is_admin_or_supervisor  # noqa: E402
from app.core.platform_permissions import (  # noqa: E402
    MANAGE_PLATFORM_SETTINGS,
    user_has_platform_permission,
)
from app.core.residential_scope import (  # noqa: E402
    require_faro_access,
    require_write_residential_id,
)
from app.core.roles import (  # noqa: E402
    VALID_USER_ROLES,
    VIEWER_AUTHORIZED_NAME,
    can_read_globally,
    is_viewer,
    report_authorized_name,
)
from app.models.user import User  # noqa: E402


class _URL:
    def __init__(self, path: str, query: str = "") -> None:
        self.path: str = path
        self.query: str = query


class _Request:
    def __init__(
        self,
        *,
        method: str = "GET",
        path: str = "/ui/new-list",
        query: str = "",
        session: dict[str, object] | None = None,
    ) -> None:
        self.method: str = method
        self.url: _URL = _URL(path, query)
        self.session: dict[str, object] = session if session is not None else {}


class _PermissionResult:
    def __init__(self, values: list[str]) -> None:
        self.values: list[str] = values

    def scalars(self) -> _PermissionResult:
        return self

    def all(self) -> list[str]:
        return self.values


class _PermissionDatabase:
    def __init__(self) -> None:
        self.statements: list[object] = []

    def execute(self, statement: object) -> _PermissionResult:
        self.statements.append(statement)
        return _PermissionResult([MANAGE_PLATFORM_SETTINGS])


def _user(role: str) -> User:
    user = User(
        username=f"{role}@csifpr.org",
        email=f"{role}@csifpr.org",
        password_hash="not-rendered",
        role=role,
        is_active=True,
        local_login_enabled=False,
        session_version=1,
    )
    user.user_id = 7
    return user


class ViewerReadOnlyTests(unittest.TestCase):
    def test_viewer_is_a_global_reader_but_not_a_privileged_writer(self):
        viewer = _user("viewer")

        self.assertIn("viewer", VALID_USER_ROLES)
        self.assertTrue(is_viewer(viewer))
        self.assertTrue(can_read_globally(viewer))
        self.assertFalse(is_admin_or_supervisor(viewer))

    def test_viewer_can_open_a_normal_faro_get(self):
        viewer = _user("viewer")
        request = _Request(method="GET", path="/ui/new-list")

        with (
            patch.object(
                residential_scope,
                "_FARO_PERMISSION_DEPENDENCY",
                return_value=viewer,
            ),
            patch.object(
                residential_scope,
                "assigned_residentials",
                return_value=[],
            ),
        ):
            resolved_user = require_faro_access(request=request, db=object())

        self.assertIs(resolved_user, viewer)

    def test_viewer_cannot_open_admin_or_participant_edit_pages(self):
        viewer = _user("viewer")
        forbidden_paths = (
            "/ui/admin",
            "/ui/admin/users",
            "/ui/new-list/42/edit",
        )

        for path in forbidden_paths:
            with self.subTest(path=path):
                request = _Request(method="GET", path=path)
                with (
                    patch.object(
                        residential_scope,
                        "_FARO_PERMISSION_DEPENDENCY",
                        return_value=viewer,
                    ),
                    self.assertRaises(HTTPException) as context,
                ):
                    require_faro_access(request=request, db=object())

                self.assertEqual(context.exception.status_code, 403)

    def test_viewer_cannot_use_mutating_http_methods(self):
        viewer = _user("viewer")
        mutating_requests = (
            ("POST", "/ui/new-list"),
            ("POST", "/ui/new-list/42/edit"),
            ("POST", "/ui/new-list/42/delete"),
            ("PUT", "/api/participants/42"),
            ("PATCH", "/api/participants/42"),
            ("DELETE", "/api/participants/42"),
        )

        for method, path in mutating_requests:
            with self.subTest(method=method, path=path):
                request = _Request(method=method, path=path)
                with (
                    patch.object(
                        residential_scope,
                        "_FARO_PERMISSION_DEPENDENCY",
                        return_value=viewer,
                    ),
                    self.assertRaises(HTTPException) as context,
                ):
                    require_faro_access(request=request, db=object())

                self.assertEqual(context.exception.status_code, 403)

    def test_viewer_can_post_notes_pdf_generation(self):
        viewer = _user("viewer")
        request = _Request(method="POST", path="/ui/reports/notas/pdf")

        with (
            patch.object(
                residential_scope,
                "_FARO_PERMISSION_DEPENDENCY",
                return_value=viewer,
            ),
            patch.object(
                residential_scope,
                "assigned_residentials",
                return_value=[],
            ),
        ):
            resolved_user = require_faro_access(request=request, db=object())

        self.assertIs(resolved_user, viewer)

    def test_viewer_cannot_resolve_a_write_residential(self):
        viewer = _user("viewer")

        with self.assertRaises(HTTPException) as context:
            require_write_residential_id(
                _Request(),
                viewer,
                object(),
                requested_residential_id=1,
            )

        self.assertEqual(context.exception.status_code, 403)

    def test_only_viewer_authorized_name_is_replaced(self):
        viewer = _user("viewer")
        supervisor = _user("supervisor")

        self.assertEqual(
            report_authorized_name(viewer, "Directora Regional"),
            VIEWER_AUTHORIZED_NAME,
        )
        self.assertEqual(
            report_authorized_name(supervisor, "  Directora Regional  "),
            "Directora Regional",
        )

    def test_report_redirect_uses_viewer_authorized_name_placeholder(self):
        response = reports.reports_run(
            report_key="adm",
            proposal_id=1,
            month=None,
            year=None,
            employee_id=None,
            output="screen",
            period_type="monthly",
            authorized_name="Directora Regional",
            start_date=None,
            end_date=None,
            current_user=_user("viewer"),
        )
        query = parse_qs(urlparse(response.headers["location"]).query)

        self.assertEqual(query["authorized_name"], [VIEWER_AUTHORIZED_NAME])

    def test_viewer_cannot_manage_settings_even_if_permission_is_assigned(self):
        viewer = _user("viewer")
        db = _PermissionDatabase()

        self.assertFalse(
            user_has_platform_permission(db, viewer, MANAGE_PLATFORM_SETTINGS)
        )
        self.assertEqual(db.statements, [])


if __name__ == "__main__":
    unittest.main()
