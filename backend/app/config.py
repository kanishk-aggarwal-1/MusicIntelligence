from dotenv import load_dotenv
import os

load_dotenv()


def _normalize_database_url(url):
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def _parse_csv(value):
    return [item.strip() for item in (value or "").split(",") if item.strip()]


class Settings:

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

    BACKEND_CORS_ORIGINS = _parse_csv(os.getenv("BACKEND_CORS_ORIGINS")) or [
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ]


settings = Settings()
