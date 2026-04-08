from dotenv import load_dotenv
import os

load_dotenv()


class Settings:

    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
    SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

    LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
    LASTFM_SHARED_SECRET = os.getenv("LASTFM_SHARED_SECRET")
    LASTFM_API_URL = os.getenv("LASTFM_API_URL")
    LASTFM_BASE_URL = LASTFM_API_URL

    DATABASE_URL = os.getenv("DATABASE_URL")

    # Session/token security settings.
    SESSION_ENCRYPTION_KEY = os.getenv("SESSION_ENCRYPTION_KEY")


settings = Settings()
