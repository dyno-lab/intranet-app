from __future__ import annotations

import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from authlib.integrations.starlette_client import OAuth

from app.core.config import settings


GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
GOOGLE_SCOPES = "openid email profile"
GOOGLE_NONCE_SESSION_KEY = "google_oauth_nonce"


class GoogleOAuthConfigurationError(RuntimeError):
    pass


class GoogleIdentityError(ValueError):
    pass


@dataclass(frozen=True)
class GoogleOAuthConfiguration:
    client_id: str
    client_secret: str
    allowed_domain: str
    redirect_uri: str


def _configured_value(value: str | None) -> str:
    return (value or "").strip()


def get_google_oauth_configuration() -> GoogleOAuthConfiguration:
    values = GoogleOAuthConfiguration(
        client_id=_configured_value(settings.GOOGLE_CLIENT_ID),
        client_secret=_configured_value(settings.GOOGLE_CLIENT_SECRET),
        allowed_domain=_configured_value(settings.GOOGLE_ALLOWED_DOMAIN).lower(),
        redirect_uri=_configured_value(settings.GOOGLE_REDIRECT_URI),
    )
    if not all((values.client_id, values.client_secret, values.allowed_domain, values.redirect_uri)):
        raise GoogleOAuthConfigurationError(
            "Google OAuth is enabled but its required configuration is incomplete."
        )
    if not values.redirect_uri.startswith("https://"):
        raise GoogleOAuthConfigurationError("Google OAuth redirect URI must use HTTPS.")
    return values


def google_oauth_is_available() -> bool:
    if not settings.GOOGLE_OAUTH_ENABLED:
        return False
    try:
        get_google_oauth_configuration()
    except GoogleOAuthConfigurationError:
        return False
    return True


def create_google_oauth_client(configuration: GoogleOAuthConfiguration):
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=configuration.client_id,
        client_secret=configuration.client_secret,
        server_metadata_url=GOOGLE_DISCOVERY_URL,
        client_kwargs={"scope": GOOGLE_SCOPES},
    )
    return oauth.google


def new_google_nonce() -> str:
    return secrets.token_urlsafe(32)


def clear_google_oauth_session(session: dict[str, Any]) -> None:
    session.pop(GOOGLE_NONCE_SESSION_KEY, None)
    for key in list(session):
        if key.startswith("_state_google_"):
            session.pop(key, None)


def validate_google_identity(
    claims: Mapping[str, Any],
    *,
    configuration: GoogleOAuthConfiguration,
    expected_nonce: str,
    now: int | None = None,
) -> tuple[str, str]:
    issuer = claims.get("iss")
    if issuer not in GOOGLE_ISSUERS:
        raise GoogleIdentityError("Invalid token issuer.")

    audience = claims.get("aud")
    if isinstance(audience, str):
        valid_audience = audience == configuration.client_id
    elif isinstance(audience, list):
        valid_audience = configuration.client_id in audience
        if len(audience) > 1:
            valid_audience = valid_audience and claims.get("azp") == configuration.client_id
    else:
        valid_audience = False
    if not valid_audience:
        raise GoogleIdentityError("Invalid token audience.")

    try:
        expires_at = int(claims.get("exp"))
    except (TypeError, ValueError):
        raise GoogleIdentityError("Invalid token expiration.") from None
    if expires_at <= (int(time.time()) if now is None else now):
        raise GoogleIdentityError("Expired token.")

    nonce = claims.get("nonce")
    if not isinstance(nonce, str) or not secrets.compare_digest(nonce, expected_nonce):
        raise GoogleIdentityError("Invalid token nonce.")

    if claims.get("email_verified") is not True:
        raise GoogleIdentityError("Google email is not verified.")

    allowed_domain = configuration.allowed_domain
    hosted_domain = claims.get("hd")
    if not isinstance(hosted_domain, str) or hosted_domain.strip().lower() != allowed_domain:
        raise GoogleIdentityError("Google Workspace domain is not allowed.")

    subject = claims.get("sub")
    email = claims.get("email")
    if not isinstance(subject, str) or not subject.strip():
        raise GoogleIdentityError("Google subject is missing.")
    if not isinstance(email, str) or not email.strip():
        raise GoogleIdentityError("Google email is missing.")

    normalized_email = email.strip().lower()
    if normalized_email.rpartition("@")[2] != allowed_domain:
        raise GoogleIdentityError("Google email domain is not allowed.")

    return subject.strip(), normalized_email
