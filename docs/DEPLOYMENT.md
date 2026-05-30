# Deployment Guide

MusicIntelligence is deployed as two services:

- Backend: FastAPI on Render
- Frontend: React/Vite on Vercel

The most important rule: backend variables go in Render, frontend build variables go in Vercel.

## Pre-Deploy Checks

Run these locally before pushing:

```powershell
python -c "import backend.app.main; print('backend import ok')"
python -m pytest tests -q
cd frontend
npm run build
```

Expected result:

- Backend import succeeds.
- Tests pass.
- Vite build succeeds. A chunk-size warning is acceptable for now.

## Render Backend

Render uses the `render.yaml` Blueprint.

Expected service settings:

```text
Runtime: Python
Build Command: python -m pip install -r requirements.txt
Start Command: python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
Health Check Path: /ops/health
```

Required Render environment variables:

```text
APP_ENV=production
DATABASE_URL=postgresql://...
BACKEND_CORS_ORIGINS=https://music-intelligence-eight.vercel.app
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_REDIRECT_URI=https://musicintelligence-api.onrender.com/user/callback
LASTFM_API_KEY=...
LASTFM_SHARED_SECRET=...
LASTFM_API_URL=http://ws.audioscrobbler.com/2.0/
SESSION_ENCRYPTION_KEY=...
CRON_SECRET=...
```

Notes:

- `BACKEND_CORS_ORIGINS` must contain the exact Vercel origin, with no trailing slash.
- `SPOTIFY_REDIRECT_URI` must point to the Render backend, not Vercel.
- `SESSION_ENCRYPTION_KEY` must be a Fernet key.

Generate the session encryption key locally:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Neon Database

Create a Neon PostgreSQL project and copy the pooled connection string.

Use it as:

```text
DATABASE_URL=postgresql://...
```

If Neon includes SSL query parameters, keep them.

## Spotify Dashboard

In the Spotify Developer Dashboard, add the exact redirect URI:

```text
https://musicintelligence-api.onrender.com/user/callback
```

This must exactly match Render's `SPOTIFY_REDIRECT_URI`.

Common mistakes:

- Using the Vercel URL here.
- Using `/user/spotify/callback` instead of `/user/callback`.
- Adding a trailing slash.
- Using credentials from a different Spotify app.

## Vercel Frontend

Create the Vercel project from this repo.

Expected Vercel settings:

```text
Framework Preset: Vite
Root Directory: frontend
Build Command: npm install && npm run build
Output Directory: dist
```

Required Vercel environment variable:

```text
VITE_API_BASE_URL=https://musicintelligence-api.onrender.com
```

Set it for Production. Also set it for Preview if you test preview deployments.

Important: Vite bakes environment variables into the frontend during build. If you change `VITE_API_BASE_URL`, redeploy Vercel. Prefer redeploying without build cache when debugging.

## Render Cron

The hourly sync cron is defined in `render.yaml`.

Required cron environment variables:

```text
API_URL=https://musicintelligence-api.onrender.com
CRON_SECRET=...
```

`CRON_SECRET` must match the backend web service's `CRON_SECRET`.

## Production Smoke Test

After every deployment, run:

```powershell
python scripts/smoke_check.py --api https://musicintelligence-api.onrender.com
```

Then manually test the frontend:

1. Open `https://music-intelligence-eight.vercel.app/login`.
2. Open DevTools Network tab and select All or Fetch/XHR.
3. Confirm `/user/session` calls Render:

   ```text
   https://musicintelligence-api.onrender.com/user/session
   ```

4. Click Connect with Spotify.
5. Confirm `/user/login` calls Render:

   ```text
   https://musicintelligence-api.onrender.com/user/login
   ```

6. Complete Spotify login.
7. Confirm the popup reaches `/user/callback`.
8. Confirm the app lands on the dashboard.
9. Run Sync Now.
10. Confirm enrichment starts if songs are pending.
11. Generate a playlist.
12. Create the playlist in Spotify.

## Failure Symptoms

### The login page says missing `VITE_API_BASE_URL`

You set the variable in the wrong place or did not redeploy Vercel.

Fix:

- Set `VITE_API_BASE_URL` in Vercel, not Render.
- Redeploy Vercel.

### DevTools shows `127.0.0.1:8000`

The deployed frontend was built without the Vercel env var.

Fix:

- Set `VITE_API_BASE_URL` in Vercel.
- Redeploy without build cache.
- Hard refresh or test in incognito.

### No Render logs appear when clicking login

The frontend is not calling Render.

Fix:

- Check the `/user/login` request URL in DevTools.
- Confirm Vercel's root directory is `frontend`.
- Confirm `VITE_API_BASE_URL` is set in the Vercel environment you are testing.

### Spotify says redirect URI mismatch

Render's `SPOTIFY_REDIRECT_URI` and Spotify Dashboard do not exactly match.

Fix both to:

```text
https://musicintelligence-api.onrender.com/user/callback
```

### Popup completes but main window stays logged out

The session cookie was not accepted or CORS is wrong.

Check:

- Render `APP_ENV=production`
- Render `BACKEND_CORS_ORIGINS=https://music-intelligence-eight.vercel.app`
- Frontend requests use `credentials: include`
- `/user/session` response includes the expected CORS headers

### Render refuses to start

Check logs for missing production config.

Likely missing:

- `DATABASE_URL`
- `BACKEND_CORS_ORIGINS`
- `SESSION_ENCRYPTION_KEY`
- `python-multipart` in `requirements.txt`

## Commit Checklist

Before pushing:

```powershell
git status
python -m pytest tests -q
cd frontend
npm run build
```

Before trusting production:

- GitHub Actions passed.
- Render latest deploy succeeded.
- Vercel latest deploy succeeded.
- Smoke test passed.
- Manual login/sync/playlist flow passed.
