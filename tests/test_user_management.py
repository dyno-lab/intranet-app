from __future__ import annotations

import os
import unittest
from urllib.parse import parse_qs, urlparse


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")

from app.api.routes import admin, auth  # noqa: E402
from app.db.schema import PLATFORM_SETTINGS_SQL, PLATFORM_SETTINGS_USER_COLUMNS_SQL  # noqa: E402
from app.models.platform_user_audit import PlatformUserAudit  # noqa: E402
from app.models.residential import Residential  # noqa: E402
from app.core.auth import get_current_user  # noqa: E402
from app.core.platform_permissions import MANAGE_PLATFORM_SETTINGS  # noqa: E402
from app.models.user import User  # noqa: E402


class _Request:
    def __init__(self, session: dict | None = None):
        self.session = session if session is not None else {}
        if "user_id" in self.session and "session_version" not in self.session:
            self.session["session_version"] = 1


class _Result:
    def __init__(self, values: list | None = None, scalar=None):
        self.values = values or []
        self.scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self.values

    def first(self):
        if self.scalar is not None:
            return self.scalar
        return self.values[0] if self.values else None

    def scalar_one_or_none(self):
        return self.scalar


class _Database:
    def __init__(self, *, objects: dict | None = None, results: list[_Result] | None = None):
        self.objects = objects or {}
        self.results = list(results or [])
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    def get(self, model, object_id):
        return self.objects.get((model, object_id))

    def execute(self, statement):
        if not self.results:
            raise AssertionError("Unexpected database query")
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        self.flushes += 1
        for value in self.added:
            if isinstance(value, User) and value.user_id is None:
                value.user_id = 100

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _user(
    user_id: int,
    *,
    email: str = "employee@csifpr.org",
    google_sub: str | None = None,
    is_active: bool = True,
    local_login_enabled: bool = True,
    role: str = "admin",
) -> User:
    user = User(
        username=email,
        email=email,
        google_sub=google_sub,
        password_hash="$2b$12$invalid-but-not-rendered",
        local_login_enabled=local_login_enabled,
        role=role,
        is_active=is_active,
        session_version=1,
    )
    user.user_id = user_id
    return user


def _residential(residential_id: int = 1) -> Residential:
    residential = Residential(
        code="TEST",
        name="Residencial Test",
        municipality="Municipio",
        rq_code="RQ-TEST",
        is_active=True,
    )
    residential.residential_id = residential_id
    return residential


def _message(response) -> str:
    return parse_qs(urlparse(response.headers["location"]).query)["msg"][0]


