# MusicIntelligence

MusicIntelligence is a local music analytics and recommendation app built around Spotify listening history, Last.fm enrichment, a FastAPI backend, and a simple multi-page frontend.

It lets you:
- log into Spotify
- sync your recent listening history
- enrich songs with tags, genre, listeners, and playcount from Last.fm
- browse your music library in table form
- view dashboard analytics
- generate Spotify playlists from your saved library
- run feedback, goal, dedup, and reporting features

## Project Structure

```text
MusicIntelligence/
├─ backend/                FastAPI backend
│  └─ app/
│     ├─ models/           SQLAlchemy models
│     ├─ routes/           API endpoints
│     ├─ services/         Spotify / Last.fm / recommendation logic
│     ├─ config.py         Environment config
│     ├─ database.py       DB engine and startup migrations
│     └─ main.py           FastAPI app entrypoint
├─ frontend/               Static HTML/CSS/JS UI
├─ tests/                  Pytest tests
├─ create_tables.py        Create/migrate tables
├─ requirements.txt        Python dependencies
└─ README.md
```

## Requirements

- Python 3.14
- PostgreSQL
- Spotify developer app credentials
- Last.fm API key

## Environment Variables

Create a local `.env` file with:

```env
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/user/callback

LASTFM_API_KEY=your_lastfm_api_key
LASTFM_SHARED_SECRET=your_lastfm_shared_secret
LASTFM_API_URL=http://ws.audioscrobbler.com/2.0/

DATABASE_URL=postgresql://username:password@localhost:5432/musicdb
SESSION_ENCRYPTION_KEY=your_fernet_key
```

## Setup

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create or migrate tables:

```powershell
python create_tables.py
```

Start the backend:

```powershell
python -m uvicorn backend.app.main:app --reload
```

Start a simple frontend server:

```powershell
python -m http.server 5500 --directory frontend
```

Then open:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5500/index.html`

## Basic Usage

1. Open the frontend
2. Set API base URL to `http://127.0.0.1:8000`
3. Click `Spotify Login`
4. Click `Sync Recent History`
5. Use Dashboard, Song Explorer, Playlists, and Features pages

## Tests

Run:

```powershell
python -m pytest -q
```

## Notes

- Spotify recent history only returns the most recent 50 plays per request.
- Playlist generation now works from the existing library instead of mutating the database during every generation request.
- Generated reports and PDFs are written under `output/`.
