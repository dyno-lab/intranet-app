from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from authlib.integrations.base_client.errors import OAuthError
from fastapi import HTTPException
from joserfc.errors import JoseError
from sqlalchemy.exc import IntegrityError


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")

from app.api.routes import auth  # noqa: E402
from app.core.config import require_session_secret, settings  # noqa: E402
from app.core.google_oauth import (  # noqa: E402
    GOOGLE_NONCE_SESSION_KEY,
    GoogleIdentityError,
    GoogleOAuthConfiguration,
    validate_google_identity,
)
import app.models.residential  # noqa: E402, F401
from app.models.user import User  # noqa: E402


CONFIGURATION = GoogleOAuthConfiguration(
    client_id="test-client-id",
    client_secret="test-client-secret",
    allowed_domain="csifpr.org",
    redirect_uri="https://servicios.csifpr.org/auth/google/callback",
)


class _Request:
    def __init__(self, session: dict | None = None):
        self.session = session if session is not None else {}


class _Result:
    def __init__(self, values: list[User]):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values

    def scalar_one_or_none(self):
        if len(self.values) > 1:
            raise AssertionError("Expected at most one scalar result")
        return self.values[0] if self.values else None


class _Database:
    def __init__(
        self,
        results: list[list[User]],
        *,
        commit_error: Exception | None = None,
    ):
        self.results = list(results)
        self.commit_error = commit_error
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, statement):
        self.statements.append(statement)
        if not self.results:
            raise AssertionError("Unexpected database query")
        return _Result(self.results.pop(0))

    def commit(self):
        self.commits += 1
        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.rollbacks += 1


def _user(
    user_id: int,
    *,
    email: str = "employee@csifpr.org",
    google_sub: str | None = None,
    is_active: bool = True,
) -> User:
    user = User(
        username=f"user-{user_id}",
        email=email,
        google_sub=google_sub,
        password_hash="local-password-hash",
        role="user",
        is_active=is_active,
    )
    user.user_id = user_id
    return user


def _claims(**overrides) -> dict:
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CONFIGURATION.client_id,
        "exp": 9_999_999_999,
        "nonce": "expected-nonce",
        "email_verified": True,
        "hd": CONFIGURATION.allowed_domain,
        "sub": "google-subject-123",
        "email": "employee@csifpr.org",
    }
    claims.update(overrides)
    return claims


@contextmanager
def _enabled_configuration():
    with patch.multiple(
        settings,
        GOOGLE_OAUTH_ENABLED=True,
        GOOGLE_CLIENT_ID=CONFIGURATION.client_id,
        GOOGLE_CLIENT_SECRET=CONFIGURATION.client_secret,
        GOOGLE_ALLOWED_DOMAIN=CONFIGURATION.allowed_domain,
        GOOGLE_REDIRECT_URI=CONFIGURATION.redirect_uri,
    ):
        yield