class UserManagementTests(unittest.TestCase):
    def setUp(self):
        self.manager = _user(1, email="manager@csifpr.org")
        self.request = _Request({
            "user_id": self.manager.user_id,
            admin._USER_CSRF_SESSION_KEY: "valid-csrf",
        })

    def test_user_management_template_compiles(self):
        template = admin.templates.get_template("ui/admin/users.html")
        self.assertEqual(template.name, "ui/admin/users.html")

    def test_non_admin_cannot_manage_users_even_with_settings_permission(self):
        non_admin = _user(3, email="manager.user@csifpr.org", role="user")
        request = _Request({"user_id": non_admin.user_id})
        db = _Database(
            objects={(User, non_admin.user_id): non_admin},
            results=[_Result(values=[MANAGE_PLATFORM_SETTINGS])],
        )
        with self.assertRaises(Exception) as raised:
            admin._require_admin_user_manager(request=request, db=db)
        self.assertEqual(getattr(raised.exception, "status_code", None), 403)

    def test_changed_session_version_revokes_existing_session(self):
        target = _user(2)
        target.session_version = 2
        request = _Request({"user_id": target.user_id, "session_version": 1})
        db = _Database(objects={(User, target.user_id): target})
        with self.assertRaises(Exception) as raised:
            get_current_user(request=request, db=db)
        self.assertEqual(getattr(raised.exception, "status_code", None), 303)
        self.assertEqual(request.session, {})

    def test_schema_adds_local_login_and_audit_retention(self):
        self.assertIn("local_login_enabled BIT NOT NULL", PLATFORM_SETTINGS_USER_COLUMNS_SQL)
        self.assertIn("session_version INT NOT NULL", PLATFORM_SETTINGS_USER_COLUMNS_SQL)
        self.assertIn("CREATE TABLE dbo.platform_user_audit", PLATFORM_SETTINGS_SQL)
        self.assertIn("DATEADD(DAY, -365", PLATFORM_SETTINGS_SQL)

    def test_only_institutional_email_is_accepted(self):
        self.assertEqual(
            admin._normalized_authorized_email(" Employee@CSIFPR.ORG "),
            "employee@csifpr.org",
        )
        for email in ("employee@example.org", "@csifpr.org", "invalid"):
            with self.subTest(email=email):
                self.assertIsNone(admin._normalized_authorized_email(email))

    def test_create_google_only_user_preserves_residential_scope_and_audits(self):
        residential = _residential()
        db = _Database(
            objects={(Residential, residential.residential_id): residential},
            results=[_Result(values=[])],
        )

        response = admin.admin_create_user(
            request=self.request,
            email=" Employee@CSIFPR.ORG ",
            username=None,
            password=None,
            local_login_enabled=None,
            role="user",
            residential_id=residential.residential_id,
            csrf_token="valid-csrf",
            db=db,
            current_user=self.manager,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(db.commits, 1)
        self.assertEqual(db.flushes, 1)
        created_user = next(value for value in db.added if isinstance(value, User))
        audit = next(value for value in db.added if isinstance(value, PlatformUserAudit))
        self.assertEqual(created_user.email, "employee@csifpr.org")
        self.assertEqual(created_user.username, "employee@csifpr.org")
        self.assertFalse(created_user.local_login_enabled)
        self.assertEqual(created_user.residential_id, residential.residential_id)
        self.assertEqual(audit.action, "user_created")
        self.assertEqual(audit.target_user_id, created_user.user_id)

    def test_create_rejects_external_email_before_writing(self):
        db = _Database()
        response = admin.admin_create_user(
            request=self.request,
            email="employee@example.org",
            username=None,
            password=None,
            local_login_enabled=None,
            role="admin",
            residential_id=None,
            csrf_token="valid-csrf",
            db=db,
            current_user=self.manager,
        )
        self.assertIn("@csifpr.org", _message(response))
        self.assertEqual(db.added, [])
        self.assertEqual(db.commits, 0)

    def test_invalid_csrf_rejects_user_mutation(self):
        with self.assertRaises(Exception) as raised:
            admin.admin_create_user(
                request=self.request,
                email="employee@csifpr.org",
                username=None,
                password=None,
                local_login_enabled=None,
                role="admin",
                residential_id=None,
                csrf_token="wrong",
                db=_Database(),
                current_user=self.manager,
            )
        self.assertEqual(getattr(raised.exception, "status_code", None), 403)

    def test_linked_google_email_cannot_change(self):
        target = _user(2, google_sub="google-subject")
        db = _Database(objects={(User, target.user_id): target})
        response = admin.admin_edit_user(
            user_id=target.user_id,
            request=self.request,
            email="replacement@csifpr.org",
            username=target.username,
            role="admin",
            residential_id=None,
            is_active="on",
            local_login_enabled="on",
            new_password=None,
            csrf_token="valid-csrf",
            db=db,
            current_user=self.manager,
        )
        self.assertIn("desvincule Google", _message(response))
        self.assertEqual(target.email, "employee@csifpr.org")
        self.assertEqual(db.commits, 0)

    def test_manager_cannot_deactivate_self(self):
        db = _Database(objects={(User, self.manager.user_id): self.manager})
        response = admin.admin_edit_user(
            user_id=self.manager.user_id,
            request=self.request,
            email=self.manager.email,
            username=self.manager.username,
            role="admin",
            residential_id=None,
            is_active=None,
            local_login_enabled="on",
            new_password=None,
            csrf_token="valid-csrf",
            db=db,
            current_user=self.manager,
        )
        self.assertIn("propia cuenta", _message(response))
        self.assertTrue(self.manager.is_active)

    def test_google_unlink_requires_controlled_administrative_process(self):
        target = _user(2, google_sub="google-subject", is_active=False)
        db = _Database(objects={(User, target.user_id): target})
        response = admin.admin_unlink_google_user(
            user_id=target.user_id,
            request=self.request,
            csrf_token="valid-csrf",
            db=db,
            current_user=self.manager,
        )
        self.assertIn("proceso administrativo controlado", _message(response))
        self.assertEqual(target.google_sub, "google-subject")
        self.assertEqual(db.commits, 0)

    def test_local_login_disabled_user_is_rejected(self):
        target = _user(2, local_login_enabled=False)
        response = auth.login(
            request=_Request(),
            username=target.username,
            password="irrelevant",
            db=_Database(results=[_Result(scalar=target)]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("user_id", response.context["request"].session)


if __name__ == "__main__":
    unittest.main()
