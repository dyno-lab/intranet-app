"""Focused guards; full authentication/role integration is tested separately."""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes import platform_settings
from app.core.platform_permissions import ACCESS_COMMUNITY, ACCESS_AUTOMATION
from app.models.platform_permission import PlatformPermission
from app.models.user import User
from app.models.user_platform_permission import UserPlatformPermission


class CommunitySettingsGuardTests(unittest.TestCase):
    def setUp(self):
        self.request = SimpleNamespace(session={"platform_settings_csrf_token": "csrf-for-test"})
        self.target = User(user_id=2, username="target", role="user")

    def db_for(self, permission):
        db = MagicMock(spec=Session)
        db.get.return_value = self.target
        db.execute.return_value.scalar_one_or_none.return_value = permission
        return db

    def call(self, endpoint, db, *, actor_role="admin", token="csrf-for-test", key=ACCESS_COMMUNITY):
        return endpoint(
            request=self.request, user_id=2, permission_key=key, csrf_token=token,
            db=db, current_user=User(user_id=1, username="actor", role=actor_role),
        )

    def assert_no_writes(self, db):
        db.add.assert_not_called()
        db.delete.assert_not_called()
        db.commit.assert_not_called()
        db.flush.assert_not_called()

    def test_generic_grant_and_revoke_redirect_all_roles_without_mutation(self):
        permission = PlatformPermission(permission_id=3, key=ACCESS_COMMUNITY, name="Comunidad", is_active=True)
        for endpoint in (platform_settings.grant_platform_permission, platform_settings.revoke_platform_permission):
            for role in ("admin", "supervisor", "user"):
                with self.subTest(endpoint=endpoint.__name__, role=role):
                    db = self.db_for(permission)
                    response = self.call(endpoint, db, actor_role=role)
                    self.assertEqual(response.status_code, 303)
                    self.assertEqual(response.headers["location"], "/platform/settings/users/2/community")
                    self.assert_no_writes(db)

    def test_redirect_does_not_skip_csrf_user_or_permission_validation(self):
        permission = PlatformPermission(permission_id=3, key=ACCESS_COMMUNITY, name="Comunidad", is_active=True)
        for endpoint in (platform_settings.grant_platform_permission, platform_settings.revoke_platform_permission):
            for invalid, status in (("token", 403), ("user", 404), ("permission", 404)):
                with self.subTest(endpoint=endpoint.__name__, invalid=invalid):
                    db = self.db_for(None if invalid == "permission" else permission)
                    if invalid == "user":
                        db.get.return_value = None
                    with self.assertRaises(HTTPException) as caught:
                        self.call(endpoint, db, token="wrong" if invalid == "token" else "csrf-for-test")
                    self.assertEqual(caught.exception.status_code, status)
                    self.assert_no_writes(db)

    def test_other_application_permissions_still_use_existing_grant_and_revoke(self):
        permission = PlatformPermission(permission_id=4, key=ACCESS_AUTOMATION, name="Automatizaciones", is_active=True)
        for endpoint in (platform_settings.grant_platform_permission, platform_settings.revoke_platform_permission):
            with self.subTest(endpoint=endpoint.__name__):
                db = self.db_for(permission)
                assignment = UserPlatformPermission(user_id=2, permission_id=4)
                db.execute.return_value.scalar_one_or_none.side_effect = [
                    permission, assignment if endpoint is platform_settings.revoke_platform_permission else None,
                ]
                response = self.call(endpoint, db, actor_role="supervisor", key=ACCESS_AUTOMATION)
                self.assertEqual(response.status_code, 303)
                self.assertIn("section=permissions", response.headers["location"])
                db.commit.assert_called_once()
                if endpoint is platform_settings.revoke_platform_permission:
                    db.delete.assert_called_once_with(assignment)
                else:
                    self.assertTrue(any(isinstance(call.args[0], UserPlatformPermission) for call in db.add.call_args_list))

    def test_permission_card_has_only_dedicated_community_action(self):
        permission = PlatformPermission(permission_id=3, key=ACCESS_COMMUNITY, name="Comunidad", is_active=True)
        request = SimpleNamespace(url_for=lambda _, **kwargs: "/static/" + kwargs["path"])
        for assigned in (set(), {ACCESS_COMMUNITY}):
            with self.subTest(assigned=bool(assigned)):
                html = platform_settings.templates.get_template("platform_settings/user_detail.html").render(
                    request=request, current_user=User(user_id=1, username="admin", role="admin"),
                    target_user=self.target, section="permissions", permissions=[permission],
                    assigned_permission_keys=assigned, community_enabled=True,
                    manage_platform_settings_key="manage_platform_settings", csrf_token="csrf-for-test",
                )
                self.assertIn("Configurar Comunidad", html)
                self.assertIn('/platform/settings/users/2/community', html)
                self.assertNotIn('/permissions/access_community/grant', html)
                self.assertNotIn('/permissions/access_community/revoke', html)


if __name__ == "__main__":
    unittest.main()