class SessionAndLocalLoginTests(unittest.TestCase):
    def test_missing_or_short_session_secret_is_rejected(self):
        for session_secret in (None, "too-short"):
            with self.subTest(session_secret=session_secret):
                with patch.object(settings, "SESSION_SECRET", session_secret):
                    with self.assertRaisesRegex(RuntimeError, "32 random characters"):
                        require_session_secret()

    def test_local_login_rejects_inactive_user(self):
        request = _Request()
        db = _Database([[_user(1, is_active=False)]])
        response = auth.login(
            request=request,
            username="user-1",
            password="not-checked",
            db=db,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("user_id", request.session)

    def test_google_button_only_appears_when_fully_configured(self):
        request = _Request()
        with patch.object(settings, "GOOGLE_OAUTH_ENABLED", False):
            disabled_response = auth.login_page(request)
        with _enabled_configuration():
            enabled_response = auth.login_page(request)
        self.assertNotIn("Continuar con Google", disabled_response.body.decode())
        self.assertIn("Continuar con Google", enabled_response.body.decode())


class GoogleIdentityValidationTests(unittest.TestCase):
    def _validate(self, claims: dict):
        return validate_google_identity(
            claims,
            configuration=CONFIGURATION,
            expected_nonce="expected-nonce",
            now=1_000,
        )

    def test_valid_identity_is_normalized(self):
        subject, email = self._validate(_claims(email=" Employee@CSIFPR.ORG "))
        self.assertEqual(subject, "google-subject-123")
        self.assertEqual(email, "employee@csifpr.org")

    def test_nonce_mismatch_is_rejected(self):
        with self.assertRaises(GoogleIdentityError):
            self._validate(_claims(nonce="wrong-nonce"))

    def test_invalid_issuer_is_rejected(self):
        with self.assertRaises(GoogleIdentityError):
            self._validate(_claims(iss="https://attacker.example"))

    def test_invalid_audience_is_rejected(self):
        with self.assertRaises(GoogleIdentityError):
            self._validate(_claims(aud="another-client"))

    def test_multiple_audiences_require_authorized_party(self):
        with self.assertRaises(GoogleIdentityError):
            self._validate(_claims(aud=[CONFIGURATION.client_id, "another-client"]))
        subject, _ = self._validate(
            _claims(
                aud=[CONFIGURATION.client_id, "another-client"],
                azp=CONFIGURATION.client_id,
            )
        )
        self.assertEqual(subject, "google-subject-123")

    def test_expired_token_is_rejected(self):
        with self.assertRaises(GoogleIdentityError):
            self._validate(_claims(exp=1_000))

    def test_external_email_domain_is_rejected(self):
        with self.assertRaises(GoogleIdentityError):
            self._validate(_claims(email="employee@example.com"))

    def test_missing_or_incorrect_hosted_domain_is_rejected(self):
        for hosted_domain in (None, "example.com"):
            with self.subTest(hosted_domain=hosted_domain):
                with self.assertRaises(GoogleIdentityError):
                    self._validate(_claims(hd=hosted_domain))

    def test_unverified_email_is_rejected(self):
        with self.assertRaises(GoogleIdentityError):
            self._validate(_claims(email_verified=False))


class GoogleOAuthRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_feature_flag_returns_not_found(self):
        with patch.object(settings, "GOOGLE_OAUTH_ENABLED", False):
            with self.assertRaises(HTTPException) as raised:
                await auth.google_login(_Request())
        self.assertEqual(raised.exception.status_code, 404)

    async def test_missing_configuration_returns_service_unavailable(self):
        with (
            patch.object(settings, "GOOGLE_OAUTH_ENABLED", True),
            patch.object(settings, "GOOGLE_CLIENT_ID", None),
        ):
            with self.assertRaises(HTTPException) as raised:
                await auth.google_login(_Request())
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn("client", raised.exception.detail.lower())

    async def test_state_mismatch_from_authlib_is_rejected(self):
        request = _Request({GOOGLE_NONCE_SESSION_KEY: "expected-nonce"})
        client = MagicMock()
        client.authorize_access_token = AsyncMock(
            side_effect=OAuthError(error="mismatching_state")
        )
        with (
            _enabled_configuration(),
            patch.object(auth, "create_google_oauth_client", return_value=client),
        ):
            response = await auth.google_callback(request, _Database([]))
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("mismatching_state", response.body.decode())
        self.assertNotIn(GOOGLE_NONCE_SESSION_KEY, request.session)

    async def test_jose_validation_error_is_rejected(self):
        request = _Request({GOOGLE_NONCE_SESSION_KEY: "expected-nonce"})
        client = MagicMock()
        client.authorize_access_token = AsyncMock(
            side_effect=JoseError("invalid ID token")
        )
        with (
            _enabled_configuration(),
            patch.object(auth, "create_google_oauth_client", return_value=client),
        ):
            response = await auth.google_callback(request, _Database([]))
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("invalid ID token", response.body.decode())

    async def test_inactive_user_is_rejected(self):
        response, request, db = await self._callback(
            [[_user(1, google_sub="google-subject-123", is_active=False)]]
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("user_id", request.session)
        self.assertEqual(db.commits, 0)

    async def test_unknown_user_is_rejected(self):
        response, request, db = await self._callback([[], []])
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("user_id", request.session)
        self.assertEqual(db.commits, 0)

    async def test_duplicate_email_is_rejected(self):
        response, request, db = await self._callback([[], [_user(1), _user(2)]])
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("user_id", request.session)
        self.assertEqual(db.commits, 0)

    async def test_first_login_links_google_subject(self):
        user = _user(7)
        response, request, db = await self._callback([[], [user]])
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/ui/new-list")
        self.assertEqual(user.google_sub, "google-subject-123")
        self.assertEqual(request.session, {"user_id": 7})
        self.assertEqual(db.commits, 1)

    async def test_link_integrity_error_rolls_back_and_rejects_login(self):
        user = _user(7)
        integrity_error = IntegrityError("UPDATE users", {}, Exception("duplicate"))
        request = _Request({GOOGLE_NONCE_SESSION_KEY: "expected-nonce"})
        db = _Database([[], [user]], commit_error=integrity_error)
        client = MagicMock()
        client.authorize_access_token = AsyncMock(return_value={"userinfo": _claims()})
        with (
            _enabled_configuration(),
            patch.object(auth, "create_google_oauth_client", return_value=client),
        ):
            response = await auth.google_callback(request, db)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(db.rollbacks, 1)
        self.assertNotIn("user_id", request.session)

    async def test_existing_google_subject_logs_in_without_relinking(self):
        user = _user(8, google_sub="google-subject-123")
        response, request, db = await self._callback([[user]])
        self.assertEqual(response.status_code, 303)
        self.assertEqual(request.session, {"user_id": 8})
        self.assertEqual(db.commits, 0)
        self.assertEqual(len(db.statements), 1)

    async def test_different_existing_google_subject_is_rejected(self):
        user = _user(9, google_sub="different-subject")
        response, request, db = await self._callback([[], [user]])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(user.google_sub, "different-subject")
        self.assertNotIn("user_id", request.session)
        self.assertEqual(db.commits, 0)

    async def _callback(self, results: list[list[User]]):
        request = _Request({GOOGLE_NONCE_SESSION_KEY: "expected-nonce"})
        db = _Database(results)
        client = MagicMock()
        client.authorize_access_token = AsyncMock(return_value={"userinfo": _claims()})
        with (
            _enabled_configuration(),
            patch.object(auth, "create_google_oauth_client", return_value=client),
        ):
            response = await auth.google_callback(request, db)
        return response, request, db


if __name__ == "__main__":
    unittest.main()
