# Deployment Guide

## Backend: Render

This repo includes a `render.yaml` Blueprint for the FastAPI backend. Use Neon for the PostgreSQL database and paste Neon's pooled connection string into Render as `DATABASE_URL`.

Render uses:

- Build command: `python -m pip install -r requirements.txt`
- Start command: `python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
- Health check: `/ops/health`
- Database: Neon PostgreSQL via `DATABASE_URL`

Create these environment variables in Render when prompted:

```text
BACKEND_CORS_ORIGINS=https://your-vercel-app.vercel.app,http://127.0.0.1:5500,http://localhost:5500
DATABASE_URL=postgresql://...
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_REDIRECT_URI=https://your-render-service.onrender.com/user/callback
LASTFM_API_KEY=...
LASTFM_SHARED_SECRET=...
SESSION_ENCRYPTION_KEY=...
```

## Database: Neon

Create a Neon project and copy the pooled PostgreSQL connection string. Use the `postgresql://...` URL, not a Prisma URL.

In Render, set:

```text
DATABASE_URL=your-neon-pooled-connection-string
```

Keep SSL enabled in the Neon connection string if Neon includes it.

Generate `SESSION_ENCRYPTION_KEY` locally:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

After the backend URL exists, update the Spotify Developer Dashboard redirect URI to match:

```text
https://your-render-service.onrender.com/user/callback
```

## Frontend: Vercel

Create a Vercel project from this GitHub repo and set:

```text
Framework Preset: Other
Root Directory: frontend
Build Command: leave empty
Output Directory: leave empty
Install Command: leave empty
```

The frontend directory includes `vercel.json` for clean static routing and basic browser security headers.

After Vercel gives you a URL, add it to the backend `BACKEND_CORS_ORIGINS` list in Render.

Set the default backend URL in `frontend/config.js`:

```js
window.MUSICINTEL_CONFIG = {
  apiBaseUrl: "https://your-render-service.onrender.com",
};
```

The frontend also stores the API base URL in browser local storage after a user clicks Save on the home page.
