from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "IntranetApp"
    ENV: str = "dev"
    SECRET_KEY: str = "change-me"
    SESSION_SECRET: str | None = None
    # Deprecated compatibility setting; report authorization now uses per-user permissions.
    FARO_INSTITUTIONAL_REPORT_PIN: str | None = None
    PLATFORM_SETTINGS_BOOTSTRAP_EMAIL: str | None = None
    PLATFORM_SETTINGS_BOOTSTRAP_PASSWORD: str | None = None

    # Google Workspace OAuth/OIDC (disabled until explicitly configured).
    GOOGLE_OAUTH_ENABLED: bool = False
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_ALLOWED_DOMAIN: str = "csifpr.org"
    GOOGLE_REDIRECT_URI: str = "https://servicios.csifpr.org/auth/google/callback"

    # Feature flags
    # El formato estructurado FE-YYYY-{CODIGO_RESIDENCIAL}-#### es el flujo operativo.
    PHASE2_EXPEDIENTE_ENABLED: bool = True

    # Stage 2 only: require a validated residential context for Faro requests.
    RESIDENTIAL_SCOPE_ENFORCEMENT_ENABLED: bool = False

    DB_SERVER: str
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_DRIVER: str = "ODBC Driver 18 for SQL Server"
    DB_ENCRYPT: str = "yes"
    DB_TRUST_CERT: str = "yes"

    # Optional explicit path for wkhtmltopdf. If omitted, the app will try PATH.
    WKHTMLTOPDF_PATH: str | None = None

    # Optional token for n8n/automation endpoints.
    # If set, clients must send it in X-Automation-Token.
    AUTOMATION_API_KEY: str | None = None


settings = Settings()


def require_session_secret() -> str:
    session_secret = (settings.SESSION_SECRET or "").strip()
    if len(session_secret) < 32:
        raise RuntimeError(
            "SESSION_SECRET must be configured with at least 32 random characters "
            "before the application can start."
        )
    return session_secret
