from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")

from app.api.routes import auth, platform_settings, portal  # noqa: E402
from app.core.platform_permissions import (  # noqa: E402
    MANAGE_PLATFORM_SETTINGS,
    bootstrap_platform_settings_user,
    get_optional_current_user,
    require_platform_permission,
    user_has_platform_permission,
    user_permission_keys,
)
from app.core.security import verify_password  # noqa: E402
from app.db import schema as db_schema  # noqa: E402
from app.db.schema import (  # noqa: E402
    PLATFORM_SETTINGS_SQL,
    PLATFORM_SETTINGS_USER_COLUMNS_SQL,
)
import app.models.residential  # noqa: E402, F401
from app.models.platform_permission import PlatformPermission  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.user_platform_permission import UserPlatformPermission  # noqa: E402


class _Request:
    def __init__(self, session: dict | None = None):
        self.session = session if session is not None else {}

    def url_for(self, name: str, **path_params) -> str:
        if name != "static":
            raise AssertionError(f"Unexpected route name: {name}")
        return f"/static/{path_params['path']}"


class _Result:
    def __init__(self, values: list | None = None, scalar=None):
        self._values = values if values is not None else []
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self._values

    def first(self):
        if self._scalar is not None:
            return self._scalar
        return self._values[0] if self._values else None

    def scalar_one_or_none(self):
        return self._scalar


class _Database:
    def __init__(self, *, users: dict[int, User] | None = None, results: list[_Result] | None = None):
        self.users = users or {}
        self.results = list(results or [])
        self.statements = []
        self.added = []
        self.deleted = []
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0
        self.get_calls = []

    def get(self, model, object_id):
        self.get_calls.append((model, object_id))
        if model is User:
            return self.users.get(object_id)
        return None

    def execute(self, statement):
        self.statements.append(statement)
        if not self.results:
            raise AssertionError("The endpoint executed an unexpected database query.")
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    def delete(self, value):
        self.deleted.append(value)

    def flush(self):
        self.flushes += 1
        for value in self.added:
            if isinstance(value, User) and value.user_id is None:
                value.user_id = max(self.users, default=0) + 1
                self.users[value.user_id] = value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _user(
    user_id: int,
    username: str,
    *,
    email: str | None = None,
    role: str = "user",
    is_active: bool = True,
    password_hash: str = "hash-not-for-display",
) -> User:
    user = User(
        username=username,
        email=email,
        google_sub=None,
        password_hash=password_hash,
        role=role,
        is_active=is_active,
    )
    user.user_id = user_id
    return user


def _permission(
    permission_id: int,
    key: str,
    *,
    name: str | None = None,
    is_active: bool = True,
) -> PlatformPermission:
    permission = PlatformPermission(
        key=key,
        name=name or key,
        description=f"Description for {key}",
        is_active=is_active,
        sort_order=permission_id,
    )
    permission.permission_id = permission_id
    return permission


def _body(response) -> str:
    return response.body.decode("utf-8")


def _query_parameters(response) -> dict[str, list[str]]:
    return parse_qs(urlparse(response.headers["location"]).query)


