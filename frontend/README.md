# Frontend Test UI

This frontend is split into dedicated pages for easier testing.

## Pages
- `index.html`: Home (API setup, login, background sync/backfill jobs)
- `dashboard.html`: Dashboard stats + date window compare
- `songs.html`: Song explorer + enrichment status filters
- `filters.html`: Tag filter endpoints
- `playlists.html`: Playlist generation with quality controls
- `features.html`: Insights, safe dedup, goals, ops metrics, reports

## Run
1. Start backend API:
   - `cd backend`
   - `uvicorn app.main:app --reload`
2. Serve frontend (new terminal from repo root):
   - `python -m http.server 5500 --directory frontend`
3. Open home page:
   - `http://127.0.0.1:5500/index.html`

## Flow
1. On Home, set API base URL and click Save.
2. Click Spotify Login.
3. Run background Sync History and wait for job completion.
4. Use dashboard and feature pages to inspect analytics/data quality and generate playlists.
