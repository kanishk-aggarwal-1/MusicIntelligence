from dotenv import load_dotenv
import os
from cryptography.fernet import Fernet

load_dotenv()


def _normalize_database_url(url):
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def _parse_csv(value):
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _clean_origins(origins):
    return [origin.rstrip("/") for origin in origins if origin]


class Settings:

    APP_ENV = os.getenv("APP_ENV", "development").strip().lower()

    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
    SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

    LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
    LASTFM_SHARED_SECRET = os.getenv("LASTFM_SHARED_SECRET")
    LASTFM_API_URL = os.getenv("LASTFM_API_URL")
    LASTFM_BASE_URL = LASTFM_API_URL

    DATABASE_URL = _normalize_database_url(os.getenv("DATABASE_URL"))

    # Session/token security settings.
    SESSION_ENCRYPTION_KEY = os.getenv("SESSION_ENCRYPTION_KEY")

    # Secret expected in X-Cron-Secret header for /ops/sync-all.
    CRON_SECRET = os.getenv("CRON_SECRET")

    _default_local_origins = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ]
    BACKEND_CORS_ORIGINS = _clean_origins(_parse_csv(os.getenv("BACKEND_CORS_ORIGINS")) or _default_local_origins)

    if APP_ENV == "production":
        if "*" in BACKEND_CORS_ORIGINS:
            raise ValueError("BACKEND_CORS_ORIGINS must not contain '*' in production")
        if BACKEND_CORS_ORIGINS == _default_local_origins:
            raise ValueError("BACKEND_CORS_ORIGINS must be set explicitly in production")
        if not SESSION_ENCRYPTION_KEY:
            raise ValueError("SESSION_ENCRYPTION_KEY must be set in production")
        try:
            Fernet(SESSION_ENCRYPTION_KEY.encode("utf-8"))
        except Exception as exc:
            raise ValueError("SESSION_ENCRYPTION_KEY must be a valid Fernet key in production") from exc


settings = Settings()
