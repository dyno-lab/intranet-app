from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "IntranetApp"
    ENV: str = "dev"
    SECRET_KEY: str = "change-me"

    # Feature flags
    # FASE 2: habilita UI/validaciones para expediente FE-YYYY-XX-####
    # Mantén en False para volver al comportamiento estable de FASE 1.
    PHASE2_EXPEDIENTE_ENABLED: bool = False

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
