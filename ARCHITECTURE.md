# Architecture

Music Intelligence is a music analytics and recommendation service. It ingests a
user's Spotify listening history, enriches each track with Last.fm metadata, and
generates personalized playlists from a content-based (TF-IDF) taste model. A React
single-page app drives a FastAPI backend backed by PostgreSQL (Neon).

---

## Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI |
| ORM | SQLAlchemy 2.x |
| Database | PostgreSQL (Neon serverless); SQLite for tests |
| Migrations | Alembic (`alembic/versions/`) + legacy startup shims |
| ML | scikit-learn (TF-IDF, NearestNeighbors), numpy |
| Frontend | React 18, Vite, Tailwind CSS |
| External APIs | Spotify (OAuth + playback + playlists), Last.fm (tags/genres), MusicBrainz (discovery), Anthropic Claude (AI DJ) |
| Hosting | Render (web + cron); Neon (DB) |
| Tests | pytest + FastAPI TestClient (in-memory SQLite) |

---

## Repository layout

```
backend/app/
  main.py              # FastAPI app assembly, router registration, startup
  config.py            # Env-driven settings (Settings singleton)
  database.py          # Engine, session factory, get_db, run_startup_migrations
  authz.py             # Capability policy (require_capability)
  error_handlers.py    # Exception handlers + request-context/security middleware
  time_utils.py        # UTC datetime helpers
  routes/              # HTTP endpoints (9 routers)
  services/            # Business logic + external integrations
  models/              # SQLAlchemy ORM models (~17 tables)
alembic/               # Migrations
tests/                 # 171 tests across 17 files
frontend/src/          # React SPA (pages, components, contexts, hooks)
seed_demo.py           # Demo data seeding
render.yaml            # Deployment (web service + cron jobs)
```

---

## Backend modules

### Routes (`backend/app/routes/`)

| Router | Prefix | Responsibility |
|---|---|---|
| `user_routes.py` | `/user` | Spotify OAuth login/callback, session, sync, history import, metadata backfill, data export/delete |
| `playlist_routes.py` | `/playlists` | Playlist preview/generate, edit/reorder tracks, context playlists, schedules, AI DJ, background discovery trigger |
| `insights_routes.py` | `/insights` | Taste timeline, discovery feed, feedback, goals, data quality, deduplication, tag browsing |
| `music_routes.py` | `/songs` | Song explorer (filters/sort/pagination), song detail, hide/restore, retry enrichment |
| `dashboard_routes.py` | `/dashboard` | Aggregated listening stats (top artists/genres, time series) |
| `job_routes.py` | `/jobs` | Background job status + cancellation |
| `ops_routes.py` | `/ops` | Health/readiness probes, cron endpoints (sync-all, run-due-schedules), internal metrics |
| `stats_routes.py` | (root) | Public stats + Prometheus metrics exposition |

### Services (`backend/app/services/`)

| Service | Responsibility |
|---|---|
| `recommendation_service.py` | Sync history, enrichment orchestration, `recommend_songs` wrapper (feedback layering), discovery orchestration |
| `ml_recommendation_service.py` | TF-IDF + KNN engine: `knn_recommend`, taste centroid, co-occurrence, temperature sampling, discovery scoring, per-user model cache |
| `spotify_service.py` | OAuth flow, Fernet-encrypted token storage/refresh, session resolution, track fetch/resolve, playlist creation |
| `lastfm_service.py` | Last.fm client with in-process LRU + DB response cache |
| `enrichment_service.py` | Per-song enrichment (track tags → artist tags → track info) |
| `artist_enrichment_service.py` | Artist genre backfill via Spotify |
| `discovery_service.py` | Similar-artist discovery (Last.fm / MusicBrainz) |
| `generated_playlist_service.py` | Persist/serialize generated playlist previews |
| `playlist_schedule_service.py` | Recurring playlist schedules (claim/run/advance) |
| `job_service.py` | Background job records + `run_job` executor with progress reporting |
| `dj_agent_service.py` | AI DJ agent loop: taste-profile tools + Claude tool-use |
| `api_cache_service.py` | Generic DB-backed API response cache (TTL) |
| `rate_limit_service.py` | DB-backed sliding-window rate limiter |
| `metrics_service.py` / `live_metrics_service.py` | Request metrics snapshot + cumulative live counters |