class PlatformSettingsTests(unittest.TestCase):
    def test_schema_seed_is_idempotent_and_does_not_create_bootstrap_user(self):
        self.assertIn(
            "ALTER TABLE dbo.users ADD email VARCHAR(255) NULL",
            PLATFORM_SETTINGS_USER_COLUMNS_SQL,
        )
        self.assertIn(
            "ALTER TABLE dbo.users ADD google_sub VARCHAR(255) NULL",
            PLATFORM_SETTINGS_USER_COLUMNS_SQL,
        )
        self.assertNotIn("CREATE UNIQUE INDEX", PLATFORM_SETTINGS_USER_COLUMNS_SQL)
        self.assertNotIn("ALTER TABLE dbo.users ADD email", PLATFORM_SETTINGS_SQL)
        self.assertNotIn("ALTER TABLE dbo.users ADD google_sub", PLATFORM_SETTINGS_SQL)
        self.assertIn("CREATE UNIQUE INDEX UX_users_email", PLATFORM_SETTINGS_SQL)
        self.assertIn("WHERE email IS NOT NULL", PLATFORM_SETTINGS_SQL)
        self.assertIn("CREATE UNIQUE INDEX UX_users_google_sub", PLATFORM_SETTINGS_SQL)
        self.assertIn("MERGE dbo.platform_permissions WITH (HOLDLOCK)", PLATFORM_SETTINGS_SQL)
        self.assertIn("MERGE dbo.user_platform_permissions WITH (HOLDLOCK)", PLATFORM_SETTINGS_SQL)
        for permission_key in (
            MANAGE_PLATFORM_SETTINGS,
            "access_faro",
            "access_institutional_reports",
            "access_automation",
            "access_new_programs",
        ):
            self.assertIn(permission_key, PLATFORM_SETTINGS_SQL)
        self.assertIn("cramirez@csifpr.org", PLATFORM_SETTINGS_SQL)
        self.assertNotIn("PLATFORM_SETTINGS_BOOTSTRAP_PASSWORD", PLATFORM_SETTINGS_SQL)
        self.assertNotIn("INSERT INTO dbo.users", PLATFORM_SETTINGS_SQL)

    def test_schema_executes_user_columns_before_remaining_platform_settings_sql(self):
        connection = MagicMock()
        transaction = MagicMock()
        transaction.__enter__.return_value = connection
        mocked_engine = MagicMock()
        mocked_engine.begin.return_value = transaction

        with (
            patch.object(db_schema, "engine", mocked_engine),
            patch.object(db_schema.settings, "PLATFORM_SETTINGS_BOOTSTRAP_EMAIL", None),
            patch.object(db_schema.settings, "PLATFORM_SETTINGS_BOOTSTRAP_PASSWORD", None),
        ):
            db_schema.ensure_schema_updates()

        executed_batches = [
            call.args[0]
            for call in connection.exec_driver_sql.call_args_list
        ]
        columns_batch_index = executed_batches.index(PLATFORM_SETTINGS_USER_COLUMNS_SQL)
        platform_settings_batch_index = executed_batches.index(PLATFORM_SETTINGS_SQL)

        self.assertEqual(platform_settings_batch_index, columns_batch_index + 1)

    def test_home_is_public_without_session_and_hides_settings_button(self):
        request = _Request()
        db = _Database()

        response = portal.portal_home(request=request, db=db)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("program-hub-settings-button", _body(response))
        self.assertEqual(db.get_calls, [])
        self.assertEqual(db.statements, [])

    def test_home_is_public_with_invalid_session_and_hides_settings_button(self):
        request = _Request({"user_id": 999, "other": "value"})
        db = _Database()

        response = portal.portal_home(request=request, db=db)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("program-hub-settings-button", _body(response))
        self.assertEqual(request.session, {})
        self.assertEqual(db.get_calls, [(User, 999)])
        self.assertEqual(db.statements, [])

    def test_home_hides_settings_button_for_user_without_permission(self):
        user = _user(1, "regular.user")
        request = _Request({"user_id": user.user_id})
        db = _Database(users={user.user_id: user}, results=[_Result(values=[])])

        response = portal.portal_home(request=request, db=db)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("program-hub-settings-button", _body(response))

    def test_home_shows_settings_button_for_user_with_explicit_permission(self):
        user = _user(1, "cramirez@csifpr.org", email="cramirez@csifpr.org", role="admin")
        request = _Request({"user_id": user.user_id})
        db = _Database(
            users={user.user_id: user},
            results=[_Result(values=[MANAGE_PLATFORM_SETTINGS])],
        )

        response = portal.portal_home(request=request, db=db)
        body = _body(response)

        self.assertEqual(response.status_code, 200)
        self.assertIn("program-hub-settings-button", body)
        self.assertIn('href="/platform/settings"', body)
        self.assertIn('aria-label="Configuración de plataforma"', body)

    def test_optional_user_clears_invalid_or_inactive_session(self):
        invalid_request = _Request({"user_id": "not-an-id", "other": "value"})
        self.assertIsNone(get_optional_current_user(invalid_request, _Database()))
        self.assertEqual(invalid_request.session, {})

        inactive_user = _user(2, "inactive.user", is_active=False)
        inactive_request = _Request({"user_id": inactive_user.user_id})
        self.assertIsNone(
            get_optional_current_user(
                inactive_request,
                _Database(users={inactive_user.user_id: inactive_user}),
            )
        )
        self.assertEqual(inactive_request.session, {})

    def test_bootstrap_without_both_variables_does_not_create_user(self):
        for email, password in (
            (None, None),
            ("bootstrap@example.org", None),
            (None, "temporary-secret"),
            ("   ", "temporary-secret"),
        ):
            with self.subTest(email=email, has_password=password is not None):
                db = _Database()

                user = bootstrap_platform_settings_user(
                    db,
                    email=email,
                    password=password,
                )

                self.assertIsNone(user)
                self.assertEqual(db.added, [])
                self.assertEqual(db.statements, [])
                self.assertEqual(db.flushes, 0)

    def test_bootstrap_creates_local_admin_and_assigns_permission(self):
        plain_password = "A-secure-temporary-password"
        permission = _permission(1, MANAGE_PLATFORM_SETTINGS)
        db = _Database(
            results=[
                _Result(scalar=None),
                _Result(scalar=permission),
                _Result(scalar=None),
            ]
        )

        user = bootstrap_platform_settings_user(
            db,
            email="  Bootstrap.User@Example.ORG ",
            password=plain_password,
        )

        self.assertIsNotNone(user)
        self.assertEqual(user.username, "bootstrap.user@example.org")
        self.assertEqual(user.email, "bootstrap.user@example.org")
        self.assertEqual(user.role, "admin")
        self.assertTrue(user.is_active)
        self.assertIsNone(user.residential_id)
        self.assertNotEqual(user.password_hash, plain_password)
        self.assertNotIn(plain_password, user.password_hash)
        self.assertTrue(verify_password(plain_password, user.password_hash))
        self.assertEqual(db.flushes, 1)
        self.assertEqual(len(db.added), 2)
        assignment = db.added[1]
        self.assertIsInstance(assignment, UserPlatformPermission)
        self.assertEqual(assignment.user_id, user.user_id)
        self.assertEqual(assignment.permission_id, permission.permission_id)

        login_request = _Request()
        login_response = auth.login(
            request=login_request,
            username=user.username,
            password=plain_password,
            db=_Database(results=[_Result(scalar=user)]),
        )
        self.assertEqual(login_response.status_code, 303)
        self.assertEqual(login_response.headers["location"], "/ui/new-list")
        self.assertEqual(login_request.session["user_id"], user.user_id)

        home_response = portal.portal_home(
            request=login_request,
            db=_Database(
                users={user.user_id: user},
                results=[_Result(values=[MANAGE_PLATFORM_SETTINGS])],
            ),
        )
        self.assertEqual(home_response.status_code, 200)
        self.assertIn("program-hub-settings-button", _body(home_response))

    def test_bootstrap_existing_user_preserves_password_and_does_not_duplicate(self):
        original_hash = "existing-password-hash"
        user = _user(
            7,
            "bootstrap.user@example.org",
            email=None,
            role="",
            is_active=False,
            password_hash=original_hash,
        )
        permission = _permission(1, MANAGE_PLATFORM_SETTINGS)
        existing_assignment = UserPlatformPermission(
            user_id=user.user_id,
            permission_id=permission.permission_id,
            granted_by_user_id=None,
        )
        db = _Database(
            users={user.user_id: user},
            results=[
                _Result(scalar=user),
                _Result(scalar=permission),
                _Result(scalar=None),
                _Result(scalar=user),
                _Result(scalar=permission),
                _Result(scalar=existing_assignment),
            ],
        )

        first_result = bootstrap_platform_settings_user(
            db,
            email="BOOTSTRAP.USER@EXAMPLE.ORG",
            password="new-password-that-must-not-replace-the-hash",
        )
        added_after_first_run = list(db.added)
        second_result = bootstrap_platform_settings_user(
            db,
            email="bootstrap.user@example.org",
            password="another-password-that-must-not-replace-the-hash",
        )

        self.assertIs(first_result, user)
        self.assertIs(second_result, user)
        self.assertEqual(user.email, "bootstrap.user@example.org")
        self.assertEqual(user.role, "admin")
        self.assertTrue(user.is_active)
        self.assertEqual(user.password_hash, original_hash)
        self.assertEqual(len(added_after_first_run), 1)
        self.assertIsInstance(added_after_first_run[0], UserPlatformPermission)
        self.assertEqual(db.added, added_after_first_run)
        self.assertEqual(db.flushes, 0)

    def test_settings_dependency_redirects_without_session(self):
        dependency = require_platform_permission(MANAGE_PLATFORM_SETTINGS)

        with self.assertRaises(HTTPException) as context:
            dependency(request=_Request(), db=_Database())

        self.assertEqual(context.exception.status_code, 303)
        self.assertEqual(context.exception.headers["Location"], "/login")

    def test_settings_dependency_denies_user_without_permission(self):
        user = _user(1, "admin.without.explicit.permission", role="admin")
        request = _Request({"user_id": user.user_id})
        db = _Database(users={user.user_id: user}, results=[_Result(values=[])])
        dependency = require_platform_permission(MANAGE_PLATFORM_SETTINGS)

        with self.assertRaises(HTTPException) as context:
            dependency(request=request, db=db)

        self.assertEqual(context.exception.status_code, 403)

    def test_permission_helpers_return_only_explicit_active_keys(self):
        user = _user(1, "permission.user")
        db = _Database(results=[_Result(values=[MANAGE_PLATFORM_SETTINGS, "access_faro"])])

        self.assertEqual(
            user_permission_keys(db, user),
            {MANAGE_PLATFORM_SETTINGS, "access_faro"},
        )

        db = _Database(results=[_Result(values=[MANAGE_PLATFORM_SETTINGS])])
        self.assertTrue(user_has_platform_permission(db, user, MANAGE_PLATFORM_SETTINGS))

        db = _Database(results=[_Result(values=[])])
        self.assertFalse(user_has_platform_permission(db, user, MANAGE_PLATFORM_SETTINGS))

    def test_settings_page_with_permission_renders_without_password_hash(self):
        password_hash = "DO-NOT-RENDER-THIS-PASSWORD-HASH"
        current_user = _user(
            1,
            "cramirez@csifpr.org",
            email="cramirez@csifpr.org",
            role="admin",
            password_hash=password_hash,
        )
        regular_user = _user(2, "regular.user", email="regular.user@csifpr.org")
        manage_permission = _permission(
            1,
            MANAGE_PLATFORM_SETTINGS,
            name="Administrar configuración de plataforma",
        )
        faro_permission = _permission(2, "access_faro", name="Acceder a Faro")
        db = _Database(
            results=[
                _Result(values=[manage_permission, faro_permission]),
                _Result(values=[current_user, regular_user]),
                _Result(values=[(current_user.user_id, MANAGE_PLATFORM_SETTINGS)]),
            ]
        )
        request = _Request({"user_id": current_user.user_id})

        response = platform_settings.platform_settings_index(
            request=request,
            msg=None,
            error=None,
            db=db,
            current_user=current_user,
        )
        body = _body(response)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Configuración de plataforma", body)
        self.assertIn("Accesos disponibles", body)
        self.assertIn("cramirez@csifpr.org", body)
        self.assertNotIn(password_hash, body)

    def test_authorized_grant_adds_permission_and_is_idempotent(self):
        current_user = _user(1, "settings.manager")
        target_user = _user(2, "target.user")
        permission = _permission(2, "access_faro", name="Acceder a Faro")
        request = _Request({
            "user_id": current_user.user_id,
            platform_settings._CSRF_SESSION_KEY: "valid-token",
        })
        db = _Database(
            users={target_user.user_id: target_user},
            results=[_Result(scalar=permission), _Result(scalar=None)],
        )

        response = platform_settings.grant_platform_permission(
            request=request,
            user_id=target_user.user_id,
            permission_key=permission.key,
            csrf_token="valid-token",
            db=db,
            current_user=current_user,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(db.commits, 1)
        self.assertEqual(len(db.added), 1)
        assignment = db.added[0]
        self.assertEqual(assignment.user_id, target_user.user_id)
        self.assertEqual(assignment.permission_id, permission.permission_id)
        self.assertEqual(assignment.granted_by_user_id, current_user.user_id)

        existing = UserPlatformPermission(
            user_id=target_user.user_id,
            permission_id=permission.permission_id,
            granted_by_user_id=current_user.user_id,
        )
        duplicate_db = _Database(
            users={target_user.user_id: target_user},
            results=[_Result(scalar=permission), _Result(scalar=existing)],
        )
        duplicate_response = platform_settings.grant_platform_permission(
            request=request,
            user_id=target_user.user_id,
            permission_key=permission.key,
            csrf_token="valid-token",
            db=duplicate_db,
            current_user=current_user,
        )

        self.assertEqual(duplicate_response.status_code, 303)
        self.assertEqual(duplicate_db.added, [])
        self.assertEqual(duplicate_db.commits, 0)
        self.assertIn("ya estaba asignado", _query_parameters(duplicate_response)["msg"][0])

    def test_authorized_revoke_deletes_assignment(self):
        current_user = _user(1, "settings.manager")
        target_user = _user(2, "target.user")
        permission = _permission(2, "access_faro")
        assignment = UserPlatformPermission(
            user_id=target_user.user_id,
            permission_id=permission.permission_id,
            granted_by_user_id=current_user.user_id,
        )
        request = _Request({
            "user_id": current_user.user_id,
            platform_settings._CSRF_SESSION_KEY: "valid-token",
        })
        db = _Database(
            users={target_user.user_id: target_user},
            results=[_Result(scalar=permission), _Result(scalar=assignment)],
        )

        response = platform_settings.revoke_platform_permission(
            request=request,
            user_id=target_user.user_id,
            permission_key=permission.key,
            csrf_token="valid-token",
            db=db,
            current_user=current_user,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(db.deleted, [assignment])
        self.assertEqual(db.commits, 1)

    def test_current_user_cannot_revoke_own_settings_permission(self):
        current_user = _user(1, "settings.manager")
        permission = _permission(1, MANAGE_PLATFORM_SETTINGS)
        request = _Request({
            "user_id": current_user.user_id,
            platform_settings._CSRF_SESSION_KEY: "valid-token",
        })
        db = _Database(
            users={current_user.user_id: current_user},
            results=[_Result(scalar=permission)],
        )

        response = platform_settings.revoke_platform_permission(
            request=request,
            user_id=current_user.user_id,
            permission_key=permission.key,
            csrf_token="valid-token",
            db=db,
            current_user=current_user,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(db.deleted, [])
        self.assertEqual(db.commits, 0)
        self.assertIn("propio acceso", _query_parameters(response)["error"][0])

    def test_permission_mutations_reject_invalid_csrf(self):
        current_user = _user(1, "settings.manager")
        request = _Request({platform_settings._CSRF_SESSION_KEY: "expected-token"})

        with self.assertRaises(HTTPException) as context:
            platform_settings.grant_platform_permission(
                request=request,
                user_id=2,
                permission_key="access_faro",
                csrf_token="wrong-token",
                db=_Database(),
                current_user=current_user,
            )

        self.assertEqual(context.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
