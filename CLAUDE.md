# CLAUDE.md

Working conventions for this repo. See `ARCHITECTURE.md` for the system map
(modules, data flows, entry points).

## Stack

FastAPI + SQLAlchemy 2.x + PostgreSQL (Neon), React 18 + Vite frontend, ML via
scikit-learn. Tests use pytest against in-memory SQLite. Hosted on Render.

## Layout & naming (keep consistent)

- `backend/app/routes/*_routes.py` — HTTP endpoints, one router per file.
- `backend/app/services/*_service.py` — business logic and external integrations.
- `backend/app/models/*.py` — one SQLAlchemy model per file, singular noun.
- `backend/app/deps.py` — shared FastAPI route helpers.
- Follow the existing suffix conventions (`_routes`, `_service`) for new files.

## Reuse before writing new

Prefer existing helpers over re-implementing:

- **Auth:** `from ..deps import require_user_id, require_user_session`. Every
  protected endpoint resolves the user through these — do not re-inline the
  `load_request_user_session` + 401 preamble. Use `require_user_session` when
  you also need the Spotify token.
- **Cron endpoints:** `require_cron_secret(request)` (also in `deps`).
- **Recommendations:** go through `recommend_songs` / `knn_recommend`; don't
  build a parallel scoring path.
- **External calls:** `lastfm_service` (cached) and `spotify_service`; don't call
  those APIs directly elsewhere.
- Search for an existing query/helper before adding a new one (e.g. top-artists
  queries, the `_window` filter in `dashboard_routes`).

## Load-bearing patterns — do not "clean up"

- Model imports in `main.py`, `create_tables.py`, and `models/__init__.py` look
  unused but register tables with SQLAlchemy. They're covered by Ruff
  `per-file-ignores`; never delete them.
- `recommend_songs` accepts several legacy params that are ignored but still
  passed by callers — keep the signature.
- `run_startup_migrations` in `database.py` is legacy/frozen. Add schema changes
  as Alembic migrations, not here.

## Commands

```bash
# Backend
python -m pytest tests/ -q          # tests (must stay green)
python -m ruff check .              # lint
python -m ruff format .             # format
python -m vulture backend/app --min-confidence 80   # dead-code scan

# Frontend (from frontend/)
npm test                            # vitest
npm run lint                        # eslint
npm run build                       # production build
```

## Database & migrations

- Schema changes go in `alembic/versions/` (idempotent: `IF NOT EXISTS`).
- **Deployment does not run `alembic upgrade`** — apply migrations to Neon
  manually (`alembic upgrade head`) or via the SQL console.
- Also add the change to the model so fresh DBs/tests get it via `create_all`.

## Ground rules

- **No new dependencies without asking.** Runtime deps go in `requirements.txt`;
  keep tooling dev-only.
- **Preserve behavior.** Refactors must keep the same HTTP responses; run the
  full test suite after changes.
- Keep IDs in the database — prefer correlated subqueries over pulling lists into
  Python and sending them back as `IN (...)`. This directly affects Neon compute.
- Line endings are LF (enforced by `.gitattributes`).