### Models (`backend/app/models/`)

Core: `Song`, `Artist`, `ListeningHistory`, `Tag`, `SongTag`.
Recommendation loop: `RecommendationFeedback`, `GeneratedPlaylist`, `GeneratedPlaylistTrack`.
User state: `UserSession`, `UserSongPref`, `ListeningGoal`.
Infrastructure: `Job`, `PlaylistSchedule`, `ApiCache`, `MetricCounter`, `DedupMergeLog`.

---

## Data flow

**Authentication.** Spotify OAuth2 (`/user/login` → `/user/callback`). Tokens are
Fernet-encrypted and stored in `user_sessions`; a signed cookie (`musicintel_session`)
identifies the browser session (with an `X-User-Id` header fallback in non-production).
`load_request_user_session` resolves the current user per request. Authorization is a
capability policy in `authz.py` (`require_capability`), with a restricted demo-user
profile.

**Ingestion.** Live sync (`/user/sync-history`) pulls recent plays from Spotify;
full-history upload (`/user/import-history/job`) is pre-filtered in the browser and
processed as a background job. `sync_listening_history` normalizes into song/artist/
history rows using `INSERT … ON CONFLICT DO NOTHING`.

**Enrichment.** New songs are enriched from Last.fm (tags/genres/listeners) in batched
background jobs; responses are cached in `api_cache`.

**Recommendation.** `recommend_songs` → `knn_recommend`: each song becomes a TF-IDF
vector over tags + genres; the user's taste is a play/time-weighted centroid; results
are the nearest neighbors, boosted by session co-occurrence, temperature-sampled, and
split between familiar and discovery pools. The fitted model is cached per user, keyed
on their latest play timestamp.

**Playlist generation.** `_build_preview` applies quality guardrails (known/discovery
ratio, artist-repetition cap, recent-repeat guard); `/generate` resolves Spotify track
IDs and creates the playlist.

**AI DJ.** `/playlists/dj` runs a Claude tool-use loop (`dj_agent_service.py`) that reads
the user's taste profile via DB tools, then drives the existing playlist pipeline.

**Background work.** Jobs run on daemon threads via `job_service.run_job`; a Render cron
calls `/ops/sync-all` and `/ops/run-due-schedules` (protected by `X-Cron-Secret`).

---

## Entry points

- **App:** `backend/app/main.py` — builds the FastAPI app, installs middleware/error
  handlers, runs `run_startup_migrations()` + `create_all()`, registers all routers.
- **Request infra:** `error_handlers.py` middleware assigns request IDs, records
  timing/metrics, and sets security headers on every response.
- **DB session:** `database.py::get_db` (FastAPI dependency); engine uses `NullPool`.
- **Cron:** `/ops/sync-all`, `/ops/run-due-schedules` (Render scheduled jobs).
- **Frontend:** `frontend/src/App.jsx` → `frontend/src/lib/api.js` (API client).

---

## Configuration

Environment-driven via `config.py` (`Settings`). Key vars: `DATABASE_URL`,
`SPOTIFY_CLIENT_ID/SECRET/REDIRECT_URI`, `LASTFM_API_KEY`, `SESSION_ENCRYPTION_KEY`
(Fernet), `CRON_SECRET`, `ANTHROPIC_API_KEY`, `BACKEND_CORS_ORIGINS`, `DEMO_USER_ID`,
`APP_ENV`. Production startup validates CORS origins and the Fernet key.

---

## Testing

171 tests (pytest) in `tests/`, using FastAPI `TestClient` against an in-memory SQLite
database (`conftest.py` fixtures: `db_session`, `client_factory`). Tests exercise real
route + service + ML paths with seeded data rather than mocking internals; external
calls (Spotify, Last.fm, Anthropic) are mocked. Run: `python -m pytest tests/ -q`.
